"""
從 TWSE OpenAPI 取得完整的股票產業分類
"""
import requests
import sqlite3
from datetime import datetime
import time

def get_industry_from_openapi():
    """從證交所 OpenAPI 取得產業分類"""
    print("從證交所 OpenAPI 取得產業分類...\n")
    
    # TWSE OpenAPI - 上市公司基本資料
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        print("正在下載...")
        resp = requests.get(url, headers=headers, timeout=60)
        data = resp.json()
        
        if not data:
            print("  ✗ 無資料")
            return {}
        
        print(f"  ✓ 收到 {len(data)} 筆資料")
        
        # 解析產業分類
        industry_map = {}
        industry_stats = {}
        
        for item in data:
            code = item.get('公司代號', '').strip()
            industry = item.get('產業別', '').strip()
            
            if len(code) == 4 and code.isdigit() and industry:
                industry_map[code] = industry
                industry_stats[industry] = industry_stats.get(industry, 0) + 1
        
        print(f"  ✓ 找到 {len(industry_map)} 檔股票")
        print(f"  ✓ 共 {len(industry_stats)} 個產業\n")
        
        # 顯示產業統計
        print("產業分布 Top 15:")
        for i, (ind, count) in enumerate(sorted(industry_stats.items(), key=lambda x: x[1], reverse=True)[:15], 1):
            print(f"  {i:2d}. {ind:20s}: {count:3d} 檔")
        
        return industry_map
        
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")
        import traceback
        traceback.print_exc()
        return {}

def update_database(industry_map):
    """更新資料庫"""
    if not industry_map:
        return
    
    print(f"\n更新資料庫...")
    
    conn = sqlite3.connect('data/market_data.db')
    cursor = conn.cursor()
    
    updated = 0
    for code, industry in industry_map.items():
        cursor.execute('''
            UPDATE stock_master 
            SET industry = ?, updated_at = ?
            WHERE stock_id = ?
        ''', (industry, datetime.now().isoformat(), code))
        
        if cursor.rowcount > 0:
            updated += 1
    
    conn.commit()
    conn.close()
    
    print(f"  ✓ 已更新 {updated} 檔股票")

def verify_results():
    """驗證結果"""
    print("\n驗證金融股分類:")
    
    conn = sqlite3.connect('data/market_data.db')
    cursor = conn.cursor()
    
    test_stocks = ['2883', '2887', '2884', '2867', '2866', '2880', '2892', '2801']
    
    for code in test_stocks:
        cursor.execute('SELECT stock_name, industry FROM stock_master WHERE stock_id = ?', (code,))
        row = cursor.fetchone()
        if row:
            print(f"  {code} {row[0]:10s}: {row[1]}")
    
    conn.close()

if __name__ == '__main__':
    print("\n" + "="*60)
    print("從 TWSE OpenAPI 匯入產業分類")
    print("="*60 + "\n")
    
    # 取得產業分類
    industry_map = get_industry_from_openapi()
    
    if industry_map:
        # 更新資料庫
        update_database(industry_map)
        
        # 重新匯出 JSON
        print("\n重新匯出 JSON...")
        from stock_master_collector_v2 import StockMasterCollector
        
        conn = sqlite3.connect('data/market_data.db')
        cursor = conn.cursor()
        cursor.execute('SELECT stock_id, stock_name, industry, market FROM stock_master')
        rows = cursor.fetchall()
        conn.close()
        
        stocks = [
            {'stock_id': r[0], 'stock_name': r[1], 'industry': r[2], 'market': r[3]}
            for r in rows
        ]
        
        collector = StockMasterCollector()
        collector.export_to_json(stocks)
        
        # 驗證
        verify_results()
        
        # 重新收集產業外資流向
        print("\n重新收集產業外資流向...")
        from industry_foreign_flow_collector import collect_industry_foreign_flow
        collect_industry_foreign_flow()
        
        print("\n" + "="*60)
        print("✓ 完成!")
        print("="*60)
    else:
        print("\n✗ 無法取得產業資料")

