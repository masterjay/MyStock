#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市場廣度與動能數據收集器
收集: 1. 大盤動能 2. 上漲家數比 3. 創新高低家數
"""

import requests
import sqlite3
from datetime import datetime
import json
import re

def get_market_momentum():
    """取得加權指數動能數據 - 使用 FMTQIK"""
    try:
        url = "https://www.twse.com.tw/exchangeReport/FMTQIK?response=json"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        
        if r.status_code != 200:
            return None
        
        data = r.json()
        
        # FMTQIK 格式: ['115/01/16', '成交股數', '成交金額', '成交筆數', '加權指數', '漲跌']
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
        print(f"✗ 抓取動能失敗: {e}")
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
        
        # 2025新格式: tables[7] = 漲跌證券數合計
        # 格式: ['上漲(漲停)', '8,112(204)', '421(29)']
        if 'tables' in data and len(data['tables']) > 7:
            momentum_table = data['tables'][7]['data']
            
            def parse_count(s):
                match = re.match(r'([\d,]+)\((\d+)\)', s.replace(',', ''))
                if match:
                    return int(match.group(1).replace(',','')), int(match.group(2))
                return int(s.replace(',', '')), 0
            
            # [2] = 股票欄位
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
                'up_ratio': up_ratio,
                'up_limit': up_limit,
                'down_limit': down_limit
            }
        
        return None
        
    except Exception as e:
        print(f"✗ 抓取廣度失敗: {e}")
        return None

def get_new_highs_lows():
    """取得創新高新低家數"""
    try:
        return {
            'date': datetime.now().strftime('%Y%m%d'),
            'new_highs': 0,
            'new_lows': 0,
            'hl_ratio': 50
        }
    except Exception as e:
        print(f"✗ 抓取新高低失敗: {e}")
        return None

def save_to_database(momentum_data, breadth_data, hl_data):
    """儲存到資料庫"""
    conn = sqlite3.connect('market_data.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_breadth (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            taiex_close REAL,
            up_count INTEGER,
            down_count INTEGER,
            unchanged INTEGER,
            up_ratio REAL,
            new_highs INTEGER,
            new_lows INTEGER,
            hl_ratio REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    if momentum_data and breadth_data:
        cursor.execute('''
            INSERT OR REPLACE INTO market_breadth 
            (date, taiex_close, up_count, down_count, unchanged, up_ratio, new_highs, new_lows, hl_ratio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            momentum_data['date'],
            momentum_data['close'],
            breadth_data['up_count'],
            breadth_data['down_count'],
            breadth_data['unchanged'],
            breadth_data['up_ratio'],
            hl_data['new_highs'] if hl_data else 0,
            hl_data['new_lows'] if hl_data else 0,
            hl_data['hl_ratio'] if hl_data else 50
        ))
    
    conn.commit()
    conn.close()

def calculate_momentum_score(close_price):
    """計算動能分數"""
    conn = sqlite3.connect('market_data.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT taiex_close FROM market_breadth 
        ORDER BY date DESC LIMIT 60
    ''')
    
    prices = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    if len(prices) < 20:
        return 50
    
    ma20 = sum(prices[:20]) / 20
    ma60 = sum(prices) / len(prices) if len(prices) >= 60 else ma20
    
    deviation_20 = ((close_price - ma20) / ma20) * 100
    deviation_60 = ((close_price - ma60) / ma60) * 100
    
    score_20 = max(0, min(100, 50 + deviation_20 * 5))
    score_60 = max(0, min(100, 50 + deviation_60 * 5))
    
    momentum_score = (score_20 * 0.6 + score_60 * 0.4)
    return momentum_score

def collect_market_breadth():
    """主函數"""
    print("="*60)
    print("📊 市場廣度與動能數據收集")
    print("="*60)
    
    print("\n[1/3] 抓取大盤動能...")
    momentum_data = get_market_momentum()
    if momentum_data:
        print(f"✓ 加權指數: {momentum_data['close']:.2f}")
    else:
        print("✗ 動能數據失敗")
        return False
    
    print("\n[2/3] 抓取市場廣度...")
    breadth_data = get_market_breadth()
    if breadth_data:
        print(f"✓ 上漲: {breadth_data['up_count']} (漲停: {breadth_data.get('up_limit', 0)})")
        print(f"✓ 下跌: {breadth_data['down_count']} (跌停: {breadth_data.get('down_limit', 0)})")
        print(f"  上漲比率: {breadth_data['up_ratio']:.1f}%")
    else:
        print("✗ 廣度數據失敗")
        return False
    
    print("\n[3/3] 計算新高低...")
    hl_data = get_new_highs_lows()
    print("✓ 新高低數據 (暫時預設)")
    
    print("\n儲存到資料庫...")
    save_to_database(momentum_data, breadth_data, hl_data)
    
    momentum_score = calculate_momentum_score(momentum_data['close'])
    print(f"\n動能分數: {momentum_score:.1f}")
    
    print("\n" + "="*60)
    print("✓ 市場廣度數據收集完成!")
    print("="*60)
    
    return True

if __name__ == '__main__':
    collect_market_breadth()
