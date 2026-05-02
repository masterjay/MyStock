#!/usr/bin/env python3
"""
[2b/4] 從 CMoney 抓取指定題材的成分股 (含當日股價)

取代 2_fetch_theme_stocks.py - CMoney 表格直接含股價/漲跌幅/成交量,
比 HiStock 多附加值, 但每題材只 SSR 8 檔 (各題材的核心龍頭股).

讀入: config/themes_config_cmoney.json
輸出: data/theme_stocks_cmoney.json (含成分股 + 當日股價快照)

執行時間: 約 30 秒 (15 次請求 x 1.5 秒)

用法: python3 2b_fetch_cmoney_stocks.py
"""
import requests
from bs4 import BeautifulSoup
import re
import json
import time
import os
import sys
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}
URL_TEMPLATE = "https://www.cmoney.tw/forum/concept/{cid}"

CONFIG_PATH = "config/themes_config_cmoney.json"
OUTPUT_PATH = "data/theme_stocks_cmoney.json"


def parse_price(s: str) -> float | None:
    """'2,215' → 2215.0, '-' → None"""
    if not s or s.strip() in ("-", "--", ""):
        return None
    try:
        return float(s.replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def parse_volume(s: str) -> int | None:
    """'4.7萬' → 47000, '4,156' → 4156"""
    if not s:
        return None
    s = s.strip().replace(",", "")
    try:
        if "萬" in s:
            return int(float(s.replace("萬", "")) * 10000)
        return int(float(s))
    except ValueError:
        return None


def fetch_theme(theme_key: str, cid: str, session: requests.Session) -> dict:
    """抓取單一題材的成分股 (含股價快照)"""
    url = URL_TEMPLATE.format(cid=cid)
    resp = session.get(url, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")

    # 找成分股表格 - parent class = table__plural--active
    stocks = []
    rows = soup.find_all(class_=re.compile(r"table__plural"))
    seen_codes = set()

    for row in rows:
        # 每一個 row 應該是一個 tr 或 div, 內含個股資料
        text = row.get_text(" ", strip=True)
        # 找到代號
        m = re.search(r"\b(\d{4})\b", text)
        if not m:
            continue
        code = m.group(1)
        if code in seen_codes:
            continue
        seen_codes.add(code)

        # 嘗試解析 row 的所有 td 或子元素
        cells = row.find_all(["td", "div", "span"])
        cell_texts = [c.get_text(strip=True) for c in cells if c.get_text(strip=True)]

        # 從表格找此 row 對應的所有欄位資料
        # 表格欄位: 個股名稱 / 股價 / 漲跌 / 漲跌幅% / 成交張數 / 本益比
        # 用 row 整段文字 split 找
        # row 文字像 "2330 台積電 2,215 -50 -2.21% 4.7萬 33.40 自選"
        parts = text.split()
        # parts[0] = code, parts[1] = name, parts[2] = price, parts[3] = change,
        # parts[4] = change_pct, parts[5] = volume, parts[6] = pe

        stock_info = {"code": code, "name": "", "price": None,
                      "change": None, "change_pct": None,
                      "volume": None, "pe": None}

        if len(parts) >= 2:
            stock_info["name"] = parts[1]
        if len(parts) >= 3:
            stock_info["price"] = parse_price(parts[2])
        if len(parts) >= 4:
            stock_info["change"] = parse_price(parts[3])
        if len(parts) >= 5:
            stock_info["change_pct"] = parse_price(parts[4])
        if len(parts) >= 6:
            stock_info["volume"] = parse_volume(parts[5])
        if len(parts) >= 7:
            stock_info["pe"] = parse_price(parts[6])

        stocks.append(stock_info)

    return {
        "concept_id": cid,
        "stocks": stocks,
    }


def main():
    if not os.path.exists(CONFIG_PATH):
        print(f"❌ 找不到 {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    raw = config["themes"]
    # 過濾: 跳過註解項 (key 開頭 _) 和空的 ID
    themes = {k: v for k, v in raw.items()
              if not k.startswith("_") and isinstance(v, str) and v.startswith("C")}

    print(f"=== 抓取 {len(themes)} 個題材的成分股 ===\n")

    session = requests.Session()
    session.headers.update(HEADERS)

    result = {}
    failed = []

    for theme_key, cid in themes.items():
        try:
            data = fetch_theme(theme_key, cid, session)
            n = len(data["stocks"])
            if n < 3:
                print(f"  ⚠️  {theme_key:<20s} ({cid}): 只有 {n} 檔, 可能解析失敗")
                failed.append(theme_key)
            else:
                result[theme_key] = data
                stock_codes = [s["code"] for s in data["stocks"]]
                print(f"  ✅ {theme_key:<20s} ({cid}): {n} 檔 - {stock_codes}")
        except Exception as e:
            print(f"  ❌ {theme_key:<20s} ({cid}): {type(e).__name__}: {e}")
            failed.append(theme_key)
        time.sleep(1.5)

    print()
    if failed:
        print(f"⚠️  失敗: {failed}")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "CMoney",
        "themes": result,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total_stocks = sum(len(v["stocks"]) for v in result.values())
    print(f"\n已儲存: {OUTPUT_PATH}")
    print(f"總計 {len(result)} 個題材, {total_stocks} 檔個股 (含跨題材重複)")


if __name__ == "__main__":
    main()
