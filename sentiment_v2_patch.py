#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
情緒指數 v2 升級 Patch Script
在 GCP 上執行: python3 sentiment_v2_patch.py
會自動修改以下檔案:
1. market_breadth_collector.py - 修 DB 路徑 + 改 new_highs_lows + 加乖離率
2. market_data_exporter.py - calc_sentiment 擴充到 7 指標
3. run_daily.py - 加入 breadth collector step
4. dashboard.html - 前端移除待實作標記 + 更新權重
"""

import os
import shutil
from datetime import datetime

BACKEND = os.path.expanduser('~/MyStock/backend')
DASHBOARD = os.path.expanduser('~/MyStock/dashboard.html')

def backup_file(path):
    """備份檔案"""
    if os.path.exists(path):
        backup = f"{path}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(path, backup)
        print(f"  備份: {backup}")

# ============================================================
# 1. 重寫 market_breadth_collector.py
# ============================================================
def patch_breadth_collector():
    path = os.path.join(BACKEND, 'market_breadth_collector.py')
    print(f"\n[1/4] 重寫 {path}")
    backup_file(path)
    
    content = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市場廣度與動能數據收集器 v2
收集: 1. 大盤收盤價 2. 漲跌家數 3. 漲跌停家數(從 limit_updown 讀取)
"""

import requests
import sqlite3
from datetime import datetime
from pathlib import Path
import re
import time

DB_PATH = Path(__file__).parent / 'data' / 'market_data.db'


def get_conn():
    return sqlite3.connect(str(DB_PATH))


def get_market_momentum():
    """取得加權指數動能數據 - 使用 FMTQIK"""
    try:
        url = "https://www.twse.com.tw/exchangeReport/FMTQIK?response=json"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        
        if r.status_code != 200:
            return None
        
        data = r.json()
        
        if 'data' in data and len(data['data']) > 0:
            latest = data['data'][-1]
            close_price = float(latest[4].replace(',', ''))
            change = float(latest[5].replace(',', ''))
            
            return {
                'date': datetime.now().strftime('%Y%m%d'),
                'close': close_price,
                'change': change
            }
        return None
        
    except Exception as e:
        print(f"  ✗ 抓取動能失敗: {e}")
        return None


def get_market_breadth():
    """取得市場廣度 (上漲下跌家數) - 2025新格式"""
    try:
        url = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALL"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=15)
        
        if r.status_code != 200:
            return None
        
        data = r.json()
        
        if 'tables' in data and len(data['tables']) > 7:
            momentum_table = data['tables'][7]['data']
            
            def parse_count(s):
                match = re.match(r'([\\d,]+)\\((\d+)\\)', s.replace(',', ''))
                if match:
                    return int(match.group(1).replace(',','')), int(match.group(2))
                return int(s.replace(',', '')), 0
            
            up_count, up_limit = parse_count(momentum_table[0][2])
            down_count, down_limit = parse_count(momentum_table[1][2])
            unchanged = int(momentum_table[2][2].replace(',', ''))
            
            total = up_count + down_count + unchanged
            up_ratio = (up_count / total * 100) if total > 0 else 50
            
            return {
                'date': datetime.now().strftime('%Y%m%d'),
                'up_count': up_count,
                'down_count': down_count,
                'unchanged': unchanged,
                'up_ratio': round(up_ratio, 1),
                'up_limit': up_limit,
                'down_limit': down_limit
            }
        
        return None
        
    except Exception as e:
        print(f"  ✗ 抓取廣度失敗: {e}")
        return None


def get_limit_updown_from_db(date_str):
    """從 limit_updown 表讀取當天漲跌停家數"""
    try:
        conn = get_conn()
        up = conn.execute(
            "SELECT COUNT(*) FROM limit_updown WHERE date=? AND type='limit_up'",
            (date_str,)
        ).fetchone()[0]
        down = conn.execute(
            "SELECT COUNT(*) FROM limit_updown WHERE date=? AND type='limit_down'",
            (date_str,)
        ).fetchone()[0]
        conn.close()
        return {'up_limit': up, 'down_limit': down}
    except Exception as e:
        print(f"  ✗ 讀取漲跌停失敗: {e}")
        return None


def save_to_database(momentum_data, breadth_data):
    """儲存到 market_breadth 表"""
    conn = get_conn()
    cursor = conn.cursor()
    
    cursor.execute(\'\'\'
        CREATE TABLE IF NOT EXISTS market_breadth (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            taiex_close REAL,
            up_count INTEGER,
            down_count INTEGER,
            unchanged INTEGER,
            up_ratio REAL,
            up_limit INTEGER DEFAULT 0,
            down_limit INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    \'\'\')
    
    # 漲跌停從 breadth 或 limit_updown 表取
    up_limit = breadth_data.get('up_limit', 0) if breadth_data else 0
    down_limit = breadth_data.get('down_limit', 0) if breadth_data else 0
    
    # 如果 breadth 的漲跌停是 0，嘗試從 limit_updown 表補
    if up_limit == 0 and down_limit == 0:
        db_limits = get_limit_updown_from_db(momentum_data['date'])
        if db_limits:
            up_limit = db_limits['up_limit']
            down_limit = db_limits['down_limit']
    
    if momentum_data:
        cursor.execute(\'\'\'
            INSERT OR REPLACE INTO market_breadth 
            (date, taiex_close, up_count, down_count, unchanged, up_ratio, up_limit, down_limit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        \'\'\', (
            momentum_data['date'],
            momentum_data['close'],
            breadth_data['up_count'] if breadth_data else None,
            breadth_data['down_count'] if breadth_data else None,
            breadth_data['unchanged'] if breadth_data else None,
            breadth_data['up_ratio'] if breadth_data else None,
            up_limit,
            down_limit
        ))
    
    conn.commit()
    conn.close()


def collect_market_breadth():
    """主函數"""
    print("=" * 50)
    print("📊 市場廣度數據收集")
    print("=" * 50)
    
    print("\\n[1/2] 抓取大盤收盤價...")
    momentum_data = get_market_momentum()
    if momentum_data:
        print(f"  ✓ 加權指數: {momentum_data[\'close\']:.2f}")
    else:
        print("  ✗ 動能數據失敗")
        return False
    
    time.sleep(3)  # TWSE rate limit
    
    print("\\n[2/2] 抓取漲跌家數...")
    breadth_data = get_market_breadth()
    if breadth_data:
        print(f"  ✓ 上漲: {breadth_data[\'up_count\']} (漲停: {breadth_data.get(\'up_limit\', 0)})")
        print(f"  ✓ 下跌: {breadth_data[\'down_count\']} (跌停: {breadth_data.get(\'down_limit\', 0)})")
        print(f"  上漲比率: {breadth_data[\'up_ratio\']:.1f}%")
    else:
        print("  ✗ 廣度數據失敗 (非交易時間?)")
    
    print("\\n儲存到資料庫...")
    save_to_database(momentum_data, breadth_data)
    
    print("\\n✓ 市場廣度數據收集完成!")
    return True


if __name__ == '__main__':
    collect_market_breadth()
'''
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("  ✓ 完成")


# ============================================================
# 2. 重寫 market_data_exporter.py
# ============================================================
def patch_exporter():
    path = os.path.join(BACKEND, 'market_data_exporter.py')
    print(f"\n[2/4] 重寫 {path}")
    backup_file(path)
    
    content = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
market_data.json 產生器 v2
從 data/market_data.db 整合融資、期貨、市場廣度、情緒指數，輸出給前端
情緒指數 v2: 7 指標 (價格動能/市場廣度/新高低比 + 融資/期貨/外資/PCR)
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / 'data' / 'market_data.db'
OUTPUT = Path(__file__).parent / 'data' / 'market_data.json'


def get_conn():
    return sqlite3.connect(str(DB_PATH))


def get_latest_margin(conn):
    row = conn.execute(
        'SELECT date, margin_ratio, margin_balance FROM margin_data ORDER BY date DESC LIMIT 1'
    ).fetchone()
    if not row:
        return None
    return {'date': row[0], 'ratio': row[1], 'balance': row[2]}


def get_margin_history(conn, limit=60):
    rows = conn.execute(
        'SELECT date, margin_ratio, margin_balance FROM margin_data ORDER BY date DESC LIMIT ?',
        (limit,)
    ).fetchall()
    return [{'date': r[0], 'ratio': r[1], 'balance': r[2]} for r in reversed(rows)]


def get_latest_futures(conn):
    row = conn.execute(
        \'\'\'SELECT date, long_short_ratio, foreign_net, trust_net, dealer_net,
                  retail_long, retail_short, retail_net, retail_ratio, pcr_volume
           FROM futures_data ORDER BY date DESC LIMIT 1\'\'\'
    ).fetchone()
    if not row:
        return None
    return {
        'date': row[0], 'ratio': row[1],
        'foreign_net': row[2], 'trust_net': row[3], 'dealer_net': row[4],
        'retail_long': row[5], 'retail_short': row[6],
        'retail_net': row[7], 'retail_ratio': row[8], 'pcr_volume': row[9],
    }


def get_futures_history(conn, limit=60):
    rows = conn.execute(
        'SELECT date, long_short_ratio, foreign_net FROM futures_data ORDER BY date DESC LIMIT ?',
        (limit,)
    ).fetchall()
    return [{'date': r[0], 'ratio': r[1], 'foreign_net': r[2]} for r in reversed(rows)]


# ===== 新增: 市場廣度相關讀取 =====

def get_latest_breadth(conn):
    """讀取最新市場廣度資料"""
    row = conn.execute(
        \'\'\'SELECT date, taiex_close, up_count, down_count, unchanged, up_ratio, up_limit, down_limit
           FROM market_breadth ORDER BY date DESC LIMIT 1\'\'\'
    ).fetchone()
    if not row:
        return None
    return {
        'date': row[0], 'close': row[1],
        'up_count': row[2], 'down_count': row[3],
        'unchanged': row[4], 'up_ratio': row[5],
        'up_limit': row[6], 'down_limit': row[7],
    }


def get_price_history(conn, limit=60):
    """讀取大盤收盤價歷史 (算 MA 用)"""
    rows = conn.execute(
        'SELECT date, taiex_close FROM market_breadth WHERE taiex_close IS NOT NULL ORDER BY date DESC LIMIT ?',
        (limit,)
    ).fetchall()
    return [{'date': r[0], 'close': r[1]} for r in rows]  # 注意: DESC, [0]=最新


def get_latest_limit_counts(conn, date_str=None):
    """從 limit_updown 表讀漲跌停家數"""
    try:
        if date_str:
            up = conn.execute(
                "SELECT COUNT(*) FROM limit_updown WHERE date=? AND type='limit_up'",
                (date_str,)
            ).fetchone()[0]
            down = conn.execute(
                "SELECT COUNT(*) FROM limit_updown WHERE date=? AND type='limit_down'",
                (date_str,)
            ).fetchone()[0]
        else:
            # 取最新日期
            row = conn.execute(
                "SELECT date FROM limit_updown ORDER BY date DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            date_str = row[0]
            up = conn.execute(
                "SELECT COUNT(*) FROM limit_updown WHERE date=? AND type='limit_up'",
                (date_str,)
            ).fetchone()[0]
            down = conn.execute(
                "SELECT COUNT(*) FROM limit_updown WHERE date=? AND type='limit_down'",
                (date_str,)
            ).fetchone()[0]
        return {'date': date_str, 'up_limit': up, 'down_limit': down}
    except Exception:
        return None


# ===== 情緒指數 v2 =====

def calc_momentum_score(conn, breadth):
    """價格動能評分 (MA位置 + MA20乖離率)"""
    if not breadth or not breadth.get('close'):
        return None
    
    close = breadth['close']
    prices = get_price_history(conn, 60)
    
    if len(prices) < 5:
        return None
    
    closes = [p['close'] for p in prices]  # [0]=最新, DESC
    
    # 計算 MA
    ma20 = sum(closes[:20]) / min(len(closes), 20) if len(closes) >= 5 else close
    ma60 = sum(closes[:60]) / min(len(closes), 60) if len(closes) >= 20 else ma20
    
    # MA20 方向: 比較今天 MA20 vs 5天前 MA20
    ma20_rising = True
    if len(closes) >= 25:
        ma20_5d_ago = sum(closes[5:25]) / 20
        ma20_rising = ma20 > ma20_5d_ago
    
    # MA20 乖離率
    deviation = ((close - ma20) / ma20) * 100 if ma20 > 0 else 0
    
    # 基礎分數: MA 位置
    if close > ma20 and ma20_rising:
        base = 75
    elif close > ma20 and not ma20_rising:
        base = 60
    elif close > ma60:
        base = 40
    else:
        base = 20
    
    # 乖離率修正: 每 1% 乖離 +/- 3 分, 上限 +/- 15
    deviation_adj = max(-15, min(15, deviation * 3))
    
    score = max(5, min(95, base + deviation_adj))
    
    return {
        'score': round(score),
        'close': close,
        'ma20': round(ma20, 1),
        'ma60': round(ma60, 1),
        'ma20_rising': ma20_rising,
        'deviation': round(deviation, 2),
    }


def calc_breadth_score(breadth):
    """市場廣度評分 (漲跌家數比)"""
    if not breadth or breadth.get('up_ratio') is None:
        return None
    
    r = breadth['up_ratio']
    if r >= 70:
        score = 85
    elif r >= 60:
        score = 70
    elif r >= 40:
        score = 50
    elif r >= 30:
        score = 30
    else:
        score = 15
    
    return {
        'score': score,
        'up_count': breadth.get('up_count'),
        'down_count': breadth.get('down_count'),
        'up_ratio': round(r, 1),
    }


def calc_highlowlimit_score(breadth, limit_data):
    """新高低比評分 (用漲跌停家數近似)"""
    up_limit = 0
    down_limit = 0
    
    # 優先用 breadth 裡的漲跌停
    if breadth and breadth.get('up_limit'):
        up_limit = breadth['up_limit']
        down_limit = breadth.get('down_limit', 0)
    
    # 補充: 從 limit_updown 表
    if up_limit == 0 and down_limit == 0 and limit_data:
        up_limit = limit_data.get('up_limit', 0)
        down_limit = limit_data.get('down_limit', 0)
    
    if up_limit == 0 and down_limit == 0:
        return None
    
    # 評分邏輯
    if up_limit > 20 and down_limit < 5:
        score = 85
    elif up_limit > 0 and (down_limit == 0 or up_limit > down_limit * 2):
        score = 70
    elif down_limit > 0 and (up_limit == 0 or down_limit > up_limit * 2):
        score = 30
    elif down_limit > 20 and up_limit < 5:
        score = 15
    else:
        score = 50
    
    return {
        'score': score,
        'up_limit': up_limit,
        'down_limit': down_limit,
    }


def calc_sentiment(margin, futures, conn):
    """計算台股情緒指數 v2 (0-100), 7 指標"""
    components = {}
    weights_used = 0
    
    # ===== 價格類 (45%) =====
    
    # 1. 價格動能 (20%)
    breadth = get_latest_breadth(conn)
    momentum = calc_momentum_score(conn, breadth)
    if momentum:
        components['momentum'] = {
            'score': momentum['score'], 'weight': 0.20, 'desc': '價格動能',
            'detail': f"收盤{momentum['close']:.0f} MA20={momentum['ma20']:.0f} 乖離{momentum['deviation']:+.1f}%"
        }
        weights_used += 0.20
    
    # 2. 市場廣度 (15%)
    breadth_score = calc_breadth_score(breadth)
    if breadth_score:
        components['breadth'] = {
            'score': breadth_score['score'], 'weight': 0.15, 'desc': '市場廣度',
            'detail': f"漲{breadth_score['up_count']} 跌{breadth_score['down_count']} 比率{breadth_score['up_ratio']}%"
        }
        weights_used += 0.15
    
    # 3. 新高低比 (10%)
    limit_data = get_latest_limit_counts(conn, breadth['date'] if breadth else None)
    hl_score = calc_highlowlimit_score(breadth, limit_data)
    if hl_score:
        components['strength'] = {
            'score': hl_score['score'], 'weight': 0.10, 'desc': '新高低比',
            'detail': f"漲停{hl_score['up_limit']} 跌停{hl_score['down_limit']}"
        }
        weights_used += 0.10
    
    # ===== 籌碼類 (55%) =====
    
    # 4. 融資使用率 (15%)
    if margin and margin.get('ratio'):
        r = margin['ratio']
        if r >= 70:
            score = 90
        elif r >= 65:
            score = 75
        elif r >= 60:
            score = 60
        elif r >= 55:
            score = 45
        elif r >= 50:
            score = 30
        else:
            score = 15
        components['margin'] = {
            'score': score, 'weight': 0.15, 'desc': '融資使用率',
            'detail': f"{r:.1f}%"
        }
        weights_used += 0.15

    # 5. 期貨多空比 (15%)
    if futures and futures.get('ratio'):
        r = futures['ratio']
        if r >= 1.15:
            score = 85
        elif r >= 1.05:
            score = 70
        elif r >= 0.95:
            score = 50
        elif r >= 0.85:
            score = 30
        else:
            score = 15
        components['futures'] = {
            'score': score, 'weight': 0.15, 'desc': '期貨多空比',
            'detail': f"{r:.2f}"
        }
        weights_used += 0.15

    # 6. 外資淨部位 (10%)
    if futures and futures.get('foreign_net') is not None:
        fn = futures['foreign_net']
        if fn > 20000:
            score = 85
        elif fn > 5000:
            score = 70
        elif fn > -5000:
            score = 50
        elif fn > -20000:
            score = 30
        else:
            score = 15
        components['foreign'] = {
            'score': score, 'weight': 0.10, 'desc': '外資淨部位',
            'detail': f"{fn:+,.0f}"
        }
        weights_used += 0.10

    # 7. PCR (15%)
    if futures and futures.get('pcr_volume'):
        pcr = futures['pcr_volume']
        if pcr >= 1.5:
            score = 25
        elif pcr >= 1.2:
            score = 40
        elif pcr >= 0.8:
            score = 55
        elif pcr >= 0.5:
            score = 70
        else:
            score = 85
        components['pcr'] = {
            'score': score, 'weight': 0.15, 'desc': 'Put/Call比',
            'detail': f"{pcr:.2f}"
        }
        weights_used += 0.15

    if weights_used == 0:
        return None

    # 加權平均 (動態正規化)
    total = sum(c['score'] * c['weight'] for c in components.values())
    score = round(total / weights_used)

    if score >= 75:
        rating = '極度貪婪'
    elif score >= 60:
        rating = '貪婪'
    elif score >= 45:
        rating = '中性'
    elif score >= 30:
        rating = '恐懼'
    else:
        rating = '極度恐懼'

    return {
        'score': score,
        'rating': rating,
        'components': components,
        'available_weight': round(weights_used, 2),
    }


def get_us_fear_greed():
    """即時抓取美股恐懼貪婪指數"""
    try:
        from scraper_us_sentiment import USFearGreedScraper
        scraper = USFearGreedScraper()
        data = scraper.fetch_current_index()
        if data and data.get('score') is not None:
            score = round(data['score'])
            return {
                'score': score,
                'rating': data.get('rating', 'N/A').upper(),
                'previous_close': round(data.get('previous_close', 0)),
                'previous_week': round(data.get('previous_week', 0)),
                'previous_month': round(data.get('previous_month', 0)),
            }
    except Exception as e:
        print(f"  ⚠ 美股指數抓取失敗: {e}")
    return {'score': None, 'rating': 'N/A', 'previous_close': None}


def export():
    print("=" * 50)
    print("market_data.json 產生器 v2")
    print("=" * 50)

    conn = get_conn()

    margin = get_latest_margin(conn)
    futures = get_latest_futures(conn)
    margin_hist = get_margin_history(conn, 15)
    futures_hist = get_futures_history(conn, 15)
    breadth = get_latest_breadth(conn)

    print(f"  融資: {margin['date'] if margin else 'N/A'} ratio={margin['ratio'] if margin else 'N/A'}")
    print(f"  期貨: {futures['date'] if futures else 'N/A'} ratio={futures['ratio'] if futures else 'N/A'}")
    print(f"  廣度: {breadth['date'] if breadth else 'N/A'} up_ratio={breadth['up_ratio'] if breadth else 'N/A'}")
    print(f"  融資歷史: {len(margin_hist)} 筆")
    print(f"  期貨歷史: {len(futures_hist)} 筆")

    tw_sentiment = calc_sentiment(margin, futures, conn)
    us_sentiment = get_us_fear_greed()

    output = {
        'latest': {
            'margin': margin,
            'futures': futures,
            'breadth': breadth,
        },
        'sentiment': {
            'taiwan': tw_sentiment,
            'us': us_sentiment,
        },
        'history': {
            'margin': margin_hist,
            'futures': futures_hist,
        },
        'updated_at': datetime.now().isoformat(),
    }

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    conn.close()

    score_str = f"{tw_sentiment['score']} ({tw_sentiment['rating']})" if tw_sentiment else 'N/A'
    print(f"\\n✓ 已輸出: {OUTPUT}")
    print(f"  台股情緒: {score_str}")
    if tw_sentiment:
        print(f"  啟用指標: {len(tw_sentiment['components'])} 個 (權重覆蓋 {tw_sentiment['available_weight']*100:.0f}%)")
        for k, v in tw_sentiment['components'].items():
            print(f"    {v['desc']}: {v['score']} ({v.get('detail', '')})")
    return True


if __name__ == '__main__':
    export()
'''
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("  ✓ 完成")


# ============================================================
# 3. 修改 run_daily.py — 在 exporter 前加入 breadth collector
# ============================================================
def patch_run_daily():
    path = os.path.join(BACKEND, 'run_daily.py')
    print(f"\n[3/4] 修改 {path}")
    backup_file(path)
    
    content = open(path, 'r', encoding='utf-8').read()
    
    # 在 market_data_exporter 之前插入 breadth collector
    marker = '    print("\\n[9/9] 產生 market_data.json...")'
    
    breadth_step = '''    print("\\n[9/10] 收集市場廣度數據...")
    try:
        result = subprocess.run(["python3", "market_breadth_collector.py"],
                              capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print("  ✓ 完成")
        else:
            print(f"  ✗ 失敗: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")

    print("\\n[10/10] 產生 market_data.json...")'''
    
    if marker in content:
        content = content.replace(marker, breadth_step)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("  ✓ 完成 (在 exporter 前加入 breadth collector)")
    else:
        # 嘗試其他格式
        marker2 = '    print("\\n[9/9] \\xe7\\x94\\xa2\\xe7\\x94\\x9f market_data.json...")'
        if marker2 in content:
            content = content.replace(marker2, breadth_step)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            print("  ✓ 完成 (在 exporter 前加入 breadth collector)")
        else:
            print("  ⚠ 找不到插入點，請手動加入")
            print(f"  搜尋: [9/9] 產生 market_data.json")


# ============================================================
# 4. 修改 dashboard.html — 更新前端
# ============================================================
def patch_dashboard():
    print(f"\n[4/4] 修改 {DASHBOARD}")
    backup_file(DASHBOARD)
    
    content = open(DASHBOARD, 'r', encoding='utf-8').read()
    changes = 0
    
    # 4a. 移除「待實作」標記
    for name in ['價格動能', '市場廣度', '新高低比']:
        old = f'{name} <span style="font-size:11px;color:rgba(255,255,255,0.4)">(待實作)</span>'
        if old in content:
            content = content.replace(old, name)
            changes += 1
    
    # 4b. 移除 opacity:0.3 (待實作的灰色樣式)
    for comp_id in ['comp-momentum', 'comp-breadth', 'comp-strength']:
        old_style = f'id="{comp_id}" style="opacity:0.3"'
        new_style = f'id="{comp_id}"'
        if old_style in content:
            content = content.replace(old_style, new_style)
            changes += 1
    
    # 4c. 更新權重顯示面板
    old_weights = '''                    <div class="weight-group">
                        <div class="weight-title">啟用中</div>
                        <div class="weight-item"><span>融資使用率</span><span>27%</span></div>
                        <div class="weight-item"><span>期貨多空比</span><span>27%</span></div>
                        <div class="weight-item"><span>外資淨部位</span><span>27%</span></div>
                        <div class="weight-item"><span>Put/Call比</span><span>19%</span></div>
                    </div>
                    <div class="weight-group">
                        <div class="weight-title" style="color: rgba(255,255,255,0.4)">待實作</div>
                        <div class="weight-item" style="opacity:0.4"><span>價格動能</span><span>--</span></div>
                        <div class="weight-item" style="opacity:0.4"><span>市場廣度</span><span>--</span></div>
                        <div class="weight-item" style="opacity:0.4"><span>新高低比</span><span>--</span></div>
                    </div>'''
    
    new_weights = '''                    <div class="weight-group">
                        <div class="weight-title">價格類 (45%)</div>
                        <div class="weight-item"><span>價格動能</span><span>20%</span></div>
                        <div class="weight-item"><span>市場廣度</span><span>15%</span></div>
                        <div class="weight-item"><span>新高低比</span><span>10%</span></div>
                    </div>
                    <div class="weight-group">
                        <div class="weight-title">籌碼類 (55%)</div>
                        <div class="weight-item"><span>融資使用率</span><span>15%</span></div>
                        <div class="weight-item"><span>期貨多空比</span><span>15%</span></div>
                        <div class="weight-item"><span>外資淨部位</span><span>10%</span></div>
                        <div class="weight-item"><span>Put/Call比</span><span>15%</span></div>
                    </div>'''
    
    if old_weights in content:
        content = content.replace(old_weights, new_weights)
        changes += 1
    
    # 4d. 更新指標說明裡的待實作標記
    for name in ['價格動能', '市場廣度', '新高低比']:
        old_indicator = f'{name} <span style="font-size:11px;color:rgba(255,255,255,0.4)">(待實作)</span>'
        if old_indicator in content:
            content = content.replace(old_indicator, name)
            changes += 1
    
    with open(DASHBOARD, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"  ✓ 完成 ({changes} 處修改)")


# ============================================================
# 主程序
# ============================================================
if __name__ == '__main__':
    print("=" * 60)
    print("🚀 台股情緒指數 v2 升級")
    print("=" * 60)
    print(f"時間: {datetime.now()}")
    print(f"Backend: {BACKEND}")
    print(f"Dashboard: {DASHBOARD}")
    
    patch_breadth_collector()
    patch_exporter()
    patch_run_daily()
    patch_dashboard()
    
    print("\n" + "=" * 60)
    print("✅ 全部完成!")
    print("=" * 60)
    print("""
下一步:
1. cd ~/MyStock/backend && python3 market_breadth_collector.py  (測試抓資料)
2. python3 market_data_exporter.py  (測試情緒指數計算)
3. 確認 dashboard 顯示正常
4. git add -A && git commit -m "feat: 情緒指數 v2 - 新增價格動能/市場廣度/新高低比" && git push
""")
