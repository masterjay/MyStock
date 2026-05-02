#!/usr/bin/env python3
"""
長期高點 enrich 腳本 v1.0
=================================
讀取 new_high_stocks.json，為每檔股票補上 1/3/5/10 年高點 metrics，寫回原檔。

執行時機:
- 在 new_high_screener.py 之後（在 run_daily.py 中追加為 post-step）
- 或獨立執行: python3 enrich_long_term_high.py

設計考量:
- 不動既有 new_high_screener.py（避免影響其他人的修改）
- 所有新欄位掛在 stock dict 裡，前綴 lt_ 避免衝突
- 缺資料時 lazy 補齊（會自動下載 Yahoo K 線）
- 失敗的股票照樣留在 JSON，但 lt_ 欄位為 None
"""
import json
import time
from datetime import datetime
from pathlib import Path

# 共用模組
from kline_history_manager import (
    ensure_kline_data,
    load_kline_csv,
    SLEEP_BETWEEN_FETCH,
    get_stats,
)
from long_term_high_calc import calc_metrics

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / 'data'
NH_FILE = DATA_DIR / 'new_high_stocks.json'

# 抓資料時要保留的年限
KLINE_YEARS = 10


def enrich_stock(stock_dict, verbose=True):
    """
    為單一股票 dict 補上長期高點欄位

    補入的欄位（前綴 lt_）:
        lt_high_1y, lt_high_3y, lt_high_5y, lt_high_10y
        lt_pct_to_1y_high, ...
        lt_breakout_1y, lt_breakout_3y, lt_breakout_5y, lt_breakout_10y
        lt_farthest_breakout       ('1y'/'3y'/'5y'/'10y'/None)
        lt_consolidation_days
        lt_consolidation_ref
        lt_fake_breakout_alert
        lt_fake_breakout_days_after
        lt_breakout_day             (最近一次首次突破 farthest 的日期)
        lt_breakout_day_low

    回傳: stock_dict（已就地修改）
    """
    code = stock_dict.get('code', '')
    if not code:
        return stock_dict

    # 1. 確保有本地 K 線資料（lazy 補齊）
    try:
        ensure_kline_data(code, years=KLINE_YEARS, verbose=False)
    except Exception as e:
        if verbose:
            print(f"    ⚠ {code} K 線下載失敗: {e}")
        _mark_no_data(stock_dict)
        return stock_dict

    # 2. 計算 metrics
    klines = load_kline_csv(code)
    if not klines or len(klines) < 30:
        _mark_no_data(stock_dict)
        return stock_dict

    try:
        metrics = calc_metrics(code, klines=klines)
    except Exception as e:
        if verbose:
            print(f"    ⚠ {code} 計算失敗: {e}")
        _mark_no_data(stock_dict)
        return stock_dict

    if not metrics:
        _mark_no_data(stock_dict)
        return stock_dict

    # 3. 把 metrics 對映到 lt_ 前綴欄位
    fields_to_copy = [
        'high_1y', 'high_3y', 'high_5y', 'high_10y',
        'pct_to_1y_high', 'pct_to_3y_high', 'pct_to_5y_high', 'pct_to_10y_high',
        'breakout_1y', 'breakout_3y', 'breakout_5y', 'breakout_10y',
        'farthest_breakout',
        'consolidation_days', 'consolidation_ref',
        'fake_breakout_alert', 'fake_breakout_days_after',
        'breakout_day', 'breakout_day_low',
    ]
    for f in fields_to_copy:
        stock_dict[f'lt_{f}'] = metrics.get(f)

    return stock_dict


def _mark_no_data(stock_dict):
    """標記無長期資料（讓前端可以顯示 - 而不是顯示 0）"""
    fields = [
        'high_1y', 'high_3y', 'high_5y', 'high_10y',
        'pct_to_1y_high', 'pct_to_3y_high', 'pct_to_5y_high', 'pct_to_10y_high',
        'breakout_1y', 'breakout_3y', 'breakout_5y', 'breakout_10y',
        'farthest_breakout',
        'consolidation_days', 'consolidation_ref',
        'fake_breakout_alert', 'fake_breakout_days_after',
        'breakout_day', 'breakout_day_low',
    ]
    for f in fields:
        stock_dict[f'lt_{f}'] = None


def main():
    print(f"\n{'=' * 60}")
    print(f"📈 長期高點 enrich (1/3/5/10 年)")
    print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}\n")

    # 1. 讀 new_high_stocks.json
    if not NH_FILE.exists():
        print(f"❌ 找不到 {NH_FILE}")
        print(f"   請先執行 new_high_screener.py")
        return

    print(f"[1/3] 讀取 {NH_FILE.name}...")
    with open(NH_FILE, 'r', encoding='utf-8') as f:
        nh_data = json.load(f)

    stocks = nh_data.get('stocks', [])
    if not stocks:
        print(f"  ⚠ stocks 為空，無事可做")
        return
    total = len(stocks)
    print(f"  → 共 {total} 檔需處理\n")

    # 2. 逐檔 enrich
    print(f"[2/3] 計算長期高點 metrics...")
    print(f"  （首次跑會抓 10 年 K 線，預計 {total * 3} ~ {total * 8} 秒）\n")

    success = 0
    failed = 0
    breakout_summary = {'1y': 0, '3y': 0, '5y': 0, '10y': 0}

    for i, stock in enumerate(stocks, 1):
        code = stock.get('code', '?')
        name = stock.get('name', '?')
        prefix = f"  [{i}/{total}] {code} {name}"
        print(prefix, end=' ', flush=True)

        try:
            enrich_stock(stock, verbose=False)
            farthest = stock.get('lt_farthest_breakout')
            consol = stock.get('lt_consolidation_days')
            if stock.get('lt_high_1y') is not None:
                success += 1
                if farthest:
                    breakout_summary[farthest] = breakout_summary.get(farthest, 0) + 1
                fake = '⚠️假突破' if stock.get('lt_fake_breakout_alert') else ''
                farthest_label = f"🚀{farthest}" if farthest else '—'
                print(f"{farthest_label} 盤整{consol}天 {fake}")
            else:
                failed += 1
                print("✗ 無資料")

            # Sleep 只在實際抓網路才需要
            # （ensure_kline_data 內部已 stale 才會抓）
            # 簡化處理：每檔 sleep 一點就好
            time.sleep(0.1)
        except Exception as e:
            failed += 1
            print(f"✗ 例外: {e}")

    # 3. 寫回 JSON
    print(f"\n[3/3] 寫回 {NH_FILE.name}...")
    nh_data['stocks'] = stocks
    nh_data['lt_enriched_at'] = datetime.now().isoformat()
    with open(NH_FILE, 'w', encoding='utf-8') as f:
        json.dump(nh_data, f, ensure_ascii=False, indent=2)
    print(f"  ✓ 已寫入")

    # 摘要
    print(f"\n{'=' * 60}")
    print(f"📊 結果摘要")
    print(f"{'=' * 60}")
    print(f"  成功 enrich: {success} / {total}")
    print(f"  失敗: {failed}")
    print(f"\n  突破分佈:")
    for tf in ['10y', '5y', '3y', '1y']:
        print(f"    🚀 {tf} 突破: {breakout_summary.get(tf, 0)} 檔")

    # K 線資料庫統計
    stats = get_stats()
    print(f"\n  本地 K 線資料庫:")
    print(f"    股票數: {stats['total_stocks']}")
    print(f"    總大小: {stats['total_size_mb']} MB")
    print(f"{'=' * 60}\n")


if __name__ == '__main__':
    main()
