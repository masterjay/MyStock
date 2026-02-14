"""
修正單位轉換
證交所數據：千股
顯示單位：千股（不轉億）
"""
import requests
from datetime import datetime, timedelta
import json
import sqlite3

print("=== 重新收集外資買賣超（修正單位）===\n")

conn = sqlite3.connect('data/market_data.db')
cursor = conn.cursor()
cursor.execute('SELECT stock_id, industry FROM stock_master')
stock_industry = {row[0]: row[1] for row in cursor.fetchall()}

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
                
                if len(code) != 4 or not code.isdigit():
                    continue
                
                try:
                    # 外資買賣超（千股）
                    net_raw = row[4].replace(',', '').replace('，', '')
                    net_thousand = float(net_raw) if net_raw and net_raw != '--' else 0
                    
                    stocks.append({
                        'code': code,
                        'name': name,
                        'net': round(net_thousand, 0),  # 保持千股
                        'change': 0,
                        'industry': stock_industry.get(code, '其他')
                    })
                except:
                    continue
            
            stocks.sort(key=lambda x: x['net'], reverse=True)
            
            top_buy = [s for s in stocks if s['net'] > 0][:50]
            top_sell = [s for s in stocks if s['net'] < 0][:50]
            
            print(f"買超: {len(top_buy)} 檔")
            print(f"賣超: {len(top_sell)} 檔")
            
            output = {
                'updated_at': datetime.now().isoformat(),
                'date': date,
                'top_buy': top_buy,
                'top_sell': top_sell
            }
            
            with open('data/foreign_top_stocks.json', 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            
            print(f"\n✓ 已輸出")
            
            print("\n買超前5:")
            for s in top_buy[:5]:
                # 顯示時轉為億
                net_billion = s['net'] / 1000
                print(f"  {s['code']} {s['name']}: {net_billion:+.2f}億 ({s['net']:,.0f}千股)")
            
            conn.close()
            break
            
    except Exception as e:
        continue

print("\n✓ 完成")

