#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
銅期貨數據收集器 (HG=F - COMEX Copper Futures)
"""

import requests
import sqlite3
from datetime import datetime

def get_copper_data(days=120):
    """取得銅期貨歷史數據"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/HG=F?interval=1d&range=6mo"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        
        if r.status_code != 200:
            print(f"✗ HTTP {r.status_code}")
            return None
        
        data = r.json()
        result = data.get('chart', {}).get('result', [])
        
        if not result:
            print("✗ 無數據")
            return None
        
        meta = result[0].get('meta', {})
        timestamps = result[0].get('timestamp', [])
        quote = result[0].get('indicators', {}).get('quote', [{}])[0]
        
        closes = quote.get('close', [])
        opens = quote.get('open', [])
        highs = quote.get('high', [])
        lows = quote.get('low', [])
        volumes = quote.get('volume', [])
        
        copper_data = {
            'symbol': meta.get('symbol'),
            'currency': meta.get('currency'),
            'current_price': meta.get('regularMarketPrice'),
            'history': []
        }
        
        for i in range(len(timestamps)):
            if closes[i] is not None:
                copper_data['history'].append({
                    'date': datetime.fromtimestamp(timestamps[i]).strftime('%Y-%m-%d'),
                    'open': opens[i],
                    'high': highs[i],
                    'low': lows[i],
                    'close': closes[i],
                    'volume': volumes[i] if volumes[i] else 0
                })
        
        return copper_data
        
    except Exception as e:
        print(f"✗ 錯誤: {e}")
        return None

def save_to_database(copper_data):
    """儲存到資料庫"""
    conn = sqlite3.connect('market_data.db')
    cursor = conn.cursor()
    
    # 建立表格
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS copper_futures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    saved = 0
    for record in copper_data['history']:
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO copper_futures (date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (record['date'], record['open'], record['high'], record['low'], 
                  record['close'], record['volume']))
            saved += 1
        except Exception as e:
            print(f"✗ 儲存 {record['date']} 失敗: {e}")
    
    conn.commit()
    conn.close()
    
    return saved

def export_to_json(copper_data):
    """輸出 JSON"""
    import json
    
    output = {
        'updated_at': datetime.now().isoformat(),
        'symbol': copper_data['symbol'],
        'currency': copper_data['currency'],
        'current_price': copper_data['current_price'],
        'history': copper_data['history'][-120:]  # 只保留最近120天
    }
    
    with open('data/copper_futures.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

def collect_copper_futures():
    """主函數"""
    print("="*60)
    print("📊 銅期貨數據收集 (COMEX Copper Futures - 120日走勢)")
    print("="*60)
    
    print("\n[1/3] 抓取 120 天數據...")
    copper_data = get_copper_data(120)
    
    if not copper_data:
        print("✗ 數據收集失敗")
        return False
    
    print(f"✓ 已取得 {len(copper_data['history'])} 天數據")
    print(f"  當前價格: ${copper_data['current_price']:.3f}")
    
    print("\n[2/3] 儲存到資料庫...")
    saved = save_to_database(copper_data)
    print(f"✓ 已儲存 {saved} 筆數據")
    
    print("\n[3/3] 輸出 JSON...")
    export_to_json(copper_data)
    print("✓ 已輸出: data/copper_futures.json")
    
    print("\n" + "="*60)
    print("✓ 銅期貨數據收集完成!")
    print("="*60)
    
    return True

if __name__ == '__main__':
    collect_copper_futures()
