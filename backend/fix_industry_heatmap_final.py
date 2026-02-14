"""
最終修正版 - 確保 JSON 格式正確
"""
import json
import sqlite3
from datetime import datetime

print("=== 重新生成產業熱力圖 JSON ===\n")

# 1. 讀取股票主檔
conn = sqlite3.connect('data/market_data.db')
cursor = conn.cursor()
cursor.execute('SELECT stock_id, industry FROM stock_master')
stock_industry = {row[0]: row[1] for row in cursor.fetchall()}

# 2. 讀取外資買賣超
with open('data/foreign_top_stocks.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

all_stocks = data.get('top_buy', []) + data.get('top_sell', [])

# 3. 依產業彙總
industries = {}

for stock in all_stocks:
    code = stock.get('code', '')
    name = stock.get('name', '')
    net = float(stock.get('net', 0))
    change = float(stock.get('change', 0))
    
    industry = stock_industry.get(code, '其他')
    if not industry:
        industry = '其他'
    
    if industry not in industries:
        industries[industry] = {
            'industry': industry,  # ← 關鍵：加入這個欄位！
            'total_net': 0,
            'total_change': 0,
            'stock_count': 0,
            'top_stocks': [],
            'foreign_net': 0,
            'avg_change': 0
        }
    
    industries[industry]['total_net'] += net
    industries[industry]['total_change'] += change
    industries[industry]['stock_count'] += 1
    industries[industry]['foreign_net'] = industries[industry]['total_net']
    
    if len(industries[industry]['top_stocks']) < 10:
        industries[industry]['top_stocks'].append({
            'code': code,
            'name': name,
            'net': net,
            'change': change,
            'change_pct': change
        })

# 計算平均
for ind_data in industries.values():
    if ind_data['stock_count'] > 0:
        ind_data['avg_change'] = round(ind_data['total_change'] / ind_data['stock_count'], 2)

# 輸出
output = {
    'updated_at': datetime.now().isoformat(),
    'date': data.get('date', datetime.now().strftime('%Y%m%d')),
    'industries': industries
}

with open('data/industry_heatmap.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✓ 已生成 {len(industries)} 個產業")

# 驗證
print("\n驗證金融保險:")
if '金融保險' in industries:
    fin = industries['金融保險']
    print(f"  產業名稱: {fin['industry']}")
    print(f"  股票數: {fin['stock_count']}")
    print(f"  前3檔: {[s['code'] + ' ' + s['name'] for s in fin['top_stocks'][:3]]}")

conn.close()
print("\n✓ 完成！")

