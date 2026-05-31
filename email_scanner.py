#!/usr/bin/env python3
"""
Daily email scanner: searches Gmail for financial newsletters,
analyzes content with Claude, and creates Market Notes in Notion.
"""
import base64
import json
import os
import re
from datetime import datetime, timedelta, timezone

import anthropic
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from notion_client import Client as NotionClient

# ── Config ───────────────────────────────────────────────────────────────────
NOTION_MARKET_NOTES_DB = "3dd69eead0294ee394a144e5d6640817"

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Sender domains to scan. Extend this list with any newsletters you subscribe to.
NEWSLETTER_SENDERS = [
    "economist.com",
    "morningbrew.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "seekingalpha.com",
    "substack.com",
    "barrons.com",
    "marketwatch.com",
]

SYSTEM_PROMPT = """You are a financial research assistant. Your job is to extract
actionable stock market insights from financial newsletter emails and structure
them for a personal investment research wiki."""
# ─────────────────────────────────────────────────────────────────────────────


def build_gmail_service():
    token_json = os.environ.get("GMAIL_TOKEN", "")
    if not token_json:
        raise ValueError("GMAIL_TOKEN environment variable is required")

    creds = Credentials.from_authorized_user_info(
        json.loads(token_json), GMAIL_SCOPES
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build("gmail", "v1", credentials=creds)


def search_newsletters(service, hours_back: int = 24) -> list[dict]:
    since = (
        datetime.now(timezone.utc) - timedelta(hours=hours_back)
    ).strftime("%Y/%m/%d")
    sender_query = " OR ".join(f"from:{s}" for s in NEWSLETTER_SENDERS)
    query = f"({sender_query}) after:{since}"

    result = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=25)
        .execute()
    )
    messages = result.get("messages", [])

    emails = []
    for msg in messages:
        full = (
            service.users()
            .messages()
            .get(userId="me", messageId=msg["id"], format="full")
            .execute()
        )
        headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}
        body = _extract_text(full["payload"])
        if body and len(body.strip()) > 200:
            emails.append(
                {
                    "subject": headers.get("Subject", "(no subject)"),
                    "sender": headers.get("From", ""),
                    "date": headers.get("Date", ""),
                    "body": body[:10000],
                }
            )
    return emails


def _extract_text(payload: dict) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    if mime == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            html = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            return re.sub(r"<[^>]+>", " ", html)  # strip tags, keep text
    for part in payload.get("parts", []):
        text = _extract_text(part)
        if text:
            return text
    return ""


def analyze_email(client: anthropic.Anthropic, email: dict) -> dict | None:
    """Extract investment insights from an email using Claude."""
    user_prompt = f"""Analyze this financial newsletter email and extract investment insights.

From: {email['sender']}
Subject: {email['subject']}
Date: {email['date']}

Content:
{email['body']}

Return a JSON object with these fields:
- "relevant": true/false (does this contain actionable stock/market/economic insights?)
- "title": concise title for a research note (if relevant)
- "category": one of ["Macro", "Sector", "Stock", "Earnings", "Policy", "Technical"]
- "importance": one of ["High", "Medium", "Low"]
- "tags": array of matching tags from ["Fed", "Inflation", "GDP", "Earnings", "China", "Taiwan", "AI", "Rates"]
- "summary": 2-3 sentences capturing the key investment-relevant thesis
- "key_points": array of 3-5 specific, actionable bullet points

Return only valid JSON, no markdown fences."""

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    try:
        text = response.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
        data = json.loads(text)
        return data if data.get("relevant") else None
    except (json.JSONDecodeError, IndexError, KeyError):
        return None


def push_to_notion(notion: NotionClient, analysis: dict, email: dict) -> str:
    """Create a Market Notes page in Notion from a Claude analysis result."""
    today = datetime.now().strftime("%Y-%m-%d")
    bullet_points = "\n".join(f"- {p}" for p in analysis.get("key_points", []))
    content = (
        f"## Summary\n\n{analysis.get('summary', '')}\n\n"
        f"## Key Points\n\n{bullet_points}\n\n"
        f"---\n*Source: {email['sender']} — {email['subject']}*"
    )

    page = notion.pages.create(
        parent={"database_id": NOTION_MARKET_NOTES_DB},
        properties={
            "Title": {"title": [{"text": {"content": analysis["title"]}}]},
            "Date": {"date": {"start": today}},
            "Category": {"select": {"name": analysis.get("category", "Macro")}},
            "Importance": {"select": {"name": analysis.get("importance", "Medium")}},
            "Tags": {
                "multi_select": [{"name": t} for t in analysis.get("tags", [])]
            },
        },
        children=[
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                },
            }
        ],
    )
    return page["url"]


def main():
    for var in ("NOTION_TOKEN", "ANTHROPIC_API_KEY", "GMAIL_TOKEN"):
        if not os.environ.get(var):
            raise ValueError(f"{var} environment variable is required")

    gmail = build_gmail_service()
    claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    notion = NotionClient(auth=os.environ["NOTION_TOKEN"])

    print("Searching Gmail for recent financial newsletters...")
    emails = search_newsletters(gmail)
    print(f"Found {len(emails)} emails to analyze")

    created = 0
    for email in emails:
        subject_preview = email["subject"][:70]
        print(f"  Analyzing: {subject_preview}...")
        try:
            analysis = analyze_email(claude, email)
            if analysis:
                url = push_to_notion(notion, analysis, email)
                print(f"    → Note created: {analysis['title']}")
                print(f"      {url}")
                created += 1
            else:
                print(f"    → Not relevant, skipped")
        except Exception as e:
            print(f"    → Error: {e}")

    print(f"\nDone: {created}/{len(emails)} notes created in Notion")


if __name__ == "__main__":
    main()
