import json
import os
import re
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")

ETFS = {
    "00403A": "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=63YTW",
    "00981A": "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=49YTW",
}


JS_EXTRACT = """() => {
    const el = document.querySelector('#asset');
    const m = el?.innerText?.match(/資料日期:(\\d{4}\\/\\d{2}\\/\\d{2})/);
    const date = m ? m[1] : '';
    const holdings = [];
    el.querySelectorAll('table').forEach(table => {
        const headers = Array.from(table.querySelectorAll('th')).map(h => h.innerText.trim());
        if (!headers.includes('股票代號')) return;
        table.querySelectorAll('tbody tr').forEach(row => {
            const cells = row.querySelectorAll('td');
            if (cells.length >= 4) {
                holdings.push({
                    code: cells[0].innerText.trim(),
                    name: cells[1].innerText.trim(),
                    shares: cells[2].innerText.trim().replace(/,/g, ''),
                    weight: cells[3].innerText.trim(),
                });
            }
        });
    });
    return { date, holdings };
}"""


def fetch_all_holdings() -> dict[str, tuple[str, list[dict]] | Exception]:
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for etf_code, url in ETFS.items():
            try:
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.locator("#asset table").first.wait_for(timeout=15000)
                data = page.evaluate(JS_EXTRACT)
                page.close()
                results[etf_code] = (data["date"], data["holdings"])
            except Exception as e:
                results[etf_code] = e
        browser.close()
    return results


def load_previous(etf_code: str) -> list[dict]:
    path = f"data/{etf_code}.json"
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f).get("holdings", [])


def save_today(etf_code: str, date: str, holdings: list[dict]):
    path = f"data/{etf_code}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": date, "holdings": holdings}, f, ensure_ascii=False, indent=2)


def diff_holdings(prev: list[dict], curr: list[dict]) -> str:
    prev_map = {h["code"]: h for h in prev}
    curr_map = {h["code"]: h for h in curr}

    added = [h for code, h in curr_map.items() if code not in prev_map]
    removed = [h for code, h in prev_map.items() if code not in curr_map]
    changed = []
    for code, h in curr_map.items():
        if code in prev_map and h["shares"] != prev_map[code]["shares"]:
            old = int(prev_map[code]["shares"])
            new = int(h["shares"])
            diff = new - old
            sign = "▲" if diff > 0 else "▼"
            changed.append(f"  {sign}{h['code']} {h['name']}: {old:,}→{new:,} ({sign}{abs(diff):,})")

    lines = []
    if added:
        lines.append("【新增】")
        lines += [f"  ✚ {h['code']} {h['name']} {h['weight']}" for h in added]
    if removed:
        lines.append("【刪除】")
        lines += [f"  ✖ {h['code']} {h['name']}" for h in removed]
    if changed:
        lines.append("【股數變動】")
        lines += changed

    return "\n".join(lines)


def notify(message: str):
    if not DISCORD_WEBHOOK:
        print("[NOTIFY]", message)
        return
    requests.post(
        DISCORD_WEBHOOK,
        json={"content": f"```\n{message}\n```"},
        timeout=10,
    )


def main():
    today = datetime.now().strftime("%Y/%m/%d")
    any_change = False
    full_msg = f"\n📊 ETF持股追蹤 {today}"

    all_holdings = fetch_all_holdings()

    for etf_code, result in all_holdings.items():
        if isinstance(result, Exception):
            full_msg += f"\n\n[{etf_code}] 抓取失敗: {result}"
            continue
        try:
            date, holdings = result
            prev = load_previous(etf_code)
            save_today(etf_code, date, holdings)

            if not prev:
                full_msg += f"\n\n[{etf_code}] 首次建立基準資料（{len(holdings)}支）"
                continue

            changes = diff_holdings(prev, holdings)
            if changes:
                any_change = True
                full_msg += f"\n\n[{etf_code}] 資料日期:{date}\n{changes}"
            else:
                full_msg += f"\n\n[{etf_code}] 無變動（共{len(holdings)}支）"

        except Exception as e:
            full_msg += f"\n\n[{etf_code}] 處理失敗: {e}"

    if any_change or "首次" in full_msg or "失敗" in full_msg:
        notify(full_msg)
    else:
        print(full_msg)
        print("無變動，不推播。")


if __name__ == "__main__":
    main()
