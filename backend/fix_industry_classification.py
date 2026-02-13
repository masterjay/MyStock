"""
修正產業分類 - 使用證交所產業分類 API
"""
import requests
import sqlite3
from datetime import datetime

def get_industry_classification():
    """從證交所取得正確的產業分類"""
    print("從證交所取得產業分類...")
    
    # 證交所產業價量統計 API
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?response=json"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        data = resp.json()
        
        if data.get('stat') != 'OK':
            print("  ✗ 無法取得資料")
            return {}
        
        # 解析產業分類
        industry_map = {}
        current_industry = None
        
        for row in data.get('data', []):
            if len(row) < 2:
                continue
            
            code = row[0].strip()
            
            # 如果是產業名稱（不是 4 位數字）
            if not (len(code) == 4 and code.isdigit()):
                # 這可能是產業標題
                if '類指數' not in code and code:
                    current_industry = code
                continue
            
            # 股票代碼
            if current_industry and len(code) == 4 and code.isdigit():
                industry_map[code] = current_industry
        
        print(f"  ✓ 找到 {len(industry_map)} 檔股票的產業分類")
        
        # 顯示產業統計
        industries = {}
        for ind in industry_map.values():
            industries[ind] = industries.get(ind, 0) + 1
        
        print(f"  ✓ 共 {len(industries)} 個產業")
        print("\n  產業分布 Top 10:")
        for ind, count in sorted(industries.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"    {ind}: {count} 檔")
        
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

def export_json():
    """重新匯出 JSON"""
    print("\n重新匯出 JSON...")
    
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
    
    from stock_master_collector_v2 import StockMasterCollector
    collector = StockMasterCollector()
    collector.export_to_json(stocks)

if __name__ == '__main__':
    print("\n=== 修正產業分類 ===\n")
    
    # 取得產業分類
    industry_map = get_industry_classification()
    
    if industry_map:
        # 更新資料庫
        update_database(industry_map)
        
        # 重新匯出
        export_json()
        
        # 驗證結果
        print("\n驗證金融股分類:")
        test_stocks = ['2883', '2887', '2884', '2867']
        for code in test_stocks:
            ind = industry_map.get(code, '未知')
            print(f"  {code}: {ind}")
        
        print("\n" + "="*60)
        print("✓ 產業分類修正完成!")
        print("="*60)
    else:
        print("\n✗ 無法取得產業資料")

