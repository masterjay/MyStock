#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TSWE 歷史訊號實戰回顧工具

對指定時間範圍內所有觸發過的訊號、計算每筆在不同持有期的實際報酬。
用於驗證「過去如果照系統做、實際表現會如何」。

用法：
  # 預設：最近 60 天的訊號回顧
  python3 pullback_signal_review.py

  # 指定時間範圍
  python3 pullback_signal_review.py --start 2026-03-01 --end 2026-04-30

  # 用 v1 策略對照
  python3 pullback_signal_review.py --strategy v1

  # 存結果到 JSON
  python3 pullback_signal_review.py --save-json /tmp/review.json
"""

import sys
import argparse
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_pullback_strategy import (
    fetch_yahoo, fetch_twii, add_indicators, detect_signals
)
from stock_universe import get_universe

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger(__name__)


def find_signals_for_stock(stock: dict, market_df, start_date: str, end_date: str,
                           strategy: str = "v2_F"):
    """找出單檔股票在 [start, end] 範圍內所有觸發訊號的日期"""
    code = stock["code"]
    name = stock.get("name", "")
    try:
        df = fetch_yahoo(code, 720)  # 抓久一點，確保涵蓋
        if len(df) < 80:
            return []
        df = add_indicators(df)
        df = detect_signals(
            df,
            require_recent_high=True,
            high_lookback=240,
            high_within_days=30,
            market_df=market_df,
            strategy=strategy,
        )

        start_ts = pd.to_datetime(start_date)
        end_ts = pd.to_datetime(end_date)
        in_range = df[(df.index >= start_ts) & (df.index <= end_ts)]

        signals = []
        for idx, row in in_range[in_range["signal"]].iterrows():
            signals.append({
                "code": code,
                "name": name,
                "signal_date": idx.strftime("%Y-%m-%d"),
                "close_at_signal": float(row["close"]),
                "osc": float(row["osc"]),
                "k": float(row["k"]),
            })
        return signals
    except Exception as e:
        return []


def calculate_returns(signal: dict, full_df: pd.DataFrame, today: pd.Timestamp):
    """計算單筆訊號在不同持有期的報酬"""
    signal_ts = pd.to_datetime(signal["signal_date"])
    future = full_df[full_df.index > signal_ts]
    if len(future) < 1:
        return None

    entry_price = future.iloc[0]["open"]
    entry_date = future.iloc[0].name
    latest_price = future.iloc[-1]["close"]

    def get_ret_at(n_days):
        if len(future) > n_days:
            exit_price = future.iloc[n_days]["close"]
            ret = (exit_price - entry_price) / entry_price * 100
            return {"ret": ret, "exit_date": future.iloc[n_days].name.strftime("%Y-%m-%d")}
        return None

    return {
        "entry_date": entry_date.strftime("%Y-%m-%d"),
        "entry_price": entry_price,
        "latest_close": latest_price,
        "latest_ret": (latest_price - entry_price) / entry_price * 100,
        "days_elapsed": len(future),
        "ret_5d": get_ret_at(5),
        "ret_10d": get_ret_at(10),
        "ret_15d": get_ret_at(15),
        "ret_20d": get_ret_at(20),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None,
                        help="起始日期 YYYY-MM-DD (預設：60 天前)")
    parser.add_argument("--end", default=None,
                        help="結束日期 YYYY-MM-DD (預設：今天)")
    parser.add_argument("--strategy", choices=["v1", "v2_F"], default="v2_F")
    parser.add_argument("--min-sources", type=int, default=2)
    parser.add_argument("--max-stocks", type=int, default=80)
    parser.add_argument("--save-json", default=None)
    parser.add_argument("--detail", action="store_true",
                        help="印出每筆交易的明細")
    args = parser.parse_args()

    # 預設區間：最近 60 天
    today = datetime.now().date()
    if not args.end:
        args.end = today.strftime("%Y-%m-%d")
    if not args.start:
        args.start = (today - timedelta(days=60)).strftime("%Y-%m-%d")

    log.info(f"區間：{args.start} ~ {args.end}")
    log.info(f"策略：{args.strategy}")

    # 1. 取得 universe
    universe = get_universe(verbose=False)
    universe = [u for u in universe if u["source_count"] >= args.min_sources]
    if args.max_stocks > 0:
        universe = universe[:args.max_stocks]
    log.info(f"股票池：{len(universe)} 檔")

    # 2. 抓加權指數（足夠涵蓋區間 + 60 天 MA60 buffer）
    log.info("抓加權指數...")
    market_df = fetch_twii(720)

    # 3. 並行掃描所有股票、找該區間所有訊號
    log.info("掃描中（找訊號）...")
    all_signals = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(find_signals_for_stock, u, market_df, args.start, args.end, args.strategy): u
            for u in universe
        }
        for fut in as_completed(futures):
            signals = fut.result()
            all_signals.extend(signals)

    if not all_signals:
        log.warning(f"區間內無任何訊號")
        return 0

    # 按日期排序
    all_signals.sort(key=lambda s: (s["signal_date"], s["code"]))
    log.info(f"找到 {len(all_signals)} 個訊號")

    # 4. 對每筆訊號算報酬
    log.info("計算報酬中...")
    today_ts = pd.Timestamp.today().normalize()

    # 為避免重抓資料，cache 每檔股票的完整 K 線
    stock_cache = {}

    def get_full_df(code):
        if code not in stock_cache:
            try:
                stock_cache[code] = fetch_yahoo(code, 720)
            except Exception:
                stock_cache[code] = None
        return stock_cache[code]

    enriched = []
    for sig in all_signals:
        full_df = get_full_df(sig["code"])
        if full_df is None or len(full_df) == 0:
            continue
        ret_data = calculate_returns(sig, full_df, today_ts)
        if ret_data:
            enriched.append({**sig, **ret_data})

    # 5. 印明細表
    if args.detail or len(enriched) <= 30:
        print()
        print("=" * 110)
        print(f"📊 訊號明細（{len(enriched)} 筆）")
        print("=" * 110)
        print(f"{'訊號日':<12}{'股票':<14}{'進場日':<12}{'進場價':<8}"
              f"{'5天%':<10}{'10天%':<10}{'15天%':<10}{'20天%':<10}{'迄今%':<10}")
        print("-" * 110)

        def fmt(r):
            if r is None:
                return "    -     "
            sign = "+" if r["ret"] >= 0 else ""
            return f"{sign}{r['ret']:>5.2f}%   "

        for s in enriched:
            stock_label = f"{s['code']} {s['name']}"
            latest_str = f"+{s['latest_ret']:.2f}%" if s['latest_ret'] >= 0 else f"{s['latest_ret']:.2f}%"
            print(f"{s['signal_date']:<12}{stock_label:<14}"
                  f"{s['entry_date']:<12}{s['entry_price']:>6.2f}  "
                  f"{fmt(s['ret_5d'])}{fmt(s['ret_10d'])}"
                  f"{fmt(s['ret_15d'])}{fmt(s['ret_20d'])}{latest_str:<10}")

    # 6. 彙總統計
    print()
    print("=" * 110)
    print("📈 彙總統計（不同持有期）")
    print("=" * 110)
    print(f"{'持有期':<10}{'樣本數':<10}{'勝率':<10}{'平均報酬':<14}"
          f"{'平均賺幅':<14}{'平均虧幅':<14}{'最佳':<12}{'最差':<12}{'回測預期':<12}")
    print("-" * 110)

    backtest_expected = {5: "+1.92%", 10: "+2.86%", 15: "(無)", 20: "+4.39%"}

    for n_days in [5, 10, 15, 20]:
        key = f"ret_{n_days}d"
        rets = [s[key]["ret"] for s in enriched if s.get(key) is not None]
        if not rets:
            print(f"{n_days} 天     {0:<10}尚無樣本")
            continue
        wins = [r for r in rets if r > 0]
        losses = [r for r in rets if r <= 0]
        win_rate = len(wins) / len(rets) * 100
        avg = sum(rets) / len(rets)
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        best = max(rets)
        worst = min(rets)
        expected = backtest_expected.get(n_days, "-")

        avg_str = f"{'+' if avg >= 0 else ''}{avg:.2f}%"
        win_str = f"+{avg_win:.2f}%" if avg_win else "-"
        loss_str = f"{avg_loss:.2f}%" if avg_loss else "-"
        print(f"{n_days} 天     {len(rets):<10}{win_rate:>5.0f}%    "
              f"{avg_str:<14}{win_str:<14}{loss_str:<14}"
              f"+{best:>5.2f}%    {worst:>+5.2f}%    {expected}")

    # 7. 各月份統計
    by_month = defaultdict(list)
    for s in enriched:
        if s.get("ret_10d"):  # 用 10 天當代表
            month = s["signal_date"][:7]  # YYYY-MM
            by_month[month].append(s["ret_10d"]["ret"])

    if len(by_month) > 1:
        print()
        print("=" * 110)
        print("📅 各月份表現（10 天持有）")
        print("=" * 110)
        print(f"{'月份':<10}{'樣本':<8}{'勝率':<10}{'平均':<10}{'最佳':<10}{'最差':<10}")
        print("-" * 60)
        for month in sorted(by_month.keys()):
            rets = by_month[month]
            wins = [r for r in rets if r > 0]
            wr = len(wins) / len(rets) * 100
            avg = sum(rets) / len(rets)
            print(f"{month:<10}{len(rets):<8}{wr:>5.0f}%    "
                  f"{'+' if avg >= 0 else ''}{avg:>5.2f}%   "
                  f"+{max(rets):>5.2f}%   "
                  f"{min(rets):>+5.2f}%")

    # 8. 各股票統計（重複觸發）
    by_code = defaultdict(list)
    for s in enriched:
        by_code[f"{s['code']} {s['name']}"].append(s)

    repeated = {k: v for k, v in by_code.items() if len(v) >= 2}
    if repeated:
        print()
        print("=" * 110)
        print("🔁 重複觸發股票（同一檔在區間內觸發 ≥ 2 次）")
        print("=" * 110)
        for stock_label, sigs in sorted(repeated.items(), key=lambda x: -len(x[1])):
            dates = [s["signal_date"] for s in sigs]
            print(f"  {stock_label}：{len(sigs)} 次（{', '.join(dates)})")

    # 9. 存 JSON
    if args.save_json:
        output = {
            "config": {
                "start": args.start, "end": args.end,
                "strategy": args.strategy,
            },
            "signal_count": len(enriched),
            "signals": enriched,
        }
        with open(args.save_json, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)
        log.info(f"\n✓ 結果存到 {args.save_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
