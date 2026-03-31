#!/usr/bin/env python3
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
                match = re.match(r'([\d,]+)\((\d+)\)', s.replace(',', ''))
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
    
    cursor.execute('''
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
    ''')
    
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
        cursor.execute('''
            INSERT OR REPLACE INTO market_breadth 
            (date, taiex_close, up_count, down_count, unchanged, up_ratio, up_limit, down_limit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
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
    
    print("\n[1/2] 抓取大盤收盤價...")
    momentum_data = get_market_momentum()
    if momentum_data:
        print(f"  ✓ 加權指數: {momentum_data['close']:.2f}")
    else:
        print("  ✗ 動能數據失敗")
        return False
    
    time.sleep(3)  # TWSE rate limit
    
    print("\n[2/2] 抓取漲跌家數...")
    breadth_data = get_market_breadth()
    if breadth_data:
        print(f"  ✓ 上漲: {breadth_data['up_count']} (漲停: {breadth_data.get('up_limit', 0)})")
        print(f"  ✓ 下跌: {breadth_data['down_count']} (跌停: {breadth_data.get('down_limit', 0)})")
        print(f"  上漲比率: {breadth_data['up_ratio']:.1f}%")
    else:
        print("  ✗ 廣度數據失敗 (非交易時間?)")
    
    print("\n儲存到資料庫...")
    save_to_database(momentum_data, breadth_data)
    
    print("\n✓ 市場廣度數據收集完成!")
    return True


if __name__ == '__main__':
    collect_market_breadth()
