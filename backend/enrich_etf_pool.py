#!/usr/bin/env python3
"""
ETF 池長期高點 Enrich v1.0
=================================
讀取 ETF 持股 + watchlist + 新高觀察清單，計算每檔 1/3/5/10 年高點 metrics
+ 機構共識資訊，輸出至 data/etf_pool_long_term.json。

執行時機:
- run_daily.py 中，放在 enrich_long_term_high.py 之後
- 或獨立執行: python3 enrich_etf_pool.py

設計:
- 與 enrich_long_term_high.py 並行（互不干擾）
- 共用 kline_history_manager / long_term_high_calc 模組
- 獨立輸出 etf_pool_long_term.json，不污染 new_high_stocks.json
- 包含機構共識資訊（tier / etf_count / etfs / avg_ratio）

預估時間:
- 首次跑（145 檔，多數要抓 10 年）: 約 5-7 分鐘
- 之後增量更新: 約 1-2 分鐘
"""
import json
import time
from datetime import datetime
from pathlib import Path

# 共用模組
from kline_history_manager import (
    ensure_kline_data,
    load_kline_csv,
    get_stats,
)
from long_term_high_calc import calc_metrics
from etf_pool_helper import get_combined_pool_codes, get_consensus_dict

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / 'data'
OUT_FILE = DATA_DIR / 'etf_pool_long_term.json'

KLINE_YEARS = 10


def enrich_one(code, name, sources, consensus_info, verbose=False):
    """
    為單檔股票計算 metrics + 補上機構共識

    Returns: dict (含 lt_ 欄位 + tier/etfs/etf_count) 或 None（無法計算）
    """
    # 1. 確保有本地 K 線
    try:
        ensure_kline_data(code, years=KLINE_YEARS, verbose=False)
    except Exception as e:
        if verbose:
            print(f"    ⚠ {code} K 線下載失敗: {e}")
        return None

    klines = load_kline_csv(code)
    if not klines or len(klines) < 30:
        return None

    # 2. 計算長期高點 metrics
    try:
        metrics = calc_metrics(code, klines=klines)
    except Exception as e:
        if verbose:
            print(f"    ⚠ {code} 計算失敗: {e}")
        return None

    if not metrics:
        return None

    # 3. 整合輸出格式
    record = {
        'code': code,
        'name': name,
        'sources': sources,
        'today_close': metrics.get('current_close'),
        'data_first_date': metrics.get('data_first_date'),
        'data_days': metrics.get('data_days'),
    }

    # 長期高點欄位（lt_ 前綴，跟 enrich_long_term_high.py 一致）
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
        record[f'lt_{f}'] = metrics.get(f)

    # 機構共識欄位（inst_ 前綴，避免跟 lt_ 衝突）
    if consensus_info:
        record['inst_tier'] = consensus_info.get('tier')
        record['inst_etf_count'] = consensus_info.get('etf_count', 0)
        record['inst_etfs'] = consensus_info.get('etfs', [])
        record['inst_avg_ratio'] = consensus_info.get('avg_ratio', 0)
        record['inst_max_ratio'] = consensus_info.get('max_ratio', 0)
    else:
        # 不在任何 ETF 持股（可能是 watchlist 獨家）
        record['inst_tier'] = None
        record['inst_etf_count'] = 0
        record['inst_etfs'] = []
        record['inst_avg_ratio'] = 0
        record['inst_max_ratio'] = 0

    return record


def main():
    print(f"\n{'=' * 60}")
    print(f"🏛️  ETF 池長期高點 enrich (1/3/5/10 年 + 機構共識)")
    print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}\n")

    # 1. 取得股池併集
    print(f"[1/4] 取得股池併集...")
    combined = get_combined_pool_codes(include_watchlist=True, include_nh_watchlist=True)
    if not combined:
        print(f"  ✗ 股池為空（檢查 SQLite 與 watchlist 是否存在）")
        return

    # 來源分佈
    source_count = {}
    for info in combined.values():
        for s in info['sources']:
            source_count[s] = source_count.get(s, 0) + 1

    print(f"  → 併集股池: {len(combined)} 檔")
    for s, n in sorted(source_count.items()):
        print(f"    {s:<15} {n:>3} 檔")

    # 2. 取得機構共識
    print(f"\n[2/4] 取得機構共識資料...")
    consensus_dict = get_consensus_dict()
    print(f"  → ETF 共識資料: {len(consensus_dict)} 檔")

    # 3. 逐檔 enrich
    print(f"\n[3/4] 計算長期高點 + 機構共識 metrics...")
    print(f"  （首次跑會抓 10 年 K 線，預估 {len(combined) * 2} ~ {len(combined) * 5} 秒）\n")

    records = []
    failed = []
    breakout_summary = {'1y': 0, '3y': 0, '5y': 0, '10y': 0}
    tier_summary = {'core': 0, 'strong': 0, 'normal': 0, 'none': 0}
    fake_count = 0

    sorted_codes = sorted(combined.keys())
    total = len(sorted_codes)

    for i, code in enumerate(sorted_codes, 1):
        info = combined[code]
        name = info['name'] or '?'
        sources = info['sources']
        consensus_info = consensus_dict.get(code)

        prefix = f"  [{i}/{total}] {code} {name[:8]:<8}"
        print(prefix, end=' ', flush=True)

        try:
            record = enrich_one(code, name, sources, consensus_info, verbose=False)
            if record is None:
                failed.append(code)
                print("✗ 無資料")
                continue

            records.append(record)

            # 統計
            farthest = record.get('lt_farthest_breakout')
            if farthest:
                breakout_summary[farthest] = breakout_summary.get(farthest, 0) + 1
            tier = record.get('inst_tier') or 'none'
            tier_summary[tier] = tier_summary.get(tier, 0) + 1
            if record.get('lt_fake_breakout_alert'):
                fake_count += 1

            # 顯示
            farthest_label = f"🚀{farthest}" if farthest else '—'
            # tier 顯示: 用「🏛️ × N」格式（N = etf_count）
            etf_count = record.get('inst_etf_count', 0) or 0
            if etf_count >= 2:
                tier_str = f"🏛️×{etf_count}"
            elif etf_count == 1:
                tier_str = "🏛️"
            else:
                tier_str = "·"
            consol = record.get('lt_consolidation_days', 0) or 0
            fake = ' ⚠️' if record.get('lt_fake_breakout_alert') else ''
            print(f"{farthest_label:<5} {tier_str:<7} 盤整{consol}天{fake}")

            time.sleep(0.05)  # 輕量 sleep（lazy 補齊大多會 hit cache）
        except Exception as e:
            failed.append(code)
            print(f"✗ 例外: {e}")

    # 4. 排序與輸出
    print(f"\n[4/4] 寫入 {OUT_FILE.name}...")

    # 排序: tier (core > strong > normal > none) → farthest_breakout (10y > 5y > 3y > 1y > none)
    tier_order = {'core': 0, 'strong': 1, 'normal': 2, None: 3}
    farthest_order = {'10y': 0, '5y': 1, '3y': 2, '1y': 3, None: 4}
    records.sort(key=lambda r: (
        tier_order.get(r.get('inst_tier'), 4),
        farthest_order.get(r.get('lt_farthest_breakout'), 4),
        -(r.get('inst_etf_count') or 0),
        r['code'],
    ))

    output = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'pool_size': len(combined),
        'enriched_count': len(records),
        'failed_count': len(failed),
        'failed_codes': failed,
        'breakdown': {
            'tier': tier_summary,
            'breakout': breakout_summary,
            'fake_breakout': fake_count,
            'sources': source_count,
        },
        'stocks': records,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"  ✓ 已寫入")

    # 摘要
    print(f"\n{'=' * 60}")
    print(f"📊 結果摘要")
    print(f"{'=' * 60}")
    print(f"  成功 enrich: {len(records)} / {total}")
    print(f"  失敗: {len(failed)}")
    print(f"\n  Tier 分佈:")
    print(f"    🏛️×6   core   (6 檔ETF):     {tier_summary.get('core', 0):>3} 檔")
    print(f"    🏛️×4-5 strong (4-5 檔ETF):   {tier_summary.get('strong', 0):>3} 檔")
    print(f"    🏛️×1-3 normal (1-3 檔ETF):   {tier_summary.get('normal', 0):>3} 檔")
    print(f"    ·      無 ETF（純 watchlist）: {tier_summary.get('none', 0):>3} 檔")
    print(f"\n  突破分佈:")
    for tf in ['10y', '5y', '3y', '1y']:
        print(f"    🚀 {tf} 突破: {breakout_summary.get(tf, 0)} 檔")
    print(f"  ⚠️ 假突破警示: {fake_count} 檔")

    stats = get_stats()
    print(f"\n  本地 K 線資料庫:")
    print(f"    股票數: {stats['total_stocks']}")
    print(f"    總大小: {stats['total_size_mb']} MB")

    # Top 推薦：core tier + 大週期突破
    top_picks = [r for r in records
                 if r.get('inst_tier') == 'core' and r.get('lt_farthest_breakout')]
    if top_picks:
        print(f"\n  💎 機構核心 + 大週期突破:")
        for r in top_picks[:10]:
            farthest = r.get('lt_farthest_breakout')
            consol = r.get('lt_consolidation_days', 0) or 0
            etf_count = r.get('inst_etf_count', 0)
            fake = ' ⚠️' if r.get('lt_fake_breakout_alert') else ''
            print(f"    {r['code']} {r['name']:<10} 🚀{farthest} 🏛️×{etf_count} 盤整{consol}天{fake}")
    else:
        # 沒有核心突破時，顯示「次優候選」: strong tier + 突破
        strong_picks = [r for r in records
                        if r.get('inst_tier') == 'strong' and r.get('lt_farthest_breakout')]
        if strong_picks:
            print(f"\n  💎 強共識 + 大週期突破（次優）:")
            for r in strong_picks[:10]:
                farthest = r.get('lt_farthest_breakout')
                consol = r.get('lt_consolidation_days', 0) or 0
                etf_count = r.get('inst_etf_count', 0)
                fake = ' ⚠️' if r.get('lt_fake_breakout_alert') else ''
                print(f"    {r['code']} {r['name']:<10} 🚀{farthest} 🏛️×{etf_count} 盤整{consol}天{fake}")
        # 同時列出: 任何 tier 的 10y 突破
        ten_y_picks = [r for r in records if r.get('lt_farthest_breakout') == '10y']
        if ten_y_picks:
            print(f"\n  🚀 所有 10 年突破:")
            for r in ten_y_picks[:10]:
                consol = r.get('lt_consolidation_days', 0) or 0
                etf_count = r.get('inst_etf_count', 0)
                tier_str = f"🏛️×{etf_count}" if etf_count > 0 else '·'
                fake = ' ⚠️' if r.get('lt_fake_breakout_alert') else ''
                print(f"    {r['code']} {r['name']:<10} {tier_str:<6} 盤整{consol}天{fake}")

    print(f"{'=' * 60}\n")


if __name__ == '__main__':
    main()
