#!/usr/bin/env python3
"""
[1b/4] 從 CMoney 抓取「概念股總覽」中的所有概念股 ID 與名稱

取代 1_discover_themes.py - CMoney 比 HiStock 新得多 (有 CoWoS, HBM, ASIC 等),
而且一次就拿全部, 不用掃描.

輸出: data/cmoney_themes_all.json (格式: {C50XXX: 題材名稱})

執行時間: 約 5 秒
"""
import requests
from bs4 import BeautifulSoup
import re
import json
import os
from datetime import datetime

URL = "https://www.cmoney.tw/forum/concept"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}
OUTPUT_PATH = "data/cmoney_themes_all.json"


def main():
    print(f"=== 抓取 CMoney 概念股總覽 ===")
    print(f"URL: {URL}\n")

    resp = requests.get(URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    print(f"HTTP {resp.status_code}, len: {len(resp.text)}")

    soup = BeautifulSoup(resp.text, "lxml")
    concept_links = soup.find_all("a", href=re.compile(r"/forum/concept/C\d+"))

    themes = {}
    for a in concept_links:
        m = re.search(r"/forum/concept/(C\d+)", a["href"])
        name = a.get_text(strip=True)
        if m and name and 1 < len(name) < 30:
            cid = m.group(1)
            # 同 ID 出現多次時保留第一次
            if cid not in themes:
                themes[cid] = name

    print(f"\n找到 {len(themes)} 個概念股分類")

    # 顯示前 30 個
    print(f"\n前 30 個範例:")
    for cid, name in list(themes.items())[:30]:
        print(f"  {cid}  {name}")

    # 存檔
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "CMoney 股市爆料同學會",
        "themes": themes,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n已儲存: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
