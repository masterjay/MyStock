#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
周轉率數據收集器
每日抓取成交量 TOP 20 並計算周轉率存入資料庫
"""

import requests
import sqlite3
from datetime import datetime, timedelta

# 產業分類對照表
INDUSTRY_MAP = {
    # 面板
    '2409': '面板', '3481': '面板',
    # PCB
    '2313': 'PCB', '2367': 'PCB', '3715': 'PCB',
    # 半導體
    '2303': '半導體', '8150': '半導體', '6770': '半導體',
    # 被動元件
    '2327': '被動元件',
    # 電源供應器
    '6282': '電源供應',
    # 電線電纜
    '1605': '電線電纜',
    # 其他電子
    '2312': '電子製造', '8110': '電子製造', '9105': '電子製造',
    # 化工
    '1717': '化工',
    # 塑膠
    '1303': '塑化',
    # 金融
    '2887': '金融',
    # 光電
    '6443': '太陽能',
    # 通訊
    '2406': '通訊', '2485': '通訊',
}

def get_industry(code):
    """取得產業分類"""
    return INDUSTRY_MAP.get(code, '其他')

def get_top_volume_stocks(top_n=20):
    """取得成交量 TOP N (剔除 ETF)"""
    try:
        url = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALL"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        data = r.json()
        
        table8 = data['tables'][8]
        stocks = []
        
        for stock in table8['data']:
            code = stock[0]
            name = stock[1]
            volume = stock[2].replace(',', '')
            
            if volume and volume.isdigit():
                # 剔除 ETF/ETN
                is_etf = (
                    code.startswith('00') or 
                    'ETF' in name or 
                    'etf' in name or
                    'ETN' in name
                )
                
                if not is_etf:
                    stocks.append({
                        'code': code,
                        'name': name,
                        'volume': int(volume),
                        'industry': get_industry(code)
                    })
        
        stocks.sort(key=lambda x: x['volume'], reverse=True)
        return stocks[:top_n]
    
    except Exception as e:
        print(f"✗ 抓取成交量失敗: {e}")
        return []

def get_issued_shares():
    """取得所有上市公司發行股數"""
    try:
        url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        data = r.json()
        
        shares_dict = {}
        for item in data:
            code = item.get('公司代號', '')
            shares = item.get('已發行普通股數或TDR原股發行股數', '0')
            if code and shares:
                shares_dict[code] = int(shares)
        
        return shares_dict
    
    except Exception as e:
        print(f"✗ 抓取發行股數失敗: {e}")
        return {}

def save_to_database(date, top_stocks, shares_dict):
    """儲存周轉率資料到資料庫"""
    conn = sqlite3.connect('market_data.db')
    cursor = conn.cursor()
    
    saved_count = 0
    
    for stock in top_stocks:
        code = stock['code']
        name = stock['name']
        volume = stock['volume']
        industry = stock['industry']
        
        issued_shares = shares_dict.get(code, 0)
        
        if issued_shares > 0:
            turnover_rate = (volume / issued_shares) * 100
            
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO turnover_history 
                    (date, stock_code, stock_name, industry, volume, issued_shares, turnover_rate)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (date, code, name, industry, volume, issued_shares, turnover_rate))
                
                saved_count += 1
            
            except Exception as e:
                print(f"✗ 儲存 {code} 失敗: {e}")
    
    conn.commit()
    conn.close()
    
    return saved_count

def clean_old_data(days=30):
    """清理超過N天的舊資料"""
    conn = sqlite3.connect('market_data.db')
    cursor = conn.cursor()
    
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
    
    cursor.execute('DELETE FROM turnover_history WHERE date < ?', (cutoff_date,))
    deleted_count = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    return deleted_count

def collect_turnover_data():
    """主函數:收集周轉率資料"""
    print("="*60)
    print("📊 周轉率數據收集")
    print("="*60)
    
    today = datetime.now().strftime('%Y%m%d')
    print(f"日期: {today}\n")
    
    # Step 1: 抓取成交量 TOP 20
    print("[1/4] 抓取成交量 TOP 20...")
    top_stocks = get_top_volume_stocks(20)
    
    if not top_stocks:
        print("✗ 無法取得成交量資料")
        return False
    
    print(f"✓ 已取得 {len(top_stocks)} 檔股票")
    
    # Step 2: 抓取發行股數
    print("\n[2/4] 抓取發行股數...")
    shares_dict = get_issued_shares()
    
    if not shares_dict:
        print("✗ 無法取得發行股數")
        return False
    
    print(f"✓ 已取得 {len(shares_dict)} 檔股票發行股數")
    
    # Step 3: 儲存到資料庫
    print("\n[3/4] 儲存到資料庫...")
    saved_count = save_to_database(today, top_stocks, shares_dict)
    print(f"✓ 已儲存 {saved_count} 筆資料")
    
    # Step 4: 清理舊資料
    print("\n[4/4] 清理舊資料 (保留30天)...")
    deleted_count = clean_old_data(30)
    print(f"✓ 已刪除 {deleted_count} 筆舊資料")
    
    print("\n" + "="*60)
    print("✓ 周轉率數據收集完成!")
    print("="*60)
    
    return True

if __name__ == '__main__':
    collect_turnover_data()
