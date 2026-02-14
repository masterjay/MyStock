"""
修正外資買賣超收集器 - 確保數值正確
"""
import requests
from datetime import datetime, timedelta
import json
import sqlite3

print("=== 重新收集外資買賣超 ===\n")

# 讀取股票主檔
conn = sqlite3.connect('data/market_data.db')
cursor = conn.cursor()
cursor.execute('SELECT stock_id, industry FROM stock_master')
stock_industry = {row[0]: row[1] for row in cursor.fetchall()}

# 嘗試最近幾天
for days_ago in range(10):
    date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y%m%d')
    
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date}&selectType=ALL&response=json"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        data = resp.json()
        
        if data.get('stat') == 'OK' and data.get('data'):
            print(f"使用日期: {date}")
            
            stocks = []
            for row in data['data']:
                if len(row) < 5:
                    continue
                
                code = row[0].strip()
                name = row[1].strip()
                
                # 只要 4 位數字
                if len(code) != 4 or not code.isdigit():
                    continue
                
                # 外資買賣超（row[4]）單位：千股
                try:
                    net_raw = row[4].replace(',', '').replace('，', '')
                    net = float(net_raw) if net_raw and net_raw != '--' else 0
                    
                    # 轉換為億（千股 / 1,000,000）
                    net_billion = net / 1000
                    
                    # 漲跌幅（需要從其他API或資料庫取得，這裡暫時設為 0）
                    change = 0
                    
                    stocks.append({
                        'code': code,
                        'name': name,
                        'net': round(net_billion, 2),  # 億
                        'change': change,  # %
                        'industry': stock_industry.get(code, '其他')
                    })
                except:
                    continue
            
            # 排序
            stocks.sort(key=lambda x: x['net'], reverse=True)
            
            # 分為買超和賣超
            top_buy = [s for s in stocks if s['net'] > 0][:50]
            top_sell = [s for s in stocks if s['net'] < 0][:50]
            
            print(f"買超: {len(top_buy)} 檔")
            print(f"賣超: {len(top_sell)} 檔")
            
            # 輸出
            output = {
                'updated_at': datetime.now().isoformat(),
                'date': date,
                'top_buy': top_buy,
                'top_sell': top_sell
            }
            
            with open('data/foreign_top_stocks.json', 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            
            print(f"\n✓ 已輸出")
            
            # 顯示前5
            print("\n買超前5:")
            for s in top_buy[:5]:
                print(f"  {s['code']} {s['name']}: {s['net']:+.2f}億")
            
            conn.close()
            break
            
    except Exception as e:
        continue

print("\n✓ 完成")

