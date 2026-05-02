#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TSWE 股票清單擷取工具

從 backend/data/ 多個既有 JSON 聯集股票清單，給回測腳本使用。
不對外抓資料，全部用本地檔案，速度快。

支援的資料結構（依 2026-05-01 確認的真實檔案）：
  foreign_top_stocks.json: {top_buy/top_sell/trust_top_buy/trust_top_sell: [...]}
  macd_signal_stocks.json: {signals: [{code, name, ...}]}
  new_high_stocks.json:    {stocks: [{code, name, ...}]}
  top_volume_stocks.json:  {stocks: [{code, name, ...}]}
  top30_history.json:      [{date, codes: ["2330", "2303", ...]}]

用法（被 backtest_batch 匯入）：
  from stock_universe import get_universe
  universe = get_universe()
  codes = [u["code"] for u in universe]

或直接命令列：
  python3 stock_universe.py
  python3 stock_universe.py --min-sources 2
  python3 stock_universe.py --count 200
"""

import json
import argparse
from pathlib import Path
from collections import Counter

DATA_DIR = Path(__file__).resolve().parent / "data"


def _load_json_safe(path: Path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _from_foreign_top(data):
    """foreign_top_stocks.json: 從 4 個陣列聯集"""
    if not isinstance(data, dict):
        return []
    items = []
    for key in ["top_buy", "top_sell", "trust_top_buy", "trust_top_sell"]:
        arr = data.get(key, [])
        if not isinstance(arr, list):
            continue
        for it in arr:
            if isinstance(it, dict) and it.get("code"):
                items.append((str(it["code"]), str(it.get("name", ""))))
    return items


def _from_signals(data):
    if not isinstance(data, dict):
        return []
    arr = data.get("signals", [])
    if not isinstance(arr, list):
        return []
    return [(str(it["code"]), str(it.get("name", "")))
            for it in arr if isinstance(it, dict) and it.get("code")]


def _from_stocks(data):
    if not isinstance(data, dict):
        return []
    arr = data.get("stocks", [])
    if not isinstance(arr, list):
        return []
    return [(str(it["code"]), str(it.get("name", "")))
            for it in arr if isinstance(it, dict) and it.get("code")]


def _from_top30_history(data):
    """top30_history.json: list of {date, codes: [str]}, codes 只有代號"""
    if not isinstance(data, list):
        return []
    items = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        codes = entry.get("codes", [])
        if not isinstance(codes, list):
            continue
        for c in codes:
            items.append((str(c), ""))
    return items


SOURCES = [
    ("foreign_top_stocks.json", _from_foreign_top, "foreign_top"),
    ("macd_signal_stocks.json", _from_signals, "macd_signal"),
    ("new_high_stocks.json", _from_stocks, "new_high"),
    ("top_volume_stocks.json", _from_stocks, "top_volume"),
    ("top30_history.json", _from_top30_history, "top30_history"),
]


def get_universe(verbose: bool = False):
    code_to_info = {}

    for filename, parser, src_label in SOURCES:
        file_path = DATA_DIR / filename
        if not file_path.exists():
            if verbose:
                print(f"  {filename}: ⚠️ 檔案不存在")
            continue

        data = _load_json_safe(file_path)
        if data is None:
            if verbose:
                print(f"  {filename}: ⚠️ 讀取失敗")
            continue

        items = parser(data)
        if verbose:
            print(f"  {filename}: {len(items)} 筆")

        for code, name in items:
            if code not in code_to_info:
                code_to_info[code] = {"name": name, "sources": set()}
            else:
                if not code_to_info[code]["name"] and name:
                    code_to_info[code]["name"] = name
            code_to_info[code]["sources"].add(src_label)

    universe = []
    for code, info in code_to_info.items():
        universe.append({
            "code": code,
            "name": info["name"],
            "sources": sorted(info["sources"]),
            "source_count": len(info["sources"]),
        })

    universe.sort(key=lambda x: (-x["source_count"], x["code"]))
    return universe


def main():
    parser = argparse.ArgumentParser(description="從本地資料聯集股票清單")
    parser.add_argument("--count", type=int, default=0,
                        help="只取前 N 檔（按出現頻率，0=全部）")
    parser.add_argument("--min-sources", type=int, default=1,
                        help="至少出現在 N 個來源才採用（預設 1）")
    parser.add_argument("--codes-only", action="store_true",
                        help="只印代號（一行一個）")
    args = parser.parse_args()

    universe = get_universe(verbose=not args.codes_only)
    universe = [u for u in universe if u["source_count"] >= args.min_sources]
    if args.count > 0:
        universe = universe[:args.count]

    if args.codes_only:
        for u in universe:
            print(u["code"])
        return

    print(f"\n聯集後總數：{len(universe)} 檔（去重後、min-sources>={args.min_sources}）")

    print(f"\n前 30 檔（按出現頻率）：")
    print(f"{'代號':<8}{'名稱':<10}{'來源數':>6}  來源")
    print("-" * 80)
    for u in universe[:30]:
        srcs = ", ".join(u["sources"])
        name_display = u['name'] if u['name'] else '(無名稱)'
        print(f"{u['code']:<8}{name_display:<10}{u['source_count']:>6}  {srcs}")

    print(f"\n📊 出現次數分布：")
    dist = Counter(u["source_count"] for u in universe)
    for count in sorted(dist.keys(), reverse=True):
        stocks_n = dist[count]
        bar = "█" * min(50, stocks_n // 2 + 1)
        print(f"  {count} 個來源: {stocks_n:>4} 檔  {bar}")

    with_name = sum(1 for u in universe if u["name"])
    print(f"\n📝 名稱完整度：{with_name}/{len(universe)} 檔有名稱")


if __name__ == "__main__":
    main()
