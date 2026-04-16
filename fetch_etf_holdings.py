import requests
from bs4 import BeautifulSoup
import sqlite3
import re
from datetime import datetime
from pathlib import Path
import sys

DB_PATH = Path.home() / "MyStock" / "data" / "market_data.db"

# 追蹤的 ETF 清單（代號: 中文名稱）
ETF_LIST = {
    "00981A": "主動統一台股增長",
    "0050":   "元大台灣50",
    "0052":   "富邦科技",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.moneydj.com/etf/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

def fetch_holdings(etf_code):
    url = f"https://www.moneydj.com/ETF/X/Basic/Basic0007B.xdjhtm?etfid={etf_code}.TW"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    date_str = ""
    for tag in soup.find_all(string=re.compile(r"資料日期")):
        m = re.search(r"(\d{4}/\d{2}/\d{2})", tag)
        if m:
            date_str = m.group(1).replace("/", "-")
            break

    holdings = []
    for row in soup.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 3:
            continue
        name_td = cols[0].get_text(strip=True)
        ratio_td = cols[1].get_text(strip=True)
        shares_td = cols[2].get_text(strip=True)
        try:
            ratio = float(ratio_td)
        except ValueError:
            continue
        code_m = re.search(r"\((\d{4,5})", name_td)
        stock_code = code_m.group(1) if code_m else ""
        stock_name = re.sub(r"\(.*", "", name_td).strip()
        shares_clean = shares_td.replace(",", "").strip()
        try:
            shares = int(float(shares_clean))
        except ValueError:
            shares = 0
        holdings.append({"stock_code": stock_code, "stock_name": stock_name, "ratio": ratio, "shares": shares})

    return date_str, holdings

def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS etf_holdings_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            etf_code    TEXT    NOT NULL,
            data_date   TEXT    NOT NULL,
            stock_code  TEXT    NOT NULL,
            stock_name  TEXT,
            ratio       REAL,
            shares      INTEGER,
            created_at  TEXT    DEFAULT (datetime('now','localtime')),
            UNIQUE (etf_code, data_date, stock_code)
        )
    """)
    conn.commit()

def save_holdings(conn, etf_code, date_str, holdings):
    rows = [(etf_code, date_str, h["stock_code"], h["stock_name"], h["ratio"], h["shares"]) for h in holdings]
    conn.executemany("""
        INSERT OR IGNORE INTO etf_holdings_history
            (etf_code, data_date, stock_code, stock_name, ratio, shares)
        VALUES (?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()

def main():
    # 可指定單一 ETF：python3 fetch_etf_holdings.py 0050
    targets = sys.argv[1:] if len(sys.argv) > 1 else list(ETF_LIST.keys())

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    for etf_code in targets:
        etf_code = etf_code.upper()
        name = ETF_LIST.get(etf_code, etf_code)
        print(f"\n[{etf_code}] {name}")
        try:
            date_str, holdings = fetch_holdings(etf_code)
            print(f"  資料日期：{date_str}，共 {len(holdings)} 檔")
            if holdings:
                save_holdings(conn, etf_code, date_str, holdings)
                print(f"  ✓ 完成")
            else:
                print(f"  ✗ 無持股資料")
        except Exception as e:
            print(f"  ✗ 失敗：{e}")

    conn.close()

if __name__ == "__main__":
    main()
