#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TSWE 訊號診斷工具

兩個診斷模式：

1. 條件分解：對指定日期，看每個條件分別有幾檔股票通過
   python3 pullback_signal_diagnose.py decompose --date 2026-04-30

2. 跨日掃描：看過去 N 天每天的訊號數變化
   python3 pullback_signal_diagnose.py scan --days-back 14
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_pullback_strategy import (
    fetch_yahoo, fetch_twii, add_indicators, detect_signals
)
from stock_universe import get_universe

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger(__name__)


def diagnose_one_stock(stock: dict, market_df, as_of: str, strategy: str = "v2_F"):
    """對單檔股票、回傳每個條件是否通過"""
    code = stock["code"]
    name = stock.get("name", "")
    try:
        df = fetch_yahoo(code, 365)
        if len(df) < 80:
            return None
        df = add_indicators(df)
        df = detect_signals(
            df,
            require_recent_high=True,
            high_lookback=240,
            high_within_days=30,
            market_df=market_df,
            strategy=strategy,
        )

        if as_of:
            as_of_ts = pd.to_datetime(as_of)
            df = df[df.index <= as_of_ts]
            if len(df) == 0:
                return None

        last = df.iloc[-1]
        result = {
            "code": code,
            "name": name,
            "close": float(last["close"]),
            "cond1": bool(last["cond1"]),
            "cond2": bool(last["cond2"]),
            "cond3": bool(last["cond3"]),
            "cond4": bool(last["cond4"]),
            "cond5": bool(last["cond5"]),
            "signal": bool(last["signal"]),
            "osc": float(last["osc"]),
            "k": float(last["k"]),
        }
        # F 版才有 cond2a / cond2b
        if "cond2a" in last:
            result["cond2a"] = bool(last["cond2a"])
            result["cond2b"] = bool(last["cond2b"])
        return result
    except Exception as e:
        return None


def cmd_decompose(args):
    """模式 1：條件分解"""
    log.info(f"診斷日期：{args.date}")
    log.info(f"策略：{args.strategy}")

    universe = get_universe(verbose=False)
    universe = [u for u in universe if u["source_count"] >= args.min_sources]
    if args.max_stocks > 0:
        universe = universe[:args.max_stocks]
    log.info(f"掃描股票：{len(universe)} 檔")

    log.info("抓加權指數...")
    market_df_full = fetch_twii(180)
    as_of_ts = pd.to_datetime(args.date)
    market_df = market_df_full[market_df_full.index <= as_of_ts]
    if len(market_df) == 0:
        log.error("資料不足")
        return 1
    last_market = market_df.iloc[-1]
    log.info(f"加權 {last_market['close']:.0f}、MA60 {last_market['ma60']:.0f}、"
             f"{'多頭' if last_market['bullish'] else '空頭'}")

    log.info("並行診斷中...")
    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(diagnose_one_stock, u, market_df, args.date, args.strategy): u
            for u in universe
        }
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                results.append(r)

    if not results:
        log.error("沒有可分析的資料")
        return 1

    # 統計
    print()
    print("=" * 70)
    print(f"📊 條件通過統計（{len(results)} 檔有資料）")
    print("=" * 70)

    total = len(results)
    cond_stats = {
        "cond1 (多頭結構)": sum(1 for r in results if r.get("cond1")),
        "cond2 (MACD 條件)": sum(1 for r in results if r.get("cond2")),
        "cond3 (KD 金叉)": sum(1 for r in results if r.get("cond3")),
        "cond4 (240 日新高)": sum(1 for r in results if r.get("cond4")),
        "cond5 (大盤多頭)": sum(1 for r in results if r.get("cond5")),
        "★ 全部通過 (signal)": sum(1 for r in results if r.get("signal")),
    }

    if "cond2a" in results[0]:
        cond_stats[" └ cond2a (10天內觸底)"] = sum(1 for r in results if r.get("cond2a"))
        cond_stats[" └ cond2b (OSC 縮回)"] = sum(1 for r in results if r.get("cond2b"))

    print(f"\n{'條件':<25}{'通過數':>10}{'通過率':>12}")
    print("-" * 50)
    for label, count in cond_stats.items():
        pct = count / total * 100
        bar = "█" * int(pct / 4)
        print(f"{label:<25}{count:>4}/{total}{pct:>9.1f}%  {bar}")

    # 最接近觸發的股票（cond1 + cond4 + cond5 都過、只差 cond2/cond3）
    print()
    print("=" * 70)
    print("🎯 最接近觸發的股票（多頭結構、新高、大盤都過、只差 MACD/KD）")
    print("=" * 70)

    near_signals = [
        r for r in results
        if r.get("cond1") and r.get("cond4") and r.get("cond5")
        and not r.get("signal")
    ]
    print(f"\n共 {len(near_signals)} 檔達到「半符合」狀態（cond1 + cond4 + cond5）")

    if near_signals:
        print(f"\n{'代號':<8}{'名稱':<10}{'收盤':>8}{'OSC':>8}{'K':>6} 缺")
        print("-" * 60)
        for r in near_signals[:20]:
            missing = []
            if not r.get("cond2"):
                missing.append("MACD")
            if not r.get("cond3"):
                missing.append("KD")
            print(f"{r['code']:<8}{r['name']:<10}"
                  f"{r['close']:>8.2f}"
                  f"{r['osc']:>+8.3f}"
                  f"{r['k']:>6.0f}"
                  f"  缺：{', '.join(missing)}")

    return 0


def cmd_scan(args):
    """模式 2：跨日掃描"""
    log.info(f"跨日掃描：過去 {args.days_back} 天的訊號數變化")

    universe = get_universe(verbose=False)
    universe = [u for u in universe if u["source_count"] >= args.min_sources]
    if args.max_stocks > 0:
        universe = universe[:args.max_stocks]
    log.info(f"掃描股票：{len(universe)} 檔、策略：{args.strategy}")

    market_df_full = fetch_twii(args.days_back + 90)

    # 產生日期列表（過去 N 天）
    today = datetime.now().date() if not args.until else pd.to_datetime(args.until).date()
    dates = []
    for i in range(args.days_back):
        d = today - timedelta(days=i)
        if d.weekday() < 5:  # 跳過週末
            dates.append(d.strftime("%Y-%m-%d"))
    dates.sort()

    log.info(f"日期範圍：{dates[0]} ~ {dates[-1]}（{len(dates)} 個交易日）")

    print()
    print(f"{'日期':<12}{'加權':>8}{'多頭':>6}{'訊號數':>8}")
    print("-" * 40)

    for date_str in dates:
        as_of_ts = pd.to_datetime(date_str)
        market_df = market_df_full[market_df_full.index <= as_of_ts]
        if len(market_df) == 0:
            continue
        last_market = market_df.iloc[-1]

        # 同 date_str 確認
        if last_market.name.strftime("%Y-%m-%d") != date_str:
            continue  # 該日無交易資料（可能是假日）

        # 計算當日訊號數
        signal_count = 0
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = {
                ex.submit(diagnose_one_stock, u, market_df, date_str, args.strategy): u
                for u in universe
            }
            for fut in as_completed(futures):
                r = fut.result()
                if r and r.get("signal"):
                    signal_count += 1

        bull = "✓" if last_market["bullish"] else "✗"
        bar = "█" * signal_count
        print(f"{date_str:<12}{last_market['close']:>8.0f}{bull:>6}{signal_count:>8}  {bar}")

    return 0


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("decompose", help="條件分解")
    p1.add_argument("--date", required=True, help="YYYY-MM-DD")
    p1.add_argument("--strategy", choices=["v1", "v2_F"], default="v2_F")
    p1.add_argument("--min-sources", type=int, default=2)
    p1.add_argument("--max-stocks", type=int, default=80)

    p2 = sub.add_parser("scan", help="跨日掃描")
    p2.add_argument("--days-back", type=int, default=14, help="往前看幾天（含週末）")
    p2.add_argument("--until", help="截止日 YYYY-MM-DD（預設今天）")
    p2.add_argument("--strategy", choices=["v1", "v2_F"], default="v2_F")
    p2.add_argument("--min-sources", type=int, default=2)
    p2.add_argument("--max-stocks", type=int, default=80)

    args = parser.parse_args()

    if args.cmd == "decompose":
        return cmd_decompose(args)
    elif args.cmd == "scan":
        return cmd_scan(args)


if __name__ == "__main__":
    sys.exit(main())
