# Stock Research Wiki

A personal stock market research knowledge base powered by Notion,
with a daily email scanner that surfaces insights from financial newsletters.

## Notion Wiki

Open the wiki: [Stock Research Wiki](https://www.notion.so/36e2c67180ea812aa388d904b172c66e)

### Databases

| Database | Purpose |
|----------|--------|
| **Industry Research** | Sector-level thesis, macro tailwinds/headwinds, conviction ratings |
| **Company Research** | Individual stock deep-dives, linked to industries |
| **Holdings** | Your portfolio — stocks, ETFs, bonds, REITs, crypto |
| **Market Notes** | Auto-populated daily from newsletter scan + your own memos |

---

## Daily Email Scanner

Runs every weekday at 09:00 Taiwan time via GitHub Actions.

**What it does:**
1. Searches Gmail for emails from financial newsletters (The Economist, Bloomberg, FT, etc.)
2. Sends each email to Claude for investment insight extraction
3. Creates structured entries in the **Market Notes** Notion database

### Setup (one-time)

#### 1. Gmail credentials

```bash
# Install the local-only setup dependency
pip install google-auth-oauthlib

# Run the setup script
python setup_gmail_token.py
```

This opens a browser for Gmail sign-in, then prints two values to add as GitHub secrets.

#### 2. Anthropic API key

Get your key from [console.anthropic.com](https://console.anthropic.com).

#### 3. GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Source |
|--------|--------|
| `GMAIL_TOKEN` | Output of `setup_gmail_token.py` |
| `NOTION_TOKEN` | Your Notion integration token |
| `ANTHROPIC_API_KEY` | From console.anthropic.com |

#### 4. Trigger a test run

Go to **Actions → Daily Email Stock Scan → Run workflow** to verify everything works.

### Customizing newsletter sources

Edit the `NEWSLETTER_SENDERS` list in `email_scanner.py` to add or remove sender domains.

---

## Research Workflow

1. Each morning, check **Market Notes** in Notion for auto-generated insights
2. Spot a sector trend → add deeper analysis to **Industry Research**
3. Find key companies → add to **Company Research**, link to the industry
4. Buy a position → log it in **Holdings** (ticker, qty, avg cost, asset type)
