#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
商品期貨數據收集器
銅 (HG=F) / 黃金 (GC=F) / 原油 (CL=F)
"""

import requests
import sqlite3
import json
from datetime import datetime

COMMODITIES = {
    'copper': {
        'symbol': 'HG=F',
        'name': 'COMEX 銅期貨',
        'name_en': 'Copper Futures',
        'unit': 'USD/lb',
        'table': 'copper_futures'
    },
    'gold': {
        'symbol': 'GC=F',
        'name': 'COMEX 黃金期貨',
        'name_en': 'Gold Futures',
        'unit': 'USD/oz',
        'table': 'gold_futures'
    },
    'silver': {
        'symbol': 'SI=F',
        'name': 'COMEX 白銀期貨',
        'name_en': 'Silver Futures',
        'unit': 'USD/oz',
        'table': 'silver_futures'
    },
    'oil': {
        'symbol': 'CL=F',
        'name': 'WTI 原油期貨',
        'name_en': 'Crude Oil Futures',
        'unit': 'USD/bbl',
        'table': 'oil_futures'
    },
    'steel': {
        'symbol': 'HRC=F',
        'name': '熱軋鋼捲期貨',
        'name_en': 'Hot Rolled Coil Steel Futures',
        'unit': 'USD/ton',
        'table': 'steel_futures'
    }
}

def get_commodity_data(symbol, days=120):
    """取得商品期貨歷史數據"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=6mo"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        
        if r.status_code != 200:
            return None
        
        data = r.json()
        result = data.get('chart', {}).get('result', [])
        
        if not result:
            return None
        
        meta = result[0].get('meta', {})
        timestamps = result[0].get('timestamp', [])
        quote = result[0].get('indicators', {}).get('quote', [{}])[0]
        
        closes = quote.get('close', [])
        opens = quote.get('open', [])
        highs = quote.get('high', [])
        lows = quote.get('low', [])
        
        commodity_data = {
            'symbol': meta.get('symbol'),
            'currency': meta.get('currency'),
            'current_price': meta.get('regularMarketPrice'),
            'history': []
        }
        
        for i in range(len(timestamps)):
            if closes[i] is not None:
                commodity_data['history'].append({
                    'date': datetime.fromtimestamp(timestamps[i]).strftime('%Y-%m-%d'),
                    'open': opens[i],
                    'high': highs[i],
                    'low': lows[i],
                    'close': closes[i]
                })
        
        return commodity_data
        
    except Exception as e:
        print(f"✗ {symbol} 錯誤: {e}")
        return None

def save_to_database(commodity_key, commodity_data):
    """儲存到資料庫"""
    conn = sqlite3.connect('data/market_data.db')
    cursor = conn.cursor()
    
    table_name = COMMODITIES[commodity_key]['table']
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    saved = 0
    for record in commodity_data['history']:
        try:
            cursor.execute(f'''
                INSERT OR REPLACE INTO {table_name} (date, open, high, low, close)
                VALUES (?, ?, ?, ?, ?)
            ''', (record['date'], record['open'], record['high'], record['low'], record['close']))
            saved += 1
        except Exception as e:
            print(f"✗ 儲存失敗: {e}")
    
    conn.commit()
    conn.close()
    
    return saved

def export_to_json(commodity_key, commodity_data):
    """輸出 JSON"""
    info = COMMODITIES[commodity_key]
    
    output = {
        'updated_at': datetime.now().isoformat(),
        'symbol': commodity_data['symbol'],
        'name': info['name'],
        'name_en': info['name_en'],
        'unit': info['unit'],
        'currency': commodity_data['currency'],
        'current_price': commodity_data['current_price'],
        'history': commodity_data['history'][-120:]
    }
    
    filename = f"data/{commodity_key}_futures.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    return filename

def collect_all_commodities():
    """收集所有商品期貨"""
    print("="*60)
    print("📊 商品期貨數據收集")
    print("="*60)
    
    results = {}
    
    for key, info in COMMODITIES.items():
        print(f"\n▶ {info['name']} ({info['symbol']})")
        print("-" * 60)
        
        print(f"[1/3] 抓取 120 天數據...")
        data = get_commodity_data(info['symbol'], 120)
        
        if not data:
            print(f"✗ {info['name']} 數據收集失敗")
            results[key] = False
            continue
        
        print(f"✓ 已取得 {len(data['history'])} 天數據")
        print(f"  當前價格: ${data['current_price']:.2f} {info['unit']}")
        
        print(f"[2/3] 儲存到資料庫...")
        saved = save_to_database(key, data)
        print(f"✓ 已儲存 {saved} 筆數據")
        
        print(f"[3/3] 輸出 JSON...")
        filename = export_to_json(key, data)
        print(f"✓ 已輸出: {filename}")
        
        results[key] = True
    
    print("\n" + "="*60)
    success = sum(results.values())
    total = len(results)
    print(f"✓ 完成! 成功 {success}/{total}")
    print("="*60)
    
    return all(results.values())

if __name__ == '__main__':
    collect_all_commodities()
