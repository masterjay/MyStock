#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TSWE 多頭回檔買點策略 — 批次回測（多檔彙總）

對多檔股票一次跑完，彙總勝率與預期值。
比逐檔執行快很多（並行抓資料），且會直接給你「整體統計」。

用法：
  # 用內建的「強勢股清單」
  python3 backtest_batch.py

  # 自訂股票清單
  python3 backtest_batch.py --codes 1597,8103,6197,3605

  # 用 new_high_stocks.json 當清單（最近的新高股）
  python3 backtest_batch.py --from-newhigh

  # 改參數
  python3 backtest_batch.py --days 365 --osc-pct 0.20 --k-threshold 25

  # 存結果
  python3 backtest_batch.py --save-json results.json
"""

import sys
import argparse
import json
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# 從同目錄的 backtest_pullback_strategy 匯入函數
sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_pullback_strategy import (
    fetch_yahoo, fetch_twii, add_indicators, detect_signals, backtest
)

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger(__name__)


# 預設測試清單（你最近名單裡的強勢股 + 大型股對照）
DEFAULT_CODES = [
    # 強勢股（你最近名單）
    "1597", "8103", "6197", "3605", "2464",
    "8086", "6271", "2426", "3016",
    # 大型股對照
    "2330", "2317", "2454",
]


import time
import random


def run_one(code: str, days: int, osc_pct: float, k_threshold: float,
            require_recent_high: bool = False,
            high_lookback: int = 240,
            high_within_days: int = 30,
            market_df=None,
            strategy: str = "v1",
            jitter_max: float = 0.5) -> dict:
    """跑單檔回測，回傳精簡結果

    jitter_max: 隨機延遲上限秒數，避免 Yahoo 限速（並行多時）
    strategy: 'v1' 原版 / 'v2_F' F 版（OSC 縮回確認）
    """
    # 隨機微延遲（避免 4 條同時打 API）
    if jitter_max > 0:
        time.sleep(random.uniform(0, jitter_max))

    try:
        df = fetch_yahoo(code, days)
        if len(df) < 80:
            return {"code": code, "error": f"資料不足 ({len(df)} 天)"}
        df = add_indicators(df)
        df = detect_signals(df, osc_pct=osc_pct, k_threshold=k_threshold,
                           require_recent_high=require_recent_high,
                           high_lookback=high_lookback,
                           high_within_days=high_within_days,
                           market_df=market_df,
                           strategy=strategy)
        result = backtest(df)

        # 抽出簡明摘要
        summary = {"code": code, "signal_count": result["signal_count"]}
        for hold_key, stats in result.get("results", {}).items():
            wins = sum(1 for t in stats['trades'] if t['win'])
            summary[hold_key] = {
                "trades": stats['trade_count'],
                "wins": wins,
                "losses": stats['trade_count'] - wins,
                "win_rate": stats['win_rate'],
                "avg_return": stats['avg_return'],
                "avg_win": stats['avg_win'],
                "avg_loss": stats['avg_loss'],
                "expected_value": stats['expected_value'],
            }
        # 保留每筆交易做明細
        summary["_full_results"] = result.get("results", {})
        return summary
    except Exception as e:
        return {"code": code, "error": str(e)}


def aggregate_split(results: list, hold_days: int, split_ratio: float = 0.667) -> dict:
    """
    把所有訊號按「日期」切兩段：訓練期（前 split_ratio）和驗證期（後 1 - split_ratio）
    分別統計，回傳 {"train": {...}, "validate": {...}, "split_date": "YYYY-MM-DD"}
    """
    key = f"hold_{hold_days}d"

    # 先收集所有訊號的日期
    all_trades = []
    for r in results:
        if "error" in r or "_full_results" not in r:
            continue
        if key not in r["_full_results"]:
            continue
        for t in r["_full_results"][key].get("trades", []):
            all_trades.append({**t, "code": r["code"]})

    if len(all_trades) < 10:
        return {"trades": 0, "train": None, "validate": None}

    # 按 entry_date 排序
    all_trades.sort(key=lambda t: t["entry_date"])

    # 切點
    split_idx = int(len(all_trades) * split_ratio)
    train_trades = all_trades[:split_idx]
    validate_trades = all_trades[split_idx:]
    split_date = train_trades[-1]["entry_date"] if train_trades else "N/A"

    def _stats(trades):
        if not trades:
            return None
        wins = [t for t in trades if t["win"]]
        losses = [t for t in trades if not t["win"]]
        win_rate = len(wins) / len(trades) * 100
        avg_return = sum(t["return_pct"] for t in trades) / len(trades)
        avg_win = sum(t["return_pct"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["return_pct"] for t in losses) / len(losses) if losses else 0
        payoff = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
        return {
            "trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 1),
            "avg_return": round(avg_return, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "payoff_ratio": round(payoff, 2),
            "best": round(max(t["return_pct"] for t in trades), 2),
            "worst": round(min(t["return_pct"] for t in trades), 2),
            "date_range": [trades[0]["entry_date"], trades[-1]["entry_date"]],
        }

    return {
        "trades": len(all_trades),
        "split_date": split_date,
        "split_idx": split_idx,
        "train": _stats(train_trades),
        "validate": _stats(validate_trades),
    }


def print_split_validate(results: list, split_ratio: float = 0.667):
    """印出訓練期 vs 驗證期的對照表"""
    print()
    print("═" * 84)
    print("🔬 訓練期 / 驗證期 對照")
    print("═" * 84)

    for hold_days in [10, 20]:
        sp = aggregate_split(results, hold_days, split_ratio)
        if sp["trades"] == 0 or not sp["train"] or not sp["validate"]:
            print(f"\n持有 {hold_days} 天：訊號太少（< 10 筆）無法做切割驗證")
            continue

        t = sp["train"]
        v = sp["validate"]

        # 計算差距
        wr_diff = v["win_rate"] - t["win_rate"]  # 正 = 驗證更好
        ev_diff = v["avg_return"] - t["avg_return"]

        # 判斷
        if abs(wr_diff) < 5 and abs(ev_diff) < 1:
            verdict = "✅ 穩健"
            verdict_msg = "訓練期與驗證期表現一致，策略真的有效"
        elif wr_diff < -10 or ev_diff < -2:
            verdict = "❌ 嚴重衰減"
            verdict_msg = "驗證期勝率/預期值大幅下降，可能過擬合"
        elif wr_diff < -5 or ev_diff < -1:
            verdict = "⚠️ 輕度衰減"
            verdict_msg = "驗證期略差但仍可接受"
        elif wr_diff > 5:
            verdict = "🤔 反向"
            verdict_msg = "驗證期反而更好，可能驗證期市場特別有利"
        else:
            verdict = "✅ 穩定"
            verdict_msg = "兩期表現相近，可信度高"

        print(f"\n持有 {hold_days} 天 — {verdict}")
        print(f"   切點：第 {sp['split_idx']} 筆訊號（{sp['split_date']}）")
        print()
        print(f"   {'指標':<14}{'訓練期':>14}{'驗證期':>14}{'差距':>14}")
        print(f"   {'─' * 56}")
        print(f"   {'樣本數':<14}{t['trades']:>14}{v['trades']:>14}{'':>14}")
        print(f"   {'日期範圍':<10}  {t['date_range'][0]} → {t['date_range'][1][:7]}    "
              f"{v['date_range'][0]} → {v['date_range'][1][:7]}")
        print(f"   {'勝率':<14}{t['win_rate']:>13.1f}%{v['win_rate']:>13.1f}%{wr_diff:>+13.1f}%")
        print(f"   {'平均報酬':<13}{t['avg_return']:>+12.2f}%{v['avg_return']:>+13.2f}%{ev_diff:>+13.2f}%")
        print(f"   {'平均賺幅':<13}{t['avg_win']:>+12.2f}%{v['avg_win']:>+13.2f}%")
        print(f"   {'平均虧幅':<13}{t['avg_loss']:>+12.2f}%{v['avg_loss']:>+13.2f}%")
        print(f"   {'賺賠比':<14}{t['payoff_ratio']:>13}:1{v['payoff_ratio']:>13}:1")
        print(f"   {'最佳/最差':<10}  +{t['best']:>5.1f}%/{t['worst']:>5.1f}%   "
              f"+{v['best']:>5.1f}%/{v['worst']:>5.1f}%")
        print()
        print(f"   📋 {verdict_msg}")

    print()
    print("═" * 84)
    print("🧭 切割驗證結論")
    print("═" * 84)
    sp20 = aggregate_split(results, 20, split_ratio)
    if sp20["trades"] == 0 or not sp20["train"] or not sp20["validate"]:
        print("⚠️ 訊號不足、無法給結論")
        return

    v_wr = sp20["validate"]["win_rate"]
    v_ev = sp20["validate"]["avg_return"]
    t_wr = sp20["train"]["win_rate"]
    wr_diff = v_wr - t_wr

    if v_ev > 1.5 and abs(wr_diff) < 10:
        print(f"✅ 通過驗證！驗證期 20 天版本：勝率 {v_wr}%、預期值 {v_ev:+.2f}%")
        print("   策略真的可用，可以開始做 dashboard 區塊")
    elif v_ev > 0 and wr_diff > -10:
        print(f"⚠️ 邊際通過：驗證期 20 天版本：勝率 {v_wr}%、預期值 {v_ev:+.2f}%")
        print("   策略可能有效但要小心，建議實戰小額試水溫")
    else:
        print(f"❌ 驗證未通過：驗證期 20 天版本：勝率 {v_wr}%、預期值 {v_ev:+.2f}%")
        print(f"   訓練期勝率 {t_wr}%、衰減 {wr_diff:.1f}%、過擬合風險高")
        print("   建議：重新調整條件或不要上線")


def aggregate(results: list, hold_days: int) -> dict:
    """跨多檔彙總指定持有天數的統計"""
    key = f"hold_{hold_days}d"
    all_trades = []
    for r in results:
        if "error" in r or key not in r:
            continue
        # 從 _full_results 拿原始 trades（含 return_pct）
        if "_full_results" in r and key in r["_full_results"]:
            for t in r["_full_results"][key].get("trades", []):
                all_trades.append({**t, "code": r["code"]})

    if not all_trades:
        return {"trades": 0}

    wins = [t for t in all_trades if t["win"]]
    losses = [t for t in all_trades if not t["win"]]
    win_rate = len(wins) / len(all_trades) * 100
    avg_return = sum(t["return_pct"] for t in all_trades) / len(all_trades)
    avg_win = sum(t["return_pct"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["return_pct"] for t in losses) / len(losses) if losses else 0

    # 賠率（取絕對值）
    payoff_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')

    # 凱利公式（理論最佳下注比例）
    p = win_rate / 100
    if avg_loss != 0:
        b = abs(avg_win / avg_loss)
        kelly = max(0, (p * (b + 1) - 1) / b) * 100
    else:
        kelly = 0

    return {
        "trades": len(all_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "avg_return": round(avg_return, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "payoff_ratio": round(payoff_ratio, 2),
        "expected_value": round(avg_return, 2),  # 同 avg_return
        "kelly_pct": round(kelly, 1),
        "best_trade": max(t["return_pct"] for t in all_trades),
        "worst_trade": min(t["return_pct"] for t in all_trades),
    }


def print_per_stock(results: list, max_rows: int = 30):
    """印出每檔股票的明細表。max_rows 限制顯示筆數，避免大樣本時塞爆畫面"""
    print()
    print("═" * 84)
    print("📊 各檔明細（10 天持有）")
    print("═" * 84)

    # 篩出「有訊號」或「錯誤」的，無訊號的不印
    visible = []
    skipped_silent = 0
    for r in sorted(results, key=lambda x: x.get("code", "")):
        if "error" in r:
            visible.append(r)
        elif r.get("signal_count", 0) > 0:
            visible.append(r)
        else:
            skipped_silent += 1

    if len(visible) > max_rows:
        print(f"（共 {len(visible)} 檔有訊號或錯誤、{skipped_silent} 檔無訊號跳過。"
              f"明細只顯示前 {max_rows} 檔，完整資料用 --save-json）\n")
    else:
        print(f"（顯示 {len(visible)} 檔有訊號或錯誤、{skipped_silent} 檔無訊號跳過）\n")

    print(f"{'代號':<8}{'訊號':>6}{'勝率':>10}{'平均':>10}{'最佳':>10}{'最差':>10}  賺賠")
    print("─" * 84)

    for r in visible[:max_rows]:
        if "error" in r:
            print(f"{r['code']:<8}  ⚠️  {r['error'][:60]}")
            continue

        stats = r.get("hold_10d")
        if not stats:
            continue

        best = max(t['return_pct'] for t in r["_full_results"]["hold_10d"]["trades"])
        worst = min(t['return_pct'] for t in r["_full_results"]["hold_10d"]["trades"])
        ratio = abs(stats['avg_win'] / stats['avg_loss']) if stats['avg_loss'] != 0 else float('inf')

        wr_str = f"{stats['win_rate']:.0f}%"
        ev_str = f"{stats['expected_value']:+.2f}%"
        marker = "✓" if stats['expected_value'] > 0 else " "

        print(f"{r['code']:<8}"
              f"{stats['trades']:>6}"
              f"{wr_str:>10}"
              f"{ev_str:>10}"
              f"{best:>+9.2f}%"
              f"{worst:>+9.2f}%"
              f"  {ratio:>4.2f}:1 {marker}")


def print_aggregate(results: list):
    """印出整體彙總"""
    print()
    print("═" * 84)
    print("📈 整體彙總（跨所有股票）")
    print("═" * 84)

    for hold_days in [5, 10, 20]:
        agg = aggregate(results, hold_days)
        if agg["trades"] == 0:
            print(f"\n持有 {hold_days} 天：無訊號")
            continue

        # 結論
        if agg["expected_value"] > 1:
            verdict = "✅ 正預期值"
        elif agg["expected_value"] > -0.5:
            verdict = "⚠️ 接近隨機"
        else:
            verdict = "❌ 負預期值"

        print(f"\n持有 {hold_days} 天 — {verdict}")
        print(f"  總交易：{agg['trades']} 筆（贏 {agg['wins']} / 輸 {agg['losses']}）")
        print(f"  勝率：{agg['win_rate']}%")
        print(f"  平均報酬：{agg['avg_return']:+.2f}%")
        print(f"  平均賺幅：+{agg['avg_win']:.2f}% / 平均虧幅：{agg['avg_loss']:.2f}%")
        print(f"  賺賠比：{agg['payoff_ratio']}:1")
        print(f"  最佳/最差：+{agg['best_trade']:.2f}% / {agg['worst_trade']:.2f}%")
        print(f"  預期值：{agg['expected_value']:+.2f}% 每筆")
        if agg['kelly_pct'] > 0:
            print(f"  凱利建議下注：{agg['kelly_pct']}%（資金的 {agg['kelly_pct']}% / 筆）")


def print_judgement(results: list):
    """給結論建議"""
    print()
    print("═" * 84)
    print("🧭 判斷建議")
    print("═" * 84)

    agg10 = aggregate(results, 10)
    if agg10["trades"] == 0:
        print("⚠️ 完全沒有訊號觸發。建議：")
        print("   1. 檢查條件是否太嚴")
        print("   2. 試 --osc-pct 0.30（放寬深度負值定義）")
        print("   3. 試 --k-threshold 35（放寬金叉時 K 值上限）")
        return

    samples = agg10["trades"]
    win_rate = agg10["win_rate"]
    ev = agg10["expected_value"]

    # 樣本量判斷
    if samples < 10:
        print(f"⚠️ 樣本量太少（{samples} 筆）— 不能下定論")
        print("   建議拉長 --days 1095（3 年）或加入更多股票")
    elif samples < 30:
        print(f"⚠️ 樣本量偏少（{samples} 筆）— 結論僅供參考")
    else:
        print(f"✓ 樣本量足夠（{samples} 筆）")

    # 預期值判斷
    print()
    if ev > 1.5:
        print(f"✅ 預期值 +{ev:.2f}% 良好 — 策略似乎有效")
        print("   建議下一步：")
        print("   - 切「訓練期 / 驗證期」確認非過擬合")
        print("   - 加籌碼面條件（外資投信買超）看能否提升")
        print("   - 開始做成 dashboard 區塊")
    elif ev > 0.5:
        print(f"⚠️ 預期值 +{ev:.2f}% 微正 — 邊際有效，扣手續費後可能不賺")
        print("   建議下一步：")
        print("   - 嘗試調整參數（osc-pct、k-threshold）")
        print("   - 加過濾條件：大盤環境、籌碼、產業類股")
    elif ev > -0.5:
        print(f"⚠️ 預期值 {ev:+.2f}% 接近零 — 跟隨機差不多")
        print("   建議下一步：")
        print("   - 條件可能定義錯了，重新思考「短線急跌」的量化")
        print("   - 試試只在「外資投信同步買超」時才採用本策略")
    else:
        print(f"❌ 預期值 {ev:+.2f}% 明顯負 — 此策略以目前條件無效")
        print("   可能原因：")
        print("   - 「MACD 60 日最深 25%」抓到的不是回檔、是真的轉弱")
        print("   - 缺少趨勢延續性過濾（譬如進場前要紅 K 確認）")
        print("   建議：要不要繼續調整、或改試其他策略？")


# ═══════════════════════════════════════════════════════════
# 主程式
# ═══════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="多檔批次回測 — 強勢股回檔買點策略")
    parser.add_argument("--codes", help="逗號分隔的股票代號（譬如 1597,8103,6197）")
    parser.add_argument("--from-newhigh", action="store_true",
                        help="使用 data/new_high_stocks.json 的清單")
    parser.add_argument("--from-universe", action="store_true",
                        help="從本地多個資料源聯集（推薦：可達 100-200 檔做大樣本驗證）")
    parser.add_argument("--min-sources", type=int, default=1,
                        help="--from-universe 時，至少出現在 N 個來源才採用（預設 1）")
    parser.add_argument("--max-codes", type=int, default=0,
                        help="只取前 N 檔（從 universe 拿出來時用，0=全部）")
    parser.add_argument("--days", type=int, default=365, help="回測天數（預設 365）")
    parser.add_argument("--osc-pct", type=float, default=0.25,
                        help="MACD 柱深度分位（預設 0.25）")
    parser.add_argument("--k-threshold", type=float, default=30,
                        help="KD 金叉時 K 值上限（預設 30）")
    parser.add_argument("--require-high", action="store_true",
                        help="啟用「真強勢股過濾」：只在最近曾創 240 日新高的股票上找訊號")
    parser.add_argument("--high-lookback", type=int, default=240,
                        help="新高的回看天數（預設 240）")
    parser.add_argument("--high-within", type=int, default=30,
                        help="新高發生在過去 N 天內才算（預設 30）")
    parser.add_argument("--market-filter", action="store_true",
                        help="啟用「大盤過濾」：台股加權 > MA60 才採用訊號")
    parser.add_argument("--strategy", choices=["v1", "v2_F"], default="v1",
                        help="策略版本：v1 (原版) 或 v2_F (F 版、抓綠柱縮小)")
    parser.add_argument("--split-validate", action="store_true",
                        help="切「訓練期/驗證期」對照（前 2/3 訓練、後 1/3 驗證）")
    parser.add_argument("--split-ratio", type=float, default=0.667,
                        help="訓練期佔比（預設 0.667 = 2/3 訓練、1/3 驗證）")
    parser.add_argument("--save-json", help="存結果到 JSON")
    parser.add_argument("--workers", type=int, default=4, help="並行抓資料數（預設 4）")
    args = parser.parse_args()

    # 1. 決定股票清單
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    elif args.from_universe:
        try:
            from stock_universe import get_universe
        except ImportError:
            log.error("找不到 stock_universe.py，請確認檔案在 backend 目錄")
            return 1
        universe = get_universe(verbose=True)
        universe = [u for u in universe if u["source_count"] >= args.min_sources]
        if args.max_codes > 0:
            universe = universe[:args.max_codes]
        codes = [u["code"] for u in universe]
        log.info(f"從 universe 取出 {len(codes)} 檔（min-sources={args.min_sources}）")
    elif args.from_newhigh:
        nh_file = Path(__file__).resolve().parent / "data" / "new_high_stocks.json"
        if not nh_file.exists():
            log.error(f"找不到 {nh_file}")
            return 1
        with open(nh_file, encoding='utf-8') as f:
            data = json.load(f)
        # 只取強度 >= 4 的，避免太多
        codes = [s["code"] for s in data.get("stocks", []) if s.get("strength", 0) >= 4]
        log.info(f"從 new_high_stocks.json 取強度>=4 的：{len(codes)} 檔")
    else:
        codes = DEFAULT_CODES
        log.info(f"使用預設清單（{len(codes)} 檔）")

    if not codes:
        log.error("股票清單是空的")
        return 1

    # 2. 並行跑回測
    log.info(f"批次回測 {len(codes)} 檔，並行 {args.workers}（預估 {len(codes) // args.workers + 1}~{len(codes) // args.workers + 3} 秒）...")
    log.info(f"使用策略：{args.strategy}")
    if args.require_high:
        log.info(f"啟用「最近 {args.high_within} 天內曾創 {args.high_lookback} 日新高」過濾")

    # 抓加權指數一次（所有股票共用）
    market_df = None
    if args.market_filter:
        log.info("抓台股加權指數（^TWII）...")
        try:
            market_df = fetch_twii(args.days)
            log.info(f"啟用「大盤過濾」：加權多頭天數 {market_df['bullish'].sum()}/{len(market_df)}（{market_df['bullish'].mean()*100:.0f}%）")
        except Exception as e:
            log.error(f"抓加權失敗，停用大盤過濾：{e}")
            market_df = None

    results = []
    completed = 0
    total = len(codes)
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(run_one, code, args.days, args.osc_pct, args.k_threshold,
                     args.require_high, args.high_lookback, args.high_within,
                     market_df, args.strategy): code
            for code in codes
        }

        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            completed += 1

            # 大樣本時每 10 檔印一次進度
            should_print = (total <= 30) or (completed % 10 == 0) or (completed == total)
            if "error" in r:
                if should_print or total <= 30:
                    log.warning(f"  [{completed}/{total}] {r['code']}: {r['error'][:60]}")
            else:
                if should_print:
                    log.info(f"  [{completed}/{total}] {r['code']}: {r['signal_count']} 訊號")

    # 3. 排序回原順序
    code_idx = {c: i for i, c in enumerate(codes)}
    results.sort(key=lambda r: code_idx.get(r.get("code", ""), 999))

    # 4. 顯示
    print_per_stock(results)
    print_aggregate(results)
    print_judgement(results)

    # 訓練/驗證期切割對照（如果啟用）
    if args.split_validate:
        print_split_validate(results, args.split_ratio)

    # 5. 存檔（可選）
    if args.save_json:
        # 移除 _full_results 太肥的部分（只留摘要）
        clean = []
        for r in results:
            r2 = {k: v for k, v in r.items() if k != "_full_results"}
            clean.append(r2)
        with open(args.save_json, 'w', encoding='utf-8') as f:
            json.dump({
                "config": {
                    "codes": codes,
                    "days": args.days,
                    "osc_pct": args.osc_pct,
                    "k_threshold": args.k_threshold,
                },
                "ran_at": datetime.now().isoformat(timespec='seconds'),
                "results": clean,
                "aggregate": {
                    f"{d}d": aggregate(results, d) for d in (5, 10, 20)
                },
            }, f, ensure_ascii=False, indent=2)
        log.info(f"\n✓ 結果存到 {args.save_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
