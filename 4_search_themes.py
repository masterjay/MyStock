#!/usr/bin/env python3
"""
[4/4] 半自動填寫工具 - 從探測結果搜尋題材, 幫你補完 themes_config.json

讀入: data/histock_themes_all.json (1_discover_themes.py 產出)
輸出: 列印對照表, 讓你手動填回 config/themes_config.json

用法:
  python3 4_search_themes.py                # 列出全部探測到的題材
  python3 4_search_themes.py 散熱           # 搜尋包含「散熱」的題材
  python3 4_search_themes.py PCB 載板       # 多關鍵字 (OR)
"""
import json
import sys
import os

DISCOVERY_PATH = "data/histock_themes_all.json"


def main():
    if not os.path.exists(DISCOVERY_PATH):
        print(f"❌ 找不到 {DISCOVERY_PATH}")
        print(f"   請先執行: python3 1_discover_themes.py")
        sys.exit(1)

    with open(DISCOVERY_PATH, encoding="utf-8") as f:
        data = json.load(f)

    themes = data["themes"]  # {id: {name, stock_count}}
    keywords = sys.argv[1:]

    if keywords:
        # 過濾
        filtered = {
            tid: info for tid, info in themes.items()
            if any(kw in info["name"] for kw in keywords)
        }
        print(f"=== 搜尋 {keywords} - 找到 {len(filtered)} 個 ===\n")
        target = filtered
    else:
        print(f"=== 全部 {len(themes)} 個題材 ===\n")
        target = themes

    # 依 ID 排序
    sorted_items = sorted(target.items(), key=lambda x: int(x[0]))
    print(f"{'ID':<6}{'題材名稱':<30}{'成分股數':>8}")
    print("-" * 48)
    for tid, info in sorted_items:
        print(f"{tid:<6}{info['name']:<30}{info['stock_count']:>5} 檔")

    if keywords and target:
        print(f"\n💡 複製對應 ID 到 config/themes_config.json:")
        for tid, info in sorted_items:
            print(f'   "{info["name"]}": {tid},')


if __name__ == "__main__":
    main()
