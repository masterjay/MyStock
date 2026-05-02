#!/usr/bin/env python3
"""
長期高點計算器 v1.0
=================================
基於本地 K 線資料庫，計算每檔股票的長期高點/盤整/突破指標。

計算項目:
  1. 1 / 3 / 5 / 10 年內的最高價
  2. 距離各時間尺度高點的百分比
  3. 是否突破各時間尺度高點（當日收盤 > 高點）
  4. 「最遠新高」: 突破到哪個尺度（10y > 5y > 3y > 1y > none）
  5. 盤整天數: 在 [長期高點 × 0.85, 長期高點 × 1.0] 區間的累積天數
  6. 假突破偵測: 突破日後 5 個交易日內是否跌破突破日最低價

使用方式:
    from long_term_high_calc import calc_metrics

    metrics = calc_metrics('2330')
    # {
    #   'high_1y': 1100, 'pct_to_1y_high': -2.3, 'breakout_1y': False,
    #   'high_3y': 1100, ...
    #   'farthest_breakout': '5y',  # 最遠突破尺度
    #   'consolidation_days': 580,  # 盤整天數（過去 N 年內）
    #   'fake_breakout_alert': False,
    # }

設計原則:
- 純計算，不抓網路。網路抓取交給 kline_history_manager
- 失敗時各欄位為 None（讓上游可區分「沒資料」vs「未突破」）
"""
from datetime import datetime, timedelta
from pathlib import Path

# 共用模組
from kline_history_manager import load_kline_csv

# ============================================================
# 設定
# ============================================================
TIMEFRAMES = [
    ('1y',  365),
    ('3y',  365 * 3),
    ('5y',  365 * 5),
    ('10y', 365 * 10),
]

# 盤整定義: 收盤在 [高點 × LOWER, 高點 × UPPER] 之間
CONSOLIDATION_LOWER = 0.85
CONSOLIDATION_UPPER = 1.00

# 假突破偵測窗口
FAKE_BREAKOUT_WINDOW = 5  # 5 個交易日

# 最遠突破優先級（從遠到近）
BREAKOUT_PRIORITY = ['10y', '5y', '3y', '1y']


# ============================================================
# 工具函式
# ============================================================
def filter_by_days(klines, days):
    """從 klines 取出近 N 日的資料"""
    if not klines:
        return []
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    return [k for k in klines if k['date'] >= cutoff_date]


def safe_round(val, digits=2):
    if val is None:
        return None
    try:
        return round(val, digits)
    except (TypeError, ValueError):
        return None


# ============================================================
# 核心計算
# ============================================================
def calc_high_for_timeframe(klines, days):
    """
    計算某時間尺度內的最高價（看 high）以及該根 K 棒的日期

    Returns: (high_price, high_date) 或 (None, None)
    """
    subset = filter_by_days(klines, days)
    if not subset:
        return None, None
    high_k = max(subset, key=lambda x: x['high'])
    return high_k['high'], high_k['date']


def calc_breakout_status(current_close, high_price, current_date, high_date):
    """
    判斷是否突破:
      - 必須當日收盤 > 過去高點
      - 高點不能是當日（不然永遠是「突破」自己）
      → 比較規則: 我們算「過去 N 日（不含今天）」的高點
    """
    if current_close is None or high_price is None:
        return False
    # 如果高點就在當日，視為「未突破」（因為是同一根）
    if high_date == current_date:
        return False
    return current_close > high_price


def calc_consolidation_days(klines, high_price, days):
    """
    計算過去 N 日內，收盤價在 [高點×0.85, 高點×1.00] 之間的天數
    """
    if high_price is None or high_price <= 0:
        return 0
    subset = filter_by_days(klines, days)
    if not subset:
        return 0

    lower = high_price * CONSOLIDATION_LOWER
    upper = high_price * CONSOLIDATION_UPPER
    count = sum(1 for k in subset if lower <= k['close'] <= upper)
    return count


def detect_fake_breakout(klines, breakout_date, breakout_low):
    """
    偵測假突破:
      - 突破日後 5 個交易日內
      - 是否有任何一天的 low 跌破 breakout_low

    Args:
        klines: 完整的 K 線
        breakout_date: 突破日 'YYYY-MM-DD'
        breakout_low: 突破當日的 low

    Returns:
        bool: True = 已假突破 / False = 未假突破或還在觀察期
        days_after: 突破後過了幾個交易日
    """
    if not breakout_date or breakout_low is None:
        return False, 0

    # 找到突破日的 index
    after_breakout = [k for k in klines if k['date'] > breakout_date]
    if not after_breakout:
        return False, 0

    # 取突破日後 5 個交易日
    window = after_breakout[:FAKE_BREAKOUT_WINDOW]
    days_after = len(window)

    # 任何一根的 low 跌破 breakout_low
    for k in window:
        if k['low'] < breakout_low:
            return True, days_after

    return False, days_after


# ============================================================
# 主入口
# ============================================================
def calc_metrics(stock_code, klines=None):
    """
    計算單檔股票的長期高點 metrics

    Args:
        stock_code: 股票代號
        klines: 已載入的 K 線（可選，為 None 則自動載入）

    Returns:
        dict 含所有指標。若資料完全缺失則回傳 None。
    """
    if klines is None:
        klines = load_kline_csv(stock_code)

    if not klines or len(klines) < 30:
        return None

    # 當前資料
    current = klines[-1]
    current_close = current['close']
    current_date = current['date']

    result = {
        'code': stock_code,
        'current_close': safe_round(current_close),
        'current_date': current_date,
        'data_days': len(klines),
        'data_first_date': klines[0]['date'],
    }

    # 各時間尺度
    breakout_flags = {}
    high_records = {}

    for tf_name, tf_days in TIMEFRAMES:
        # 排除當日（不然會把自己當高點）
        klines_excl_today = [k for k in klines if k['date'] < current_date]
        high_price, high_date = calc_high_for_timeframe(klines_excl_today, tf_days)

        result[f'high_{tf_name}'] = safe_round(high_price)
        result[f'high_{tf_name}_date'] = high_date

        # 距離高點百分比（負數=低於高點，正數=高於高點即突破）
        if high_price and current_close:
            pct = (current_close / high_price - 1) * 100
            result[f'pct_to_{tf_name}_high'] = safe_round(pct, 2)
        else:
            result[f'pct_to_{tf_name}_high'] = None

        # 突破判斷
        is_breakout = calc_breakout_status(current_close, high_price, current_date, high_date)
        result[f'breakout_{tf_name}'] = is_breakout
        breakout_flags[tf_name] = is_breakout

        if is_breakout:
            high_records[tf_name] = (high_price, high_date)

    # 最遠突破尺度
    farthest = None
    for tf in BREAKOUT_PRIORITY:
        if breakout_flags.get(tf):
            farthest = tf
            break
    result['farthest_breakout'] = farthest

    # 盤整天數（用最遠突破的尺度當基準；若無突破，用 3y 當預設基準）
    if farthest:
        ref_tf = farthest
        ref_high = result[f'high_{farthest}']
    else:
        ref_tf = '3y'
        ref_high = result.get('high_3y')

    if ref_high:
        # 算「過去 N 年內」的盤整天數（N 對應 ref_tf）
        ref_days = dict(TIMEFRAMES)[ref_tf]
        result['consolidation_days'] = calc_consolidation_days(klines, ref_high, ref_days)
        result['consolidation_ref'] = ref_tf
    else:
        result['consolidation_days'] = 0
        result['consolidation_ref'] = None

    # 假突破警示
    # 找最近一次突破的日期: 從近到遠掃，第一個收盤 > 該尺度高點的日子
    fake_alert = False
    fake_days_after = 0
    if farthest and result.get(f'high_{farthest}'):
        ref_high_price = result[f'high_{farthest}']
        # 找最近一次「收盤首次超過 ref_high_price」的那一天
        breakout_day = None
        breakout_day_low = None
        # 從新到舊掃
        for i in range(len(klines) - 1, -1, -1):
            k = klines[i]
            if k['close'] > ref_high_price:
                # 是不是「首次」突破: 看前一根是否未突破
                if i == 0 or klines[i - 1]['close'] <= ref_high_price:
                    breakout_day = k['date']
                    breakout_day_low = k['low']
                    break

        if breakout_day:
            fake_alert, fake_days_after = detect_fake_breakout(klines, breakout_day, breakout_day_low)
            result['breakout_day'] = breakout_day
            result['breakout_day_low'] = safe_round(breakout_day_low)

    result['fake_breakout_alert'] = fake_alert
    result['fake_breakout_days_after'] = fake_days_after

    return result


def calc_metrics_batch(stock_codes, verbose=False):
    """批次計算多檔"""
    results = {}
    for code in stock_codes:
        try:
            m = calc_metrics(code)
            if m:
                results[code] = m
            elif verbose:
                print(f"  ⚠ {code}: 無 K 線資料或資料太少")
        except Exception as e:
            if verbose:
                print(f"  ✗ {code}: 計算失敗 - {e}")
    return results


# ============================================================
# CLI
# ============================================================
if __name__ == '__main__':
    import sys
    import json as _json

    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <stock_code>")
        sys.exit(1)

    code = sys.argv[1]
    metrics = calc_metrics(code)
    if metrics is None:
        print(f"❌ {code}: 無法計算（資料缺失）")
        sys.exit(1)

    print(_json.dumps(metrics, ensure_ascii=False, indent=2))
