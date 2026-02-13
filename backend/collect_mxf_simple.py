#!/usr/bin/env python3
"""簡單的 MXF 歷史數據收集"""
import sqlite3
from datetime import datetime, timedelta
from scraper_taifex import TAIFEXScraper
import time

scraper = TAIFEXScraper()

# 正確的資料庫路徑
conn = sqlite3.connect('data/market_data.db')
cursor = conn.cursor()

# 確認表格存在
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mxf_futures_data'")
if not cursor.fetchone():
    print("✗ mxf_futures_data 表不存在!")
    print("請先執行 upgrade_database.py")
    exit(1)

print("\n收集 MXF 歷史數據 (30 個交易日)")
print("="*60)

# 收集過去 30 個交易日
success = 0
fail = 0
skip = 0
current = datetime(2026, 2, 7)  # 從我們知道有數據的日期開始往前推

for i in range(60):  # 多試幾天以獲得 30 個交易日
    date = current - timedelta(days=i)
    
    # 跳過週末
    if date.weekday() >= 5:
        continue
    
    date_str = date.strftime('%Y/%m/%d')
    date_db = date.strftime('%Y%m%d')
    
    # 檢查是否已有數據
    cursor.execute('SELECT COUNT(*) FROM mxf_futures_data WHERE date = ?', (date_db,))
    if cursor.fetchone()[0] > 0:
        print(f"[{date_str}] ⏭️  已有數據")
        skip += 1
        success += 1  # 計入成功數
        continue
    
    # 收集數據
    print(f"[{date_str}] 收集中...", end=" ", flush=True)
    
    try:
        result = scraper.get_retail_ratio(date_str, 'MXF', debug=False)
        
        if result:
            # 儲存到資料庫
            cursor.execute('''
                INSERT INTO mxf_futures_data (
                    date, commodity_id, close_price, total_oi,
                    dealers_long, dealers_short, dealers_net,
                    trusts_long, trusts_short, trusts_net,
                    foreign_long, foreign_short, foreign_net,
                    institutional_net,
                    retail_long, retail_short, retail_net, retail_ratio,
                    timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                date_db,
                result['commodity_id'],
                result.get('close_price', 0),
                result['total_oi'],
                result['dealers']['long'],
                result['dealers']['short'],
                result['dealers']['net'],
                result['trusts']['long'],
                result['trusts']['short'],
                result['trusts']['net'],
                result['foreign']['long'],
                result['foreign']['short'],
                result['foreign']['net'],
                result['institutional_net'],
                result['retail_long'],
                result['retail_short'],
                result['retail_net'],
                result['retail_ratio'],
                result['timestamp']
            ))
            conn.commit()
            
            print(f"✓ (比率: {result['retail_ratio']:.2f}%)")
            success += 1
        else:
            print("✗ (無數據)")
            fail += 1
        
        time.sleep(1.5)  # 避免被封鎖
        
        if success >= 30:
            break
            
    except Exception as e:
        print(f"✗ 錯誤: {str(e)[:50]}")
        fail += 1

conn.close()

print(f"\n{'='*60}")
print(f"收集完成!")
print(f"  成功: {success} 天 (包含 {skip} 天已有數據)")
print(f"  失敗: {fail} 天")
print(f"{'='*60}")

