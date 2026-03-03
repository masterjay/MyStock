#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
market_data.json 產生器
從 data/market_data.db 整合融資、期貨、情緒指數，輸出給前端
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


def calc_sentiment(margin, futures):
    """計算台股情緒指數 (0-100)"""
    components = {}
    weights_used = 0

    # 融資使用率 (反向: 高=貪婪)
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
        components['margin'] = {'score': score, 'weight': 0.15, 'desc': '融資使用率'}
        weights_used += 0.15

    # 期貨多空比
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
        components['futures'] = {'score': score, 'weight': 0.15, 'desc': '期貨多空比'}
        weights_used += 0.15

    # 外資淨部位
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
        components['foreign'] = {'score': score, 'weight': 0.15, 'desc': '外資淨部位'}
        weights_used += 0.15

    # PCR
    if futures and futures.get('pcr_volume'):
        pcr = futures['pcr_volume']
        if pcr >= 1.5:
            score = 25  # 多put=恐懼
        elif pcr >= 1.2:
            score = 40
        elif pcr >= 0.8:
            score = 55
        elif pcr >= 0.5:
            score = 70
        else:
            score = 85
        components['pcr'] = {'score': score, 'weight': 0.1, 'desc': 'Put/Call比'}
        weights_used += 0.1

    if weights_used == 0:
        return None

    # 加權平均
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
    """嘗試讀取美股恐懼貪婪指數"""
    fg_file = Path(__file__).parent / 'data' / 'fear_greed.json'
    if fg_file.exists():
        try:
            with open(fg_file) as f:
                return json.load(f)
        except:
            pass
    return {'score': None, 'rating': 'N/A', 'previous_close': None}


def export():
    print("=" * 50)
    print("market_data.json 產生器")
    print("=" * 50)

    conn = get_conn()

    margin = get_latest_margin(conn)
    futures = get_latest_futures(conn)
    margin_hist = get_margin_history(conn, 15)
    futures_hist = get_futures_history(conn, 15)

    print(f"  融資: {margin['date'] if margin else 'N/A'} ratio={margin['ratio'] if margin else 'N/A'}")
    print(f"  期貨: {futures['date'] if futures else 'N/A'} ratio={futures['ratio'] if futures else 'N/A'}")
    print(f"  融資歷史: {len(margin_hist)} 筆")
    print(f"  期貨歷史: {len(futures_hist)} 筆")

    tw_sentiment = calc_sentiment(margin, futures)
    us_sentiment = get_us_fear_greed()

    output = {
        'latest': {
            'margin': margin,
            'futures': futures,
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
    return True


if __name__ == '__main__':
    export()
