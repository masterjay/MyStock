"""
從證交所外資買賣超數據補充產業分類
"""
import requests
import sqlite3
from datetime import datetime, timedelta

def get_industry_from_twse():
    """從證交所外資買賣超取得產業分類"""
    print("從證交所取得產業分類...")
    
    # 嘗試最近幾天的資料
    for days_ago in range(10):
        date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y%m%d')
        
        url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date}&selectType=ALL&response=json"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            data = resp.json()
            
            if data.get('stat') == 'OK' and data.get('data'):
                print(f"  ✓ 使用 {date} 的資料")
                
                industry_map = {}
                for row in data['data']:
                    if len(row) >= 3:
                        code = row[0].strip()
                        name = row[1].strip()
                        industry = row[2].strip() if len(row) > 2 else '其他'
                        
                        # 只要 4 位數字的股票代碼
                        if len(code) == 4 and code.isdigit():
                            industry_map[code] = industry
                
                print(f"  ✓ 找到 {len(industry_map)} 檔股票的產業分類")
                return industry_map
                
        except Exception as e:
            continue
    
    print("  ✗ 無法取得資料")
    return {}

def update_database(industry_map):
    """更新資料庫"""
    if not industry_map:
        return
    
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
    
    print(f"\n✓ 已更新 {updated} 檔股票的產業分類")
    
    # 統計
    conn = sqlite3.connect('data/market_data.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT industry, COUNT(*) FROM stock_master GROUP BY industry ORDER BY COUNT(*) DESC')
    industries = cursor.fetchall()
    
    print(f"\n產業分布 (共 {len(industries)} 個產業):")
    for ind, count in industries[:15]:
        print(f"  {ind}: {count} 檔")
    
    if len(industries) > 15:
        print(f"  ... 還有 {len(industries) - 15} 個產業")
    
    conn.close()

if __name__ == '__main__':
    print("\n=== 補充股票產業分類 ===\n")
    
    # 從證交所取得產業分類
    industry_map = get_industry_from_twse()
    
    if industry_map:
        # 更新資料庫
        update_database(industry_map)
        
        # 重新匯出 JSON
        print("\n重新匯出 JSON...")
        import sys
        sys.path.insert(0, '.')
        from stock_master_collector_v2 import StockMasterCollector
        
        conn = sqlite3.connect('data/market_data.db')
        cursor = conn.cursor()
        cursor.execute('SELECT stock_id, stock_name, industry, market FROM stock_master')
        rows = cursor.fetchall()
        conn.close()
        
        stocks = [
            {
                'stock_id': row[0],
                'stock_name': row[1],
                'industry': row[2],
                'market': row[3]
            }
            for row in rows
        ]
        
        collector = StockMasterCollector()
        collector.export_to_json(stocks)
        
        print("\n" + "="*60)
        print("✓ 產業分類補充完成!")
        print("="*60)
    else:
        print("\n✗ 無法取得產業資料")

