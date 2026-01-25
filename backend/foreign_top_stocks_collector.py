#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
外資買賣超個股排行收集器
"""

import requests
import sqlite3
from datetime import datetime, timedelta
import json

def get_foreign_top_stocks_by_date(date_str):
    """取得指定日期的外資買賣超"""
    try:
        # 加上 selectType=ALL 取得所有股票
        url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=ALL"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=15)
        
        if r.status_code != 200:
            return None
        
        data = r.json()
        
        if 'data' not in data or not data['data']:
            return None
        
        # 解析數據
        stocks = []
        for row in data['data']:
            try:
                code = row[0].strip()
                name = row[1].strip()
                
                # 外陸資買賣超 (不含自營)
                foreign_net = int(row[4].replace(',', '')) if row[4] else 0
                
                # 過濾條件: 排除 ETF 且有外資交易
                is_etf = (code.startswith('00') or 
                         'ETF' in name.upper() or 
                         '元大' in name or 
                         '復華' in name or 
                         '國泰' in name or
                         '富邦' in name or
                         '永豐' in name)
                
                # 只保留非 ETF 且有外資交易的股票
                if not is_etf and foreign_net != 0:
                    stock = {
                        'code': code,
                        'name': name,
                        'foreign_buy': int(row[2].replace(',', '')) if row[2] else 0,
                        'foreign_sell': int(row[3].replace(',', '')) if row[3] else 0,
                        'foreign_net': foreign_net,
                        'trust_net': int(row[10].replace(',', '')) if len(row) > 10 and row[10] else 0,
                        'dealer_net': int(row[11].replace(',', '')) if len(row) > 11 and row[11] else 0,
                        'total_net': int(row[18].replace(',', '')) if len(row) > 18 and row[18] else 0,
                    }
                    stocks.append(stock)
            except Exception as e:
                continue
        
        return stocks
        
    except Exception as e:
        print(f"✗ 錯誤: {e}")
        return None

def save_to_database(stocks):
    """儲存到資料庫"""
    conn = sqlite3.connect('market_data.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS foreign_top_stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            foreign_buy INTEGER,
            foreign_sell INTEGER,
            foreign_net INTEGER,
            trust_net INTEGER,
            dealer_net INTEGER,
            total_net INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, code)
        )
    ''')
    
    today = datetime.now().strftime('%Y%m%d')
    saved = 0
    
    for stock in stocks:
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO foreign_top_stocks 
                (date, code, name, foreign_buy, foreign_sell, foreign_net,
                 trust_net, dealer_net, total_net)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (today, stock['code'], stock['name'], 
                  stock['foreign_buy'], stock['foreign_sell'], stock['foreign_net'],
                  stock['trust_net'], stock['dealer_net'], stock['total_net']))
            saved += 1
        except Exception as e:
            print(f"✗ 儲存 {stock['code']} 失敗: {e}")
    
    conn.commit()
    conn.close()
    
    return saved

def export_to_json(stocks):
    """輸出 JSON - 只輸出前50名買超和賣超"""
    # 按外資淨買賣超排序
    sorted_stocks = sorted(stocks, key=lambda x: x['foreign_net'], reverse=True)
    
    # 前50買超
    top_buy = sorted_stocks[:50]
    
    # 前50賣超
    top_sell = sorted(stocks, key=lambda x: x['foreign_net'])[:50]
    
    output = {
        'updated_at': datetime.now().isoformat(),
        'date': datetime.now().strftime('%Y%m%d'),
        'top_buy': top_buy,
        'top_sell': top_sell
    }
    
    with open('data/foreign_top_stocks.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

def collect_foreign_top_stocks():
    """主函數"""
    print("="*60)
    print("📊 外資買賣超個股排行收集")
    print("="*60)
    
    print("\n[1/3] 抓取外資買賣超數據...")
    
    # 嘗試最近3天的數據
    stocks = None
    
    for i in range(3):
        date = datetime.now() - timedelta(days=i)
        date_str = date.strftime('%Y%m%d')
        
        print(f"  嘗試 {date_str}...")
        stocks = get_foreign_top_stocks_by_date(date_str)
        
        if stocks and len(stocks) > 10:
            print(f"  ✓ {date_str} 有 {len(stocks)} 檔股票")
            break
    
    if not stocks:
        print("✗ 數據收集失敗")
        return False
    
    print(f"✓ 已取得 {len(stocks)} 檔股票 (已排除 ETF)")
    
    # 顯示前5買超
    top5 = sorted(stocks, key=lambda x: x['foreign_net'], reverse=True)[:5]
    print("\n前5買超:")
    for i, s in enumerate(top5, 1):
        print(f"  {i}. {s['code']} {s['name']}: {s['foreign_net']:,} 張")
    
    print("\n[2/3] 儲存到資料庫...")
    saved = save_to_database(stocks)
    print(f"✓ 已儲存 {saved} 檔股票")
    
    print("\n[3/3] 輸出 JSON...")
    export_to_json(stocks)
    print("✓ 已輸出: data/foreign_top_stocks.json")
    
    print("\n" + "="*60)
    print("✓ 外資買賣超排行收集完成!")
    print("="*60)
    
    return True

if __name__ == '__main__':
    collect_foreign_top_stocks()
