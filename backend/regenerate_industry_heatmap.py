"""
重新生成產業熱力圖數據 - 使用正確的股票主檔
"""
import json
import sqlite3
from datetime import datetime

def generate_industry_heatmap():
    """生成產業熱力圖數據"""
    print("\n=== 生成產業熱力圖數據 ===\n")
    
    # 1. 讀取股票主檔
    print("[1/3] 讀取股票主檔...")
    conn = sqlite3.connect('data/market_data.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT stock_id, stock_name, industry FROM stock_master')
    rows = cursor.fetchall()
    
    stock_map = {row[0]: {'name': row[1], 'industry': row[2]} for row in rows}
    print(f"  ✓ 已載入 {len(stock_map)} 檔股票")
    
    # 2. 讀取外資買賣超數據
    print("\n[2/3] 讀取外資買賣超...")
    cursor.execute('''
        SELECT stock_id, stock_name, foreign_net, change_pct, industry
        FROM foreign_top_stocks 
        ORDER BY foreign_net DESC
    ''')
    
    stocks_data = cursor.fetchall()
    conn.close()
    
    print(f"  ✓ 已取得 {len(stocks_data)} 檔股票")
    
    # 3. 依產業彙總
    print("\n[3/3] 依產業彙總...")
    industries = {}
    
    for stock_id, stock_name, foreign_net, change_pct, db_industry in stocks_data:
        # 優先使用資料庫的產業分類，否則從主檔取
        industry = db_industry if db_industry else stock_map.get(stock_id, {}).get('industry', '其他')
        
        if not industry or industry == '':
            industry = '其他'
        
        if industry not in industries:
            industries[industry] = {
                'total_net': 0,
                'total_change': 0,
                'stock_count': 0,
                'top_stocks': []
            }
        
        industries[industry]['total_net'] += foreign_net or 0
        industries[industry]['total_change'] += change_pct or 0
        industries[industry]['stock_count'] += 1
        
        # 只保留前10檔
        if len(industries[industry]['top_stocks']) < 10:
            industries[industry]['top_stocks'].append({
                'code': stock_id,
                'name': stock_name,
                'net': foreign_net,
                'change': change_pct
            })
    
    # 計算平均值
    for ind in industries.values():
        if ind['stock_count'] > 0:
            ind['avg_change'] = round(ind['total_change'] / ind['stock_count'], 2)
    
    print(f"  ✓ 涵蓋 {len(industries)} 個產業")
    
    # 輸出
    output = {
        'updated_at': datetime.now().isoformat(),
        'date': datetime.now().strftime('%Y%m%d'),
        'industries': industries
    }
    
    with open('data/industry_heatmap.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ 已輸出至 data/industry_heatmap.json")
    
    # 驗證
    print("\n產業分布 Top 10:")
    sorted_ind = sorted(industries.items(), key=lambda x: abs(x[1]['total_net']), reverse=True)
    for i, (ind, data) in enumerate(sorted_ind[:10], 1):
        print(f"  {i:2d}. {ind:15s}: {data['stock_count']:3d} 檔, 淨額 {data['total_net']:+.0f} 張")

if __name__ == '__main__':
    generate_industry_heatmap()
    print("\n✓ 完成！請重新整理網頁")

