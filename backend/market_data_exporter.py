#!/usr/bin/env python3
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
        '''SELECT date, long_short_ratio, foreign_net, trust_net, dealer_net,
                  retail_long, retail_short, retail_net, retail_ratio, pcr_volume
           FROM futures_data ORDER BY date DESC LIMIT 1'''
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
        '''SELECT date, taiex_close, up_count, down_count, unchanged, up_ratio, up_limit, down_limit
           FROM market_breadth ORDER BY date DESC LIMIT 1'''
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
    
    # 評分邏輯: 用比值判斷
    total = up_limit + down_limit
    if total == 0:
        return None
    up_pct = up_limit / total * 100 if total > 0 else 50
    
    if up_pct >= 80:
        score = 85
    elif up_pct >= 65:
        score = 70
    elif up_pct >= 40:
        score = 50
    elif up_pct >= 20:
        score = 30
    else:
        score = 15
    
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
    print(f"\n✓ 已輸出: {OUTPUT}")
    print(f"  台股情緒: {score_str}")
    if tw_sentiment:
        print(f"  啟用指標: {len(tw_sentiment['components'])} 個 (權重覆蓋 {tw_sentiment['available_weight']*100:.0f}%)")
        for k, v in tw_sentiment['components'].items():
            print(f"    {v['desc']}: {v['score']} ({v.get('detail', '')})")
    return True


if __name__ == '__main__':
    export()
