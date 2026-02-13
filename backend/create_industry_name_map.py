"""
建立產業代碼對照表
"""
import sqlite3
from datetime import datetime

# 證交所產業分類代碼對照表
INDUSTRY_CODE_MAP = {
    '01': '水泥工業',
    '02': '食品工業', 
    '03': '塑膠工業',
    '04': '紡織纖維',
    '05': '電機機械',
    '06': '電器電纜',
    '08': '玻璃陶瓷',
    '09': '造紙工業',
    '10': '鋼鐵工業',
    '11': '橡膠工業',
    '12': '汽車工業',
    '14': '建材營造',
    '15': '航運業',
    '16': '觀光餐旅',
    '17': '金融保險',
    '18': '貿易百貨',
    '19': '綜合企業',
    '20': '其他',
    '21': '化學工業',
    '22': '生技醫療',
    '23': '油電燃氣',
    '24': '半導體',
    '25': '電腦及週邊',
    '26': '光電',
    '27': '通信網路',
    '28': '電子零組件',
    '29': '電子通路',
    '30': '資訊服務',
    '31': '其他電子',
    '32': '文化創意',
    '33': '農業科技',
    '34': '電子商務',
    '80': '管理股票',
    '99': '其他',
}

def update_industry_names():
    """將產業代碼轉換為產業名稱"""
    print("\n更新產業名稱...")
    
    conn = sqlite3.connect('data/market_data.db')
    cursor = conn.cursor()
    
    updated = 0
    for code, name in INDUSTRY_CODE_MAP.items():
        cursor.execute('''
            UPDATE stock_master 
            SET industry = ?, updated_at = ?
            WHERE industry = ?
        ''', (name, datetime.now().isoformat(), code))
        
        if cursor.rowcount > 0:
            print(f"  {code} → {name}: {cursor.rowcount} 檔")
            updated += cursor.rowcount
    
    conn.commit()
    conn.close()
    
    print(f"\n✓ 已更新 {updated} 檔股票")

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
    
    # 統計產業分布
    print("\n產業分布 Top 10:")
    cursor.execute('''
        SELECT industry, COUNT(*) as cnt 
        FROM stock_master 
        GROUP BY industry 
        ORDER BY cnt DESC 
        LIMIT 10
    ''')
    
    for ind, cnt in cursor.fetchall():
        print(f"  {ind:15s}: {cnt:3d} 檔")
    
    conn.close()

if __name__ == '__main__':
    print("\n" + "="*60)
    print("產業代碼轉換為產業名稱")
    print("="*60)
    
    update_industry_names()
    
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
    
    verify_results()
    
    # 重新收集產業外資流向
    print("\n重新收集產業外資流向...")
    from industry_foreign_flow_collector import collect_industry_foreign_flow
    collect_industry_foreign_flow()
    
    print("\n" + "="*60)
    print("✓ 完成! 產業分類已正確!")
    print("="*60)

