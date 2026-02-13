"""
產業外資流向收集器 v3
使用股票主檔進行正確的產業分類
"""
import requests
import json
from datetime import datetime, timedelta
import sqlite3

def get_stock_master():
    """從資料庫讀取股票主檔"""
    conn = sqlite3.connect('data/market_data.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT stock_id, stock_name, industry FROM stock_master')
    rows = cursor.fetchall()
    conn.close()
    
    # 建立股票代碼 -> 產業對照表
    stock_industry = {}
    for stock_id, stock_name, industry in rows:
        stock_industry[stock_id] = industry or '其他'
    
    return stock_industry

def collect_industry_foreign_flow():
    """收集產業外資流向"""
    print("\n=== 產業外資流向收集器 v3 ===\n")
    
    # 1. 讀取股票主檔
    print("[1/4] 讀取股票主檔...")
    stock_industry = get_stock_master()
    print(f"  ✓ 已載入 {len(stock_industry)} 檔股票分類")
    
    # 2. 取得外資買賣超資料
    print("\n[2/4] 取得外資買賣超...")
    
    # 嘗試最近幾天
    foreign_data = None
    target_date = None
    
    for days_ago in range(10):
        date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y%m%d')
        
        url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date}&selectType=ALL&response=json"
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            data = resp.json()
            
            if data.get('stat') == 'OK' and data.get('data'):
                foreign_data = data['data']
                target_date = date
                print(f"  ✓ 使用 {date} 的資料")
                break
        except:
            continue
    
    if not foreign_data:
        print("  ✗ 無法取得外資資料")
        return
    
    # 3. 依產業彙總
    print("\n[3/4] 依產業彙總...")
    
    industry_summary = {}
    processed = 0
    
    for row in foreign_data:
        if len(row) < 5:
            continue
        
        code = row[0].strip()
        
        # 只處理 4 位數字的股票
        if len(code) != 4 or not code.isdigit():
            continue
        
        # 取得產業分類
        industry = stock_industry.get(code, '其他')
        
        # 外資買賣超（單位：千股）
        try:
            buy = float(row[3].replace(',', '')) if row[3] != '--' else 0
            sell = float(row[4].replace(',', '')) if row[4] != '--' else 0
            net = buy - sell
        except:
            continue
        
        # 累加到產業
        if industry not in industry_summary:
            industry_summary[industry] = {
                'buy': 0,
                'sell': 0,
                'net': 0,
                'stocks': []
            }
        
        industry_summary[industry]['buy'] += buy
        industry_summary[industry]['sell'] += sell
        industry_summary[industry]['net'] += net
        industry_summary[industry]['stocks'].append(code)
        
        processed += 1
    
    print(f"  ✓ 已處理 {processed} 檔股票")
    print(f"  ✓ 涵蓋 {len(industry_summary)} 個產業")
    
    # 4. 輸出結果
    print("\n[4/4] 輸出結果...")
    
    # 排序（依外資淨買超）
    sorted_industries = sorted(
        industry_summary.items(),
        key=lambda x: x[1]['net'],
        reverse=True
    )
    
    # 顯示 Top 10
    print("\n外資買超 Top 10:")
    for i, (industry, data) in enumerate(sorted_industries[:10], 1):
        net_billion = data['net'] / 1000  # 轉換為億
        print(f"  {i:2d}. {industry:12s}: {net_billion:+8.2f} 億 ({len(data['stocks'])} 檔)")
    
    print("\n外資賣超 Top 10:")
    for i, (industry, data) in enumerate(sorted_industries[-10:][::-1], 1):
        net_billion = data['net'] / 1000
        print(f"  {i:2d}. {industry:12s}: {net_billion:+8.2f} 億 ({len(data['stocks'])} 檔)")
    
    # 輸出 JSON
    output = {
        'date': target_date,
        'updated_at': datetime.now().isoformat(),
        'industries': {
            industry: {
                'buy': round(data['buy'] / 1000, 2),  # 轉為億
                'sell': round(data['sell'] / 1000, 2),
                'net': round(data['net'] / 1000, 2),
                'stock_count': len(data['stocks'])
            }
            for industry, data in industry_summary.items()
        }
    }
    
    with open('data/industry_foreign_flow.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ 已輸出至 data/industry_foreign_flow.json")
    
    print("\n" + "="*60)
    print("✓ 產業外資流向收集完成!")
    print("="*60)

if __name__ == '__main__':
    collect_industry_foreign_flow()

