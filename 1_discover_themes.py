#!/usr/bin/env python3
"""
[1/4] HiStock 題材分類自動探測腳本

掃描 HiStock 的概念股/產業 ID 範圍，找出所有有效的題材分類。
輸出: data/histock_themes_all.json (格式: {id: {"name": ..., "stock_count": ...}})

執行時間: 約 5-10 分鐘 (掃 200 個 ID, 含速率限制)
建議: 每月跑一次更新對照表

用法：
  python3 1_discover_themes.py
  python3 1_discover_themes.py --range 50,250  # 自訂掃描範圍
"""
import requests
from bs4 import BeautifulSoup
import re
import json
import time
import os
import sys
import argparse
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": "https://histock.tw/",
}

URL_TEMPLATE = "https://histock.tw/global/globalclass.aspx?mid=0&id={id}"

# 標題正則: <title>上市 XXX概念股成份股行情報價</title> 或 <title>上市 XXX成份股行情報價</title>
TITLE_RE = re.compile(r"上市\s*(.+?)(?:概念股)?成份股", re.S)

# 排除明顯不是台股題材的 (例如美股、陸股分類)
EXCLUDE_KEYWORDS = ["美股", "陸股", "港股", "日股", "韓股"]


def probe_id(theme_id: int, session: requests.Session) -> dict | None:
    """探測單一 ID，回傳 {name, stock_count} 或 None"""
    url = URL_TEMPLATE.format(id=theme_id)
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        if len(resp.text) < 5000:  # 異常短的回應通常是錯誤頁
            return None

        soup = BeautifulSoup(resp.text, "lxml")

        # 從 <title> 取題材名稱
        title_tag = soup.find("title")
        if not title_tag:
            return None
        title = title_tag.get_text(strip=True)

        m = TITLE_RE.search(title)
        if not m:
            return None
        theme_name = m.group(1).strip()

        # 排除非台股
        if any(kw in theme_name for kw in EXCLUDE_KEYWORDS):
            return None

        # 數成分股數
        stock_links = soup.find_all("a", href=re.compile(r"/stock/\d+$"))
        valid_codes = set()
        for a in stock_links:
            code = a["href"].split("/")[-1]
            if code.isdigit() and len(code) == 4:
                valid_codes.add(code)

        # 過濾掉導覽列重複出現的個股 (台積電等熱門股會在側邊欄)
        # 真正的成分股一定 >= 5 檔，否則跳過
        if len(valid_codes) < 5:
            return None

        return {
            "name": theme_name,
            "stock_count": len(valid_codes),
        }
    except Exception as e:
        print(f"  [!] id={theme_id}: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--range", default="50,250",
                        help="ID 掃描範圍, 例如 50,250")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="每次請求間隔秒數 (避免被擋)")
    parser.add_argument("--output", default="data/histock_themes_all.json")
    args = parser.parse_args()

    start_id, end_id = map(int, args.range.split(","))
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    print(f"=== HiStock 題材分類探測 ===")
    print(f"範圍: id={start_id} ~ {end_id} (共 {end_id - start_id + 1} 個)")
    print(f"延遲: {args.delay} 秒/次")
    print(f"預估時間: {(end_id - start_id + 1) * args.delay / 60:.1f} 分鐘")
    print()

    session = requests.Session()
    session.headers.update(HEADERS)

    # 先測連通性
    print("[檢查連通性] 測試 id=117 (雲端概念)...")
    test = probe_id(117, session)
    if test is None:
        print("❌ 連通性測試失敗 - HiStock 在這台機器上不可用")
        print("   請先執行 test_histock_connectivity.py 排查")
        sys.exit(1)
    print(f"✅ 連通性 OK ({test['name']}, {test['stock_count']} 檔)")
    print()

    found = {}
    for tid in range(start_id, end_id + 1):
        info = probe_id(tid, session)
        if info:
            found[str(tid)] = info
            print(f"  id={tid:3d}  {info['name']:<30s}  ({info['stock_count']} 檔)")
        else:
            # 安靜略過
            pass
        time.sleep(args.delay)

    print()
    print(f"=== 完成 ===")
    print(f"找到 {len(found)} 個有效題材")

    # 存檔
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "themes": found,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"已儲存: {args.output}")


if __name__ == "__main__":
    main()
