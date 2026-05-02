#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TSWE 多頭回檔買點策略 — 最小可行回測（單股測試版）

策略條件（同時滿足才觸發訊號）：
  ① 多頭結構：收盤 > MA60，且 MA20 > MA60
  ② MACD 深度負值：MACD 柱（OSC）落在過去 60 日的最低 25%
  ③ KD 低檔金叉：K 從 <30 區間穿越 D 向上

進場：訊號當天收盤後判定，「下個交易日」用開盤價買進
出場：N 天後（5/10/20 各測一次）的收盤價賣出

用法：
  python3 backtest_pullback_strategy.py 2330        # 測單一股票
  python3 backtest_pullback_strategy.py 2330 --days 365  # 測過去 365 天
  python3 backtest_pullback_strategy.py 2330 --plot      # 印 ASCII 訊號點

依賴：
  pip install pandas requests --break-system-packages
"""

import sys
import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

import requests
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 抓資料：用 Yahoo Finance（跟 TSWE 既有慣例一致）
# ═══════════════════════════════════════════════════════════
def fetch_yahoo(code: str, days: int = 365) -> pd.DataFrame:
    """抓單檔股票歷史 K 線。回傳 DataFrame，索引是日期"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{code}.TW"
    params = {"interval": "1d", "range": f"{days}d"}
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()

    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]

    df = pd.DataFrame({
        "date": pd.to_datetime(timestamps, unit='s').tz_localize('UTC').tz_convert('Asia/Taipei').date,
        "open": quote["open"],
        "high": quote["high"],
        "low": quote["low"],
        "close": quote["close"],
        "volume": quote["volume"],
    }).dropna()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df


def fetch_twii(days: int = 365) -> pd.DataFrame:
    """
    抓台股加權指數（^TWII）歷史資料。
    回傳 DataFrame 含 'close' 和 'ma60' 兩欄，索引是日期。
    用於判斷「大盤多頭環境」(close > ma60)。
    """
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII"
    params = {"interval": "1d", "range": f"{days}d"}
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()

    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]

    df = pd.DataFrame({
        "date": pd.to_datetime(timestamps, unit='s').tz_localize('UTC').tz_convert('Asia/Taipei').date,
        "close": quote["close"],
    }).dropna()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    # 計算 MA60 + 多頭判斷
    df["ma60"] = df["close"].rolling(60).mean()
    df["bullish"] = df["close"] > df["ma60"]
    return df


# ═══════════════════════════════════════════════════════════
# 技術指標計算
# ═══════════════════════════════════════════════════════════
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """計算 MA / MACD / KD"""
    # 均線
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()

    # MACD（標準參數 12, 26, 9）
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["dif"] = ema12 - ema26
    df["macd"] = df["dif"].ewm(span=9, adjust=False).mean()
    df["osc"] = df["dif"] - df["macd"]  # MACD 柱

    # KD（用簡化版 9 日 RSV、3 日平滑）
    low9 = df["low"].rolling(9).min()
    high9 = df["high"].rolling(9).max()
    rsv = (df["close"] - low9) / (high9 - low9) * 100

    # K 和 D 用遞迴平滑（傳統 Wilder 平滑、近似實作）
    k = pd.Series(index=df.index, dtype=float)
    d = pd.Series(index=df.index, dtype=float)
    k.iloc[0] = 50
    d.iloc[0] = 50
    for i in range(1, len(df)):
        rsv_i = rsv.iloc[i]
        if pd.isna(rsv_i):
            k.iloc[i] = k.iloc[i-1]
            d.iloc[i] = d.iloc[i-1]
        else:
            k.iloc[i] = (2/3) * k.iloc[i-1] + (1/3) * rsv_i
            d.iloc[i] = (2/3) * d.iloc[i-1] + (1/3) * k.iloc[i]
    df["k"] = k
    df["d"] = d

    return df


# ═══════════════════════════════════════════════════════════
# 訊號偵測
# ═══════════════════════════════════════════════════════════
def detect_signals(df: pd.DataFrame, osc_lookback: int = 60, osc_pct: float = 0.25,
                   k_threshold: float = 30,
                   require_recent_high: bool = False,
                   high_lookback: int = 240,
                   high_within_days: int = 30,
                   market_df=None,
                   strategy: str = "v1",
                   osc_within_days: int = 10,
                   osc_rebound_window: int = 5,
                   k_threshold_relaxed: float = 35,
                   k_within_days: int = 3) -> pd.DataFrame:
    """
    在 df 上加 'signal' 欄位（True/False）

    strategy='v1' (原版)：
      ① 多頭：close > ma60 且 ma20 > ma60
      ② MACD 柱深度負值：osc 處於過去 osc_lookback 日的最低 osc_pct 分位以下
      ③ KD 低檔金叉：昨日 K <= D 且今日 K > D，且今日 K < k_threshold

    strategy='v2_F' (F 版、貼近「綠柱縮小」直覺)：
      ① 多頭：同 v1
      ②a OSC 曾觸底：過去 osc_within_days 天內，OSC 曾達最低 osc_pct 分位
      ②b OSC 縮回：OSC[今日] > OSC[osc_rebound_window 天前] 且 OSC[今日] < 0
      ③ KD 金叉（放寬）：過去 k_within_days 天內發生金叉、且當日 K < k_threshold_relaxed

    可選的「真強勢股過濾」（require_recent_high=True 時）：
      ④ 最近 high_within_days 天內曾創 high_lookback 日新高

    可選的「大盤環境過濾」（傳入 market_df 時啟用）：
      ⑤ 訊號當天，台股加權指數 > 加權指數 MA60
    """
    # 條件 ①
    cond1 = (df["close"] > df["ma60"]) & (df["ma20"] > df["ma60"])
    df["cond1"] = cond1

    # 條件 ②：OSC 深度負值
    osc_threshold = df["osc"].rolling(osc_lookback).quantile(osc_pct)
    osc_at_deep = df["osc"] <= osc_threshold

    if strategy == "v2_F":
        # ②a 過去 10 天內曾觸底
        cond2a = osc_at_deep.rolling(osc_within_days).max().astype(bool)
        # ②b OSC 縮回（從谷底回來、但仍 < 0）
        osc_n_days_ago = df["osc"].shift(osc_rebound_window)
        cond2b = (df["osc"] > osc_n_days_ago) & (df["osc"] < 0)
        cond2 = cond2a & cond2b
        df["cond2a"] = cond2a
        df["cond2b"] = cond2b
    else:
        # v1: 當日 OSC 在最深
        cond2 = osc_at_deep
    df["cond2"] = cond2

    # 條件 ③：KD 金叉
    k_prev = df["k"].shift(1)
    d_prev = df["d"].shift(1)
    if strategy == "v2_F":
        # 過去 N 天內金叉、且當日 K < 35
        crossover = (k_prev <= d_prev) & (df["k"] > df["d"]) & (df["k"] < k_threshold_relaxed)
        cond3 = crossover.rolling(k_within_days).max().astype(bool) & (df["k"] < k_threshold_relaxed)
    else:
        # v1: 當日金叉、K < 30
        cond3 = (k_prev <= d_prev) & (df["k"] > df["d"]) & (df["k"] < k_threshold)
    df["cond3"] = cond3

    # 條件 ④（可選）：最近 N 天內有創 240 日新高
    if require_recent_high:
        rolling_max = df["high"].rolling(high_lookback).max()
        is_new_high = df["high"] >= rolling_max
        cond4 = is_new_high.rolling(high_within_days).max().astype(bool)
        df["cond4"] = cond4
    else:
        df["cond4"] = True

    # 條件 ⑤（可選）：大盤多頭環境
    if market_df is not None:
        market_bullish = market_df["bullish"].reindex(df.index, method='ffill')
        market_bullish = market_bullish.fillna(False)
        df["cond5"] = market_bullish
    else:
        df["cond5"] = True

    # 綜合
    df["signal"] = df["cond1"] & df["cond2"] & df["cond3"] & df["cond4"] & df["cond5"]
    return df


# ═══════════════════════════════════════════════════════════
# 回測：訊號 → 模擬進出場 → 計算報酬
# ═══════════════════════════════════════════════════════════
def backtest(df: pd.DataFrame, hold_days_list=(5, 10, 20)) -> dict:
    """
    對每個 signal=True 的日期：
      - 進場價 = 下一個交易日的 open
      - 出場價 = 進場後第 N 個交易日的 close
      - 計算報酬率
    """
    signals = df[df["signal"]].copy()
    if len(signals) == 0:
        return {"signal_count": 0, "results": {}}

    results = {}
    for hold_days in hold_days_list:
        trades = []
        for sig_date, _ in signals.iterrows():
            # 找下一個交易日的 open
            future = df[df.index > sig_date]
            if len(future) < hold_days + 1:
                continue
            entry = future.iloc[0]
            exit = future.iloc[hold_days]

            entry_price = entry["open"]
            exit_price = exit["close"]
            ret_pct = (exit_price - entry_price) / entry_price * 100

            trades.append({
                "signal_date": sig_date.strftime("%Y-%m-%d"),
                "entry_date": entry.name.strftime("%Y-%m-%d"),
                "entry_price": round(entry_price, 2),
                "exit_date": exit.name.strftime("%Y-%m-%d"),
                "exit_price": round(exit_price, 2),
                "return_pct": round(ret_pct, 2),
                "win": ret_pct > 0,
            })

        if trades:
            wins = [t for t in trades if t["win"]]
            losses = [t for t in trades if not t["win"]]
            win_rate = len(wins) / len(trades) * 100
            avg_return = sum(t["return_pct"] for t in trades) / len(trades)
            avg_win = sum(t["return_pct"] for t in wins) / len(wins) if wins else 0
            avg_loss = sum(t["return_pct"] for t in losses) / len(losses) if losses else 0
            best = max(t["return_pct"] for t in trades)
            worst = min(t["return_pct"] for t in trades)

            # 預期值（每筆交易的「平均報酬」）
            expected_value = avg_return

            results[f"hold_{hold_days}d"] = {
                "trade_count": len(trades),
                "win_rate": round(win_rate, 1),
                "avg_return": round(avg_return, 2),
                "avg_win": round(avg_win, 2),
                "avg_loss": round(avg_loss, 2),
                "best": round(best, 2),
                "worst": round(worst, 2),
                "expected_value": round(expected_value, 2),
                "trades": trades,
            }

    return {"signal_count": len(signals), "results": results}


# ═══════════════════════════════════════════════════════════
# 顯示報告
# ═══════════════════════════════════════════════════════════
def print_report(code: str, df: pd.DataFrame, result: dict):
    """印出人類可讀的報告"""
    print("=" * 72)
    print(f"📊 回測結果：{code}.TW")
    print(f"   資料區間：{df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}（{len(df)} 個交易日）")
    print(f"   訊號次數：{result['signal_count']}")
    print("=" * 72)

    if result["signal_count"] == 0:
        print("\n⚠️  此期間無訊號觸發。可考慮：")
        print("   - 拉長 --days 區間")
        print("   - 換一檔強勢股測試（譬如 1597 / 8103 / 6197）")
        print("   - 放寬條件（osc_pct 提高到 0.30）")
        return

    print()
    for hold_key, stats in result["results"].items():
        days = hold_key.replace("hold_", "").replace("d", "")
        print(f"📈 持有 {days} 天")
        print(f"   交易次數：{stats['trade_count']}")
        wins_count = sum(1 for t in stats['trades'] if t['win']) if 'trades' in stats else None
        losses_count = (stats['trade_count'] - wins_count) if wins_count is not None else None
        if wins_count is not None:
            print(f"   勝率：{stats['win_rate']}%（贏 {wins_count} / 輸 {losses_count}）")
        else:
            print(f"   勝率：{stats['win_rate']}%（共 {stats['trade_count']} 筆）")
        print(f"   平均報酬：{stats['avg_return']:+.2f}%")
        print(f"   平均賺幅：+{stats['avg_win']:.2f}% / 平均虧幅：{stats['avg_loss']:.2f}%")
        print(f"   最佳：+{stats['best']:.2f}% / 最差：{stats['worst']:.2f}%")
        print(f"   預期值：{stats['expected_value']:+.2f}%（每筆平均）")

        # 賠率分析
        if stats['avg_loss'] != 0:
            ratio = abs(stats['avg_win'] / stats['avg_loss'])
            print(f"   賺賠比：{ratio:.2f} : 1")
        print()


def print_signals_detail(result: dict, hold_days: int = 10):
    """印出訊號詳細列表"""
    key = f"hold_{hold_days}d"
    if key not in result.get("results", {}):
        return

    print(f"📋 {hold_days} 天持有的訊號詳細列表：")
    print(f"{'訊號日':<12} {'進場日':<12} {'進場價':>8} {'出場日':<12} {'出場價':>8} {'報酬':>8}  結果")
    print("-" * 72)
    for t in result["results"][key]["trades"]:
        marker = "✓" if t["win"] else "✗"
        ret_str = f"{t['return_pct']:+.2f}%"
        print(f"{t['signal_date']:<12} {t['entry_date']:<12} {t['entry_price']:>8.2f} "
              f"{t['exit_date']:<12} {t['exit_price']:>8.2f} {ret_str:>8}  {marker}")
    print()


# ═══════════════════════════════════════════════════════════
# 主程式
# ═══════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="多頭回檔買點策略 — 單股回測")
    parser.add_argument("code", help="股票代號（譬如 2330、1597）")
    parser.add_argument("--days", type=int, default=365, help="回測天數（預設 365）")
    parser.add_argument("--osc-pct", type=float, default=0.25,
                        help="MACD 柱深度分位（預設 0.25 = 過去最深 25%）")
    parser.add_argument("--k-threshold", type=float, default=30,
                        help="KD 金叉時 K 值上限（預設 30）")
    parser.add_argument("--require-high", action="store_true",
                        help="啟用「真強勢股過濾」：只在最近曾創 240 日新高的股票上找訊號")
    parser.add_argument("--high-lookback", type=int, default=240,
                        help="新高的回看天數（預設 240，配合 --require-high 用）")
    parser.add_argument("--high-within", type=int, default=30,
                        help="新高發生在過去 N 天內才算（預設 30，配合 --require-high 用）")
    parser.add_argument("--market-filter", action="store_true",
                        help="啟用「大盤過濾」：台股加權 > MA60 才採用訊號")
    parser.add_argument("--strategy", choices=["v1", "v2_F"], default="v1",
                        help="策略版本：v1 (原版、抓 OSC 最深點) "
                             "或 v2_F (F 版、抓 OSC 縮回確認、貼近「綠柱縮小」直覺)")
    parser.add_argument("--detail", action="store_true", help="印出每筆交易")
    parser.add_argument("--save-json", help="存結果到指定 JSON 路徑")
    args = parser.parse_args()

    log.info(f"抓 {args.code}.TW 過去 {args.days} 天資料...")
    df = fetch_yahoo(args.code, args.days)
    if len(df) < 80:
        log.error(f"資料太少（{len(df)} 天），需要至少 80 天")
        return 1

    log.info("計算技術指標...")
    df = add_indicators(df)

    # 抓加權指數（如果啟用大盤過濾）
    market_df = None
    if args.market_filter:
        log.info("抓台股加權指數（^TWII）...")
        market_df = fetch_twii(args.days)
        log.info(f"加權 MA60 多頭天數：{market_df['bullish'].sum()}/{len(market_df)} 天")

    log.info("偵測訊號...")
    df = detect_signals(
        df,
        osc_pct=args.osc_pct,
        k_threshold=args.k_threshold,
        require_recent_high=args.require_high,
        high_lookback=args.high_lookback,
        high_within_days=args.high_within,
        market_df=market_df,
        strategy=args.strategy,
    )
    log.info(f"使用策略：{args.strategy}")
    if args.require_high:
        log.info(f"啟用「最近 {args.high_within} 天內曾創 {args.high_lookback} 日新高」過濾")
    if args.market_filter:
        log.info("啟用「大盤過濾」（加權 > MA60 才採用訊號）")

    log.info("跑回測...")
    result = backtest(df)

    print_report(args.code, df, result)

    if args.detail and result["signal_count"] > 0:
        print_signals_detail(result, hold_days=10)

    if args.save_json:
        with open(args.save_json, 'w', encoding='utf-8') as f:
            json.dump({
                "code": args.code,
                "days": args.days,
                "config": {
                    "osc_pct": args.osc_pct,
                    "k_threshold": args.k_threshold,
                },
                "data_range": [
                    df.index[0].strftime("%Y-%m-%d"),
                    df.index[-1].strftime("%Y-%m-%d"),
                ],
                "result": result,
            }, f, ensure_ascii=False, indent=2)
        log.info(f"✓ 結果已存到 {args.save_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
