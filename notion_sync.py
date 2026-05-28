#!/usr/bin/env python3
"""Sync ETF holdings from data/ JSON files to the Notion ETF Holdings database."""
import json
import os
from datetime import datetime
from notion_client import Client

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
ETF_HOLDINGS_DB_ID = "2b1e1b1c2ff1420fa5d9512e0fa1ef65"


def load_all_holdings() -> dict[str, tuple[str, list[dict]]]:
    holdings = {}
    for etf_code in ["00403A", "00981A", "00988A"]:
        path = f"data/{etf_code}.json"
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
                holdings[etf_code] = (data.get("date", ""), data.get("holdings", []))
    return holdings


def fetch_existing_pages(notion: Client) -> dict[str, dict]:
    pages = {}
    cursor = None
    while True:
        kwargs: dict = {"database_id": ETF_HOLDINGS_DB_ID, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = notion.databases.query(**kwargs)
        for page in resp["results"]:
            props = page["properties"]
            etf = (props.get("ETF Code", {}).get("select") or {}).get("name", "")
            rt = props.get("Stock Code", {}).get("rich_text", [])
            code = rt[0]["plain_text"] if rt else ""
            if etf and code:
                pages[f"{etf}|{code}"] = page
        if not resp["has_more"]:
            break
        cursor = resp["next_cursor"]
    return pages


def build_props(etf_code: str, stock: dict, date_str: str, change: str) -> dict:
    props: dict = {
        "Stock Name": {"title": [{"text": {"content": stock["name"]}}]},
        "Stock Code": {"rich_text": [{"text": {"content": stock["code"]}}]},
        "ETF Code": {"select": {"name": etf_code}},
        "Weight (%)": {"rich_text": [{"text": {"content": stock.get("weight", "")}}]},
        "Shares": {"rich_text": [{"text": {"content": str(stock.get("shares", ""))}}]},
        "Change": {"select": {"name": change}},
    }
    if date_str:
        try:
            iso = datetime.strptime(date_str, "%Y/%m/%d").strftime("%Y-%m-%d")
            props["Data Date"] = {"date": {"start": iso}}
        except ValueError:
            pass
    return props


def detect_change(page: dict, new_shares: str) -> str:
    rt = page["properties"].get("Shares", {}).get("rich_text", [])
    old = rt[0]["plain_text"] if rt else ""
    if not old:
        return "Initial"
    if old == new_shares:
        return "Unchanged"
    try:
        return "Increased" if int(new_shares) > int(old) else "Decreased"
    except ValueError:
        return "Unchanged"


def sync():
    if not NOTION_TOKEN:
        print("[NOTION] NOTION_TOKEN not set — skipping sync")
        return

    notion = Client(auth=NOTION_TOKEN)
    all_holdings = load_all_holdings()
    if not all_holdings:
        print("[NOTION] No data files found in data/")
        return

    print("[NOTION] Fetching existing Notion entries...")
    existing = fetch_existing_pages(notion)
    print(f"[NOTION] {len(existing)} existing entries found")

    current_keys: set[str] = set()
    created = updated = removed = 0

    for etf_code, (date_str, holdings) in all_holdings.items():
        print(f"[NOTION] {etf_code}: {len(holdings)} stocks, date={date_str}")
        for stock in holdings:
            key = f"{etf_code}|{stock['code']}"
            current_keys.add(key)
            change = detect_change(existing[key], stock["shares"]) if key in existing else "Initial"
            props = build_props(etf_code, stock, date_str, change)
            if key in existing:
                notion.pages.update(page_id=existing[key]["id"], properties=props)
                updated += 1
            else:
                notion.pages.create(
                    parent={"database_id": ETF_HOLDINGS_DB_ID}, properties=props
                )
                created += 1

    for key, page in existing.items():
        if key not in current_keys:
            existing_change = (page["properties"].get("Change", {}).get("select") or {}).get("name", "")
            if existing_change != "Removed":
                notion.pages.update(
                    page_id=page["id"],
                    properties={"Change": {"select": {"name": "Removed"}}},
                )
                removed += 1

    print(f"[NOTION] Sync complete: {created} created, {updated} updated, {removed} marked removed")


if __name__ == "__main__":
    sync()
