#!/usr/bin/env python3
"""
內部人持股異動收集器 v1.1
資料源: https://mopsov.twse.com.tw/mops/web/ajax_stapap1
"""
import requests
from bs4 import BeautifulSoup
import json, os, sys
from datetime import datetime, timedelta
from time import sleep
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
WATCHLIST_PATH = SCRIPT_DIR.parent / "watchlist_notion.json"
if not WATCHLIST_PATH.exists():
    WATCHLIST_PATH = SCRIPT_DIR / "../watchlist_notion.json"
OUTPUT_PATH = DATA_DIR / "insider_trading.json"

MOPS_BASE = "https://mopsov.twse.com.tw"
MOPS_PAGE = f"{MOPS_BASE}/mops/web/stapap1"
MOPS_AJAX = f"{MOPS_BASE}/mops/web/ajax_stapap1"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}
EXTRA_STOCKS = ["2449","1560","4979","1503","2454","4772"]
REQUEST_DELAY = 5
_session = None

def get_session():
    global _session
    if _session is not None:
        return _session
    _session = requests.Session()
    _session.headers.update(HEADERS)
    try:
        r = _session.get(MOPS_PAGE, timeout=15)
        print(f"  session ok, cookie: {dict(_session.cookies)}")
    except Exception as e:
        print(f"  session fail: {e}")
    return _session

def load_watchlist_codes():
    codes = set(EXTRA_STOCKS)
    try:
        with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for theme_codes in data.get("themes", {}).values():
            codes.update(theme_codes)
    except Exception as e:
        print(f"  watchlist: {e}")
    return sorted(codes)

def parse_int(s):
    s = s.replace(",", "").replace("\u2013", "0").replace("\u2014","0").replace("-","0").strip()
    if not s: return 0
    try: return int(s)
    except: return 0

def fetch_insider_holdings(stock_id, roc_year, month):
    session = get_session()
    payload = {
        "encodeURIComponent": "1", "step": "1", "firstin": "1", "off": "1",
        "keyword4": "", "code1": "", "TYPEK2": "", "checkbtn": "",
        "queryName": "co_id", "inpuType": "co_id", "TYPEK": "all",
        "isnew": "false", "co_id": str(stock_id),
        "year": str(roc_year), "month": str(month).zfill(2),
    }
    try:
        resp = session.post(MOPS_AJAX, data=payload, timeout=30)
        resp.encoding = "utf-8"
    except Exception as e:
        print(f"    net err {stock_id}: {e}")
        return None
    if "\u9801\u9762\u7121\u6cd5\u57f7\u884c" in resp.text or "THE PAGE CANNOT" in resp.text:
        global _session
        _session = None
        sleep(10)
        session = get_session()
        try:
            resp = session.post(MOPS_AJAX, data=payload, timeout=30)
            resp.encoding = "utf-8"
            if "THE PAGE CANNOT" in resp.text:
                return None
        except:
            return None
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", {"class": "hasBorder"})
    if not table: return None
    rows = table.find_all("tr")
    if len(rows) < 3: return None
    records = []
    for tr in rows[2:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 6: continue
        if cells[0] == "\u8077\u7a31" or not cells[0]: continue
        try:
            records.append({
                "title": cells[0], "name": cells[1],
                "elected_shares": parse_int(cells[2]),
                "current_shares": parse_int(cells[3]),
                "pledged_shares": parse_int(cells[4]),
                "related_shares": parse_int(cells[6]) if len(cells) > 6 else 0,
            })
        except: continue
    return records

def calc_changes(stock_id, stock_name, curr_records, prev_records):
    if not curr_records: return []
    prev_map = {}
    if prev_records:
        for r in prev_records:
            prev_map[(r["title"], r["name"])] = r["current_shares"]
    changes = []
    for r in curr_records:
        key = (r["title"], r["name"])
        prev_shares = prev_map.get(key, r["current_shares"])
        change = r["current_shares"] - prev_shares
        if change == 0: continue
        change_lots = change // 1000
        if change_lots == 0: continue
        changes.append({
            "stock_id": stock_id, "stock_name": stock_name,
            "title": r["title"], "name": r["name"],
            "prev_shares": prev_shares, "current_shares": r["current_shares"],
            "change_shares": change, "change_lots": change_lots,
            "pledged_shares": r["pledged_shares"],
        })
    return changes

def get_stock_name(stock_id):
    import sqlite3
    try:
        conn = sqlite3.connect(str(SCRIPT_DIR / "data" / "market_data.db"))
        cur = conn.cursor()
        cur.execute("SELECT stock_name FROM stock_master WHERE stock_id=?", (stock_id,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else stock_id
    except: return stock_id

def main(target_year=None, target_month=None):
    print("=" * 50)
    print("insider v1.1")
    print("=" * 50)
    print("\nSession...")
    get_session()
    if target_year and target_month:
        roc_year, month = int(target_year), int(target_month)
    else:
        today = datetime.now()
        last = today.replace(day=1) - timedelta(days=1)
        roc_year, month = last.year - 1911, last.month
    prev_year, prev_month = (roc_year - 1, 12) if month == 1 else (roc_year, month - 1)
    ad_year = roc_year + 1911
    print(f"target: {ad_year}/{month:02d}, compare: {prev_year+1911}/{prev_month:02d}")
    codes = load_watchlist_codes()
    print(f"stocks: {len(codes)}")
    all_changes, success, fail = [], 0, 0
    for i, sid in enumerate(codes):
        sname = get_stock_name(sid)
        print(f"\n[{i+1}/{len(codes)}] {sid} {sname}")
        curr = fetch_insider_holdings(sid, roc_year, month)
        sleep(REQUEST_DELAY)
        if curr is None:
            print(f"  no data"); fail += 1; continue
        print(f"  found {len(curr)} insiders")
        prev = fetch_insider_holdings(sid, prev_year, prev_month)
        sleep(REQUEST_DELAY)
        changes = calc_changes(sid, sname, curr, prev)
        if changes:
            all_changes.extend(changes)
            for c in changes:
                sign = "BUY" if c["change_lots"] > 0 else "SELL"
                print(f"  {sign} {c['title']} {c['name']}: {c['change_lots']:+d}")
        else:
            print(f"  no change")
        success += 1
    buyers = sorted([c for c in all_changes if c["change_lots"] > 0], key=lambda x: x["change_lots"], reverse=True)
    sellers = sorted([c for c in all_changes if c["change_lots"] < 0], key=lambda x: x["change_lots"])
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "target_month": f"{ad_year}/{month:02d}",
        "compare_month": f"{prev_year+1911}/{prev_month:02d}",
        "total_stocks_checked": len(codes), "success_count": success, "fail_count": fail,
        "summary": {"total_changes": len(all_changes), "total_buyers": len(buyers), "total_sellers": len(sellers)},
        "buyers": buyers, "sellers": sellers,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nDone! {len(all_changes)} changes ({len(buyers)} buy / {len(sellers)} sell)")
    print(f"Output: {OUTPUT_PATH}")
    return output

if __name__ == "__main__":
    if len(sys.argv) == 3: main(sys.argv[1], sys.argv[2])
    else: main()
