#!/usr/bin/env python3
"""
ETF 持股 Helper v1.0
=================================
從 SQLite 讀取最新 ETF 持股資料，提供共用查詢介面。

資料來源:
  - SQLite: ~/MyStock/data/market_data.db
  - Table:  etf_holdings_history
  - 由 fetch_etf_holdings.py 每日更新（run_daily.py 補充段）

主要函式:
  - get_etf_pool_codes()       取得所有 ETF 持股代號集合
  - get_etf_consensus(code)    取得某檔股票的機構共識資訊
  - get_consensus_dict()       取得全部 {code: consensus_info}
  - get_combined_pool_codes()  併集股池: ETF + watchlist + new_high_watchlist

設計原則:
  - 純讀取，不寫入
  - 失敗時回傳空集合/None，不擲例外（讓上游可降級處理）
  - 自動取最新資料日期（無需呼叫端傳入）
"""
import json
import sqlite3
from pathlib import Path

# ============================================================
# 設定
# ============================================================
SCRIPT_DIR = Path(__file__).parent
DB_PATH = Path.home() / 'MyStock' / 'data' / 'market_data.db'
BLACKLIST_PATH = SCRIPT_DIR / 'data' / 'etf_holdings_blacklist.json'

# Tier 分級閾值（依資料分佈，6 檔 ETF 全有 = core）
TIER_CORE = 6      # 6 檔 ETF 全部持有 → 機構鐵桿核心
TIER_STRONG = 4    # 4-5 檔 → 強共識
TIER_NORMAL = 1    # 1-3 檔 → 普通入選

# 模組級快取（避免每次都讀檔案）
_BLACKLIST_CACHE = None


# ============================================================
# 黑名單機制（過濾非台股代號）
# ============================================================
def _load_blacklist():
    """
    載入非台股代號黑名單（已知 MoneyDJ 抓到但 Yahoo 找不到 .TW/.TWO 的代號）

    Returns: set[str]
    """
    global _BLACKLIST_CACHE
    if _BLACKLIST_CACHE is not None:
        return _BLACKLIST_CACHE

    if not BLACKLIST_PATH.exists():
        _BLACKLIST_CACHE = set()
        return _BLACKLIST_CACHE

    try:
        with open(BLACKLIST_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        _BLACKLIST_CACHE = set(data.get('blacklist', {}).keys())
    except Exception:
        _BLACKLIST_CACHE = set()

    return _BLACKLIST_CACHE


def is_blacklisted(stock_code):
    """判斷某代號是否在黑名單內（非台股）"""
    return stock_code in _load_blacklist()


# ============================================================
# 內部工具
# ============================================================
def _open_db():
    """開啟 SQLite 連線，失敗回傳 None（不丟例外）"""
    if not DB_PATH.exists():
        return None
    try:
        return sqlite3.connect(str(DB_PATH))
    except Exception:
        return None


def _get_latest_date(conn):
    """取得 etf_holdings_history 表中的最新資料日期"""
    cur = conn.execute(
        "SELECT MAX(data_date) FROM etf_holdings_history"
    )
    row = cur.fetchone()
    return row[0] if row and row[0] else None


def _classify_tier(etf_count):
    """依被持有的 ETF 數量分級"""
    if etf_count >= TIER_CORE:
        return 'core'
    elif etf_count >= TIER_STRONG:
        return 'strong'
    elif etf_count >= TIER_NORMAL:
        return 'normal'
    else:
        return None


# ============================================================
# Public API
# ============================================================
def get_etf_pool_codes():
    """
    取得最新 ETF 持股的所有股票代號（去重）

    Returns: set[str]，失敗回空集合
    """
    conn = _open_db()
    if conn is None:
        return set()

    try:
        latest = _get_latest_date(conn)
        if not latest:
            return set()

        cur = conn.execute("""
            SELECT DISTINCT stock_code
            FROM etf_holdings_history
            WHERE data_date = ? AND stock_code != ''
        """, (latest,))
        return {row[0] for row in cur.fetchall() if not is_blacklisted(row[0])}
    except Exception:
        return set()
    finally:
        conn.close()


def get_consensus_dict():
    """
    取得所有 ETF 持股的機構共識資訊

    Returns: dict[code -> {
        'etf_count': int,           被幾檔 ETF 持有
        'etfs': list[str],          ETF 代號清單（依字母順序）
        'avg_ratio': float,         平均權重(%)
        'max_ratio': float,         最高單一 ETF 權重(%)
        'tier': 'core'/'strong'/'normal',
        'name': str,                股票名稱
    }]

    失敗回空 dict
    """
    conn = _open_db()
    if conn is None:
        return {}

    try:
        latest = _get_latest_date(conn)
        if not latest:
            return {}

        # 一次撈出所有資料，在 Python 端聚合（比多次 SQL 快）
        cur = conn.execute("""
            SELECT stock_code, stock_name, etf_code, ratio
            FROM etf_holdings_history
            WHERE data_date = ? AND stock_code != ''
            ORDER BY stock_code, etf_code
        """, (latest,))

        result = {}
        for code, name, etf_code, ratio in cur.fetchall():
            # 跳過黑名單代號（非台股）
            if is_blacklisted(code):
                continue
            if code not in result:
                result[code] = {
                    'name': name,
                    'etfs': [],
                    'ratios': [],
                }
            result[code]['etfs'].append(etf_code)
            result[code]['ratios'].append(float(ratio or 0))

        # 聚合
        for code, info in result.items():
            etf_count = len(info['etfs'])
            ratios = info['ratios']
            info['etf_count'] = etf_count
            info['avg_ratio'] = round(sum(ratios) / len(ratios), 3) if ratios else 0
            info['max_ratio'] = round(max(ratios), 3) if ratios else 0
            info['tier'] = _classify_tier(etf_count)
            del info['ratios']  # 不對外暴露

        return result
    except Exception:
        return {}
    finally:
        conn.close()


def get_etf_consensus(stock_code):
    """
    取得單檔股票的機構共識資訊

    Returns: dict 或 None
    """
    return get_consensus_dict().get(stock_code)


def get_combined_pool_codes(include_watchlist=True, include_nh_watchlist=True):
    """
    取得擴大股池: ETF 持股 ∪ MACD watchlist ∪ 新高觀察清單

    Returns: dict[code -> {
        'name': str,
        'sources': list[str]   ['etf', 'watchlist', 'nh_watchlist']
    }]
    """
    pool = {}

    # 1. ETF 持股
    consensus = get_consensus_dict()
    for code, info in consensus.items():
        pool[code] = {
            'name': info.get('name', ''),
            'sources': ['etf'],
        }

    # 2. MACD watchlist
    if include_watchlist:
        wl_path = SCRIPT_DIR / 'data' / 'watchlist.json'
        if wl_path.exists():
            try:
                with open(wl_path, 'r', encoding='utf-8') as f:
                    wl = json.load(f)
                for item in wl:
                    if isinstance(item, dict):
                        code = str(item.get('code', '')).strip()
                        name = item.get('name', '')
                    else:
                        code = str(item).strip()
                        name = ''
                    if not code or is_blacklisted(code):
                        continue
                    if code in pool:
                        pool[code]['sources'].append('watchlist')
                    else:
                        pool[code] = {'name': name, 'sources': ['watchlist']}
            except Exception:
                pass

    # 3. 新高觀察清單
    if include_nh_watchlist:
        nhwl_path = SCRIPT_DIR / 'data' / 'new_high_watchlist.json'
        if nhwl_path.exists():
            try:
                with open(nhwl_path, 'r', encoding='utf-8') as f:
                    nhwl = json.load(f)
                # 兼容 list 或 {stocks: [...]} 兩種結構
                items = nhwl if isinstance(nhwl, list) else nhwl.get('stocks', [])
                for item in items:
                    if isinstance(item, dict):
                        code = str(item.get('code', '')).strip()
                        name = item.get('name', '')
                    else:
                        code = str(item).strip()
                        name = ''
                    if not code or is_blacklisted(code):
                        continue
                    if code in pool:
                        pool[code]['sources'].append('nh_watchlist')
                    else:
                        pool[code] = {'name': name, 'sources': ['nh_watchlist']}
            except Exception:
                pass

    return pool


# ============================================================
# CLI（debug 用）
# ============================================================
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("用法:")
        print(f"  {sys.argv[0]} stats             # 統計")
        print(f"  {sys.argv[0]} pool              # 印出股池併集")
        print(f"  {sys.argv[0]} consensus <code>  # 查單檔股票")
        print(f"  {sys.argv[0]} blacklist         # 顯示黑名單")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'blacklist':
        bl = _load_blacklist()
        if not bl:
            print("⚠️  黑名單為空（檔案不存在或載入失敗）")
            print(f"  路徑: {BLACKLIST_PATH}")
        else:
            print(f"📋 非台股代號黑名單（{len(bl)} 個）")
            try:
                with open(BLACKLIST_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for code, desc in data.get('blacklist', {}).items():
                    print(f"  {code}: {desc}")
                print(f"\n  路徑: {BLACKLIST_PATH}")
                print(f"  最後更新: {data.get('_last_updated', '?')}")
            except Exception as e:
                print(f"  讀取失敗: {e}")

    elif cmd == 'stats':
        codes = get_etf_pool_codes()
        consensus = get_consensus_dict()
        combined = get_combined_pool_codes()

        print(f"📊 ETF 持股 Helper 統計")
        print(f"  ETF 持股獨立股票: {len(codes)} 檔")
        print(f"  併集股池: {len(combined)} 檔")
        print()
        # Tier 分佈
        tier_count = {'core': 0, 'strong': 0, 'normal': 0}
        for info in consensus.values():
            t = info.get('tier')
            if t:
                tier_count[t] += 1
        print(f"  Tier 分佈:")
        print(f"    core    (6 檔ETF):    {tier_count['core']:>3} 檔")
        print(f"    strong  (4-5 檔ETF):  {tier_count['strong']:>3} 檔")
        print(f"    normal  (1-3 檔ETF):  {tier_count['normal']:>3} 檔")

        # Source 分佈
        source_count = {}
        for info in combined.values():
            for s in info['sources']:
                source_count[s] = source_count.get(s, 0) + 1
        print(f"\n  併集股池來源:")
        for s, n in sorted(source_count.items()):
            print(f"    {s:<15} {n:>3} 檔")

    elif cmd == 'pool':
        combined = get_combined_pool_codes()
        for code, info in sorted(combined.items()):
            srcs = '+'.join(info['sources'])
            print(f"  {code} {info['name']:<12} [{srcs}]")
        print(f"\n總計 {len(combined)} 檔")

    elif cmd == 'consensus' and len(sys.argv) >= 3:
        code = sys.argv[2]
        info = get_etf_consensus(code)
        if info is None:
            print(f"❌ {code} 不在任何 ETF 持股中")
            sys.exit(1)
        print(f"📊 {code} {info['name']}")
        print(f"  被 {info['etf_count']} 檔 ETF 持有: {', '.join(info['etfs'])}")
        print(f"  平均權重: {info['avg_ratio']}%")
        print(f"  最高權重: {info['max_ratio']}%")
        print(f"  Tier: {info['tier']}")

    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)
