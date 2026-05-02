#!/usr/bin/env python3
"""
K 線歷史資料管理器 v1.0
=================================
管理本地 CSV 形式的長期 K 線資料（最多 10 年），支援 Lazy 補齊。

設計原則:
- 每檔股票一個 CSV：data/kline_history/{code}.csv
- 欄位: date, open, high, low, close, volume
- date 格式: YYYY-MM-DD
- 來源: Yahoo Finance（.TW 上市優先，.TWO 上櫃 fallback）

使用方式:
    from kline_history_manager import ensure_kline_data, load_kline_csv

    # 確保某檔股票有 10 年資料（自動補齊缺少的天數）
    ensure_kline_data('2330', years=10)

    # 載入 CSV 為 list of dict
    klines = load_kline_csv('2330')

注意:
- 全市場批次補齊請每檔間 sleep 0.3-0.5 秒避免被 Yahoo 擋
- 假日/停牌不會寫入，所以連續日期會有跳號（這是正常的）
"""
import csv
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================
# 設定
# ============================================================
SCRIPT_DIR = Path(__file__).parent
KLINE_DIR = SCRIPT_DIR / 'data' / 'kline_history'
KLINE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_YEARS = 10
SLEEP_BETWEEN_FETCH = 0.15  # 秒，跟 new_high_screener.py 一致

# CSV 欄位順序
CSV_FIELDS = ['date', 'open', 'high', 'low', 'close', 'volume']


# ============================================================
# Yahoo Finance 抓取
# ============================================================
# 跟既有 new_high_screener.py 用同樣的 query1 REST 端點，避免引入 yfinance 依賴
import requests
from datetime import datetime as _datetime

YAHOO_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9',
}


def _parse_yahoo_chart(json_data):
    """解析 Yahoo chart API 回傳的 JSON → list of kline dict"""
    result = json_data.get('chart', {}).get('result', [])
    if not result:
        return []

    chart = result[0]
    timestamps = chart.get('timestamp', []) or []
    quote = chart.get('indicators', {}).get('quote', [{}])[0]

    opens   = quote.get('open',   []) or []
    highs   = quote.get('high',   []) or []
    lows    = quote.get('low',    []) or []
    closes  = quote.get('close',  []) or []
    volumes = quote.get('volume', []) or []

    klines = []
    for ts, o, h, l, c, v in zip(timestamps, opens, highs, lows, closes, volumes):
        # 過濾不完整的資料點
        if None in (o, h, l, c, v):
            continue
        # 過濾停牌（成交量 0 且開收同價）
        if v == 0 and o == c:
            continue
        date_str = _datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
        klines.append({
            'date': date_str,
            'open':   round(float(o), 2),
            'high':   round(float(h), 2),
            'low':    round(float(l), 2),
            'close':  round(float(c), 2),
            'volume': int(v),
        })

    # 按日期排序（由舊到新）並去重
    seen = set()
    unique = []
    for k in sorted(klines, key=lambda x: x['date']):
        if k['date'] not in seen:
            seen.add(k['date'])
            unique.append(k)
    return unique


def fetch_kline_yahoo(stock_code, period='10y'):
    """
    從 Yahoo Finance 抓 K 線（用 query1 REST API，跟既有 new_high_screener.py 一致）

    Args:
        stock_code: 股票代號
        period: '1y', '2y', '5y', '10y', 'max' 等 Yahoo range 參數

    Returns: list of dict，按日期由舊到新排序，失敗回傳 []
    """
    # .TW 上市優先，.TWO 上櫃 fallback
    for suffix in ['.TW', '.TWO']:
        url = (f'https://query1.finance.yahoo.com/v8/finance/chart/'
               f'{stock_code}{suffix}?interval=1d&range={period}')
        try:
            r = requests.get(url, headers=YAHOO_HEADERS, timeout=20)
            if r.status_code != 200:
                continue
            data = r.json()
            klines = _parse_yahoo_chart(data)
            if klines:
                return klines
        except Exception:
            continue

    return []


# ============================================================
# CSV 讀寫
# ============================================================
def get_csv_path(stock_code):
    """取得某檔股票的 CSV 路徑"""
    return KLINE_DIR / f"{stock_code}.csv"


def load_kline_csv(stock_code):
    """
    載入某檔股票的本地 CSV

    Returns: list of dict（按日期由舊到新），檔案不存在或為空則回傳 []
    """
    path = get_csv_path(stock_code)
    if not path.exists():
        return []

    klines = []
    try:
        with open(path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    klines.append({
                        'date': row['date'],
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': int(row['volume'])
                    })
                except (ValueError, KeyError):
                    continue
        # 確保排序
        klines.sort(key=lambda x: x['date'])
    except Exception as e:
        print(f"    ⚠ 讀取 {stock_code}.csv 失敗: {e}")
        return []

    return klines


def save_kline_csv(stock_code, klines):
    """
    儲存 K 線到 CSV（覆蓋寫入）

    klines: list of dict，必須含所有 CSV_FIELDS 欄位
    """
    path = get_csv_path(stock_code)
    try:
        with open(path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for k in klines:
                writer.writerow({field: k[field] for field in CSV_FIELDS})
        return True
    except Exception as e:
        print(f"    ⚠ 寫入 {stock_code}.csv 失敗: {e}")
        return False


# ============================================================
# Lazy 補齊核心邏輯
# ============================================================
def get_last_date(stock_code):
    """取得本地 CSV 最後一筆資料的日期，無檔案則回傳 None"""
    klines = load_kline_csv(stock_code)
    if not klines:
        return None
    return klines[-1]['date']  # YYYY-MM-DD


def get_first_date(stock_code):
    """取得本地 CSV 第一筆資料的日期，無檔案則回傳 None"""
    klines = load_kline_csv(stock_code)
    if not klines:
        return None
    return klines[0]['date']


def days_since(date_str):
    """距離今天幾天（YYYY-MM-DD）"""
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return (datetime.now() - d).days
    except ValueError:
        return 9999


def needs_refresh(stock_code, years=DEFAULT_YEARS, max_stale_days=3):
    """
    判斷是否需要補資料

    Returns: 'fresh' (不需要), 'stale' (要補增量), 'missing' (要全抓)
    """
    path = get_csv_path(stock_code)
    if not path.exists():
        return 'missing'

    klines = load_kline_csv(stock_code)
    if not klines:
        return 'missing'

    # 檢查涵蓋年限：第一筆要夠舊
    first_date = klines[0]['date']
    target_oldest = (datetime.now() - timedelta(days=years * 365 + 30)).strftime('%Y-%m-%d')
    if first_date > target_oldest:
        # 第一筆太新 → 需要重抓更久的歷史
        return 'missing'

    # 檢查最後一筆夠新
    last_date = klines[-1]['date']
    if days_since(last_date) > max_stale_days:
        return 'stale'

    return 'fresh'


def ensure_kline_data(stock_code, years=DEFAULT_YEARS, verbose=True):
    """
    確保某檔股票有完整的 N 年 K 線資料
    - 完全沒檔 → 全抓
    - 涵蓋不夠 → 全抓
    - 太久沒更新 → 抓 1 個月併入
    - 已是新的 → 跳過

    Returns: dict 含 status('fresh'/'updated'/'created'/'failed') 和 days_count
    """
    status = needs_refresh(stock_code, years=years)

    if status == 'fresh':
        klines = load_kline_csv(stock_code)
        if verbose:
            print(f"    ✓ {stock_code}: 已是最新 ({len(klines)} 筆)")
        return {'status': 'fresh', 'days_count': len(klines)}

    if status == 'missing':
        # 全抓 N 年
        if verbose:
            print(f"    📥 {stock_code}: 首次抓取 {years} 年資料...", end=' ', flush=True)
        period = f'{years}y' if years <= 10 else 'max'
        klines = fetch_kline_yahoo(stock_code, period=period)
        if not klines:
            if verbose:
                print(f"失敗")
            return {'status': 'failed', 'days_count': 0}

        save_kline_csv(stock_code, klines)
        if verbose:
            print(f"✓ {len(klines)} 筆")
        return {'status': 'created', 'days_count': len(klines)}

    if status == 'stale':
        # 增量補齊：抓近 3 個月併入舊資料
        if verbose:
            print(f"    🔄 {stock_code}: 補齊近期資料...", end=' ', flush=True)
        new_klines = fetch_kline_yahoo(stock_code, period='3mo')
        if not new_klines:
            if verbose:
                print(f"失敗")
            return {'status': 'failed', 'days_count': 0}

        # 與舊資料合併（去重，新覆蓋舊）
        old_klines = load_kline_csv(stock_code)
        merged = {k['date']: k for k in old_klines}
        for k in new_klines:
            merged[k['date']] = k
        merged_list = sorted(merged.values(), key=lambda x: x['date'])
        save_kline_csv(stock_code, merged_list)

        new_count = len(merged_list) - len(old_klines)
        if verbose:
            print(f"✓ 新增 {new_count} 筆 (總 {len(merged_list)} 筆)")
        return {'status': 'updated', 'days_count': len(merged_list)}


def ensure_kline_data_batch(stock_codes, years=DEFAULT_YEARS, verbose=True):
    """
    批次確保多檔股票的 K 線資料

    Returns: dict { code: {status, days_count} }
    """
    results = {}
    total = len(stock_codes)
    for i, code in enumerate(stock_codes, 1):
        if verbose:
            print(f"  [{i}/{total}] {code}", end='', flush=True)
        try:
            result = ensure_kline_data(code, years=years, verbose=verbose)
            results[code] = result
            # 只有實際抓網路才需要 sleep
            if result['status'] in ('created', 'updated'):
                time.sleep(SLEEP_BETWEEN_FETCH)
        except Exception as e:
            print(f"    ✗ {code} 例外: {e}")
            results[code] = {'status': 'failed', 'days_count': 0, 'error': str(e)}

    return results


# ============================================================
# 統計工具
# ============================================================
def get_stats():
    """取得本地 K 線資料庫統計"""
    if not KLINE_DIR.exists():
        return {'total_stocks': 0, 'total_size_mb': 0}

    csv_files = list(KLINE_DIR.glob('*.csv'))
    total_size = sum(f.stat().st_size for f in csv_files)
    return {
        'total_stocks': len(csv_files),
        'total_size_mb': round(total_size / 1024 / 1024, 2),
        'kline_dir': str(KLINE_DIR),
    }


# ============================================================
# CLI
# ============================================================
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("用法:")
        print(f"  {sys.argv[0]} stats              # 顯示統計")
        print(f"  {sys.argv[0]} fetch <code>       # 抓單檔")
        print(f"  {sys.argv[0]} check <code>       # 檢查單檔狀態")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'stats':
        s = get_stats()
        print(f"📊 K 線資料庫統計")
        print(f"  路徑: {s['kline_dir']}")
        print(f"  股票數: {s['total_stocks']}")
        print(f"  總大小: {s['total_size_mb']} MB")

    elif cmd == 'fetch' and len(sys.argv) >= 3:
        code = sys.argv[2]
        result = ensure_kline_data(code)
        print(f"\n結果: {result}")

    elif cmd == 'check' and len(sys.argv) >= 3:
        code = sys.argv[2]
        status = needs_refresh(code)
        first = get_first_date(code)
        last = get_last_date(code)
        klines = load_kline_csv(code)
        print(f"📋 {code}")
        print(f"  狀態: {status}")
        print(f"  資料筆數: {len(klines)}")
        print(f"  起始日: {first}")
        print(f"  最後日: {last}")

    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)
