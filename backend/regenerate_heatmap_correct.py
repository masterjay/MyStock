"""
產業熱力圖 - 正確的單位轉換
"""
import json
import sqlite3
from datetime import datetime

conn = sqlite3.connect('data/market_data.db')
cursor = conn.cursor()
cursor.execute('SELECT stock_id, industry FROM stock_master')
stock_industry = {row[0]: row[1] for row in cursor.fetchall()}

with open('data/foreign_top_stocks.json', 'r') as f:
    data = json.load(f)

all_stocks = data.get('top_buy', []) + data.get('top_sell', [])

industries = {}

for stock in all_stocks:
    code = stock.get('code', '')
    name = stock.get('name', '')
    net = float(stock.get('net', 0))  # 千股
    change = float(stock.get('change', 0))
    
    industry = stock_industry.get(code, '其他')
    if not industry:
        industry = '其他'
    
    if industry not in industries:
        industries[industry] = {
            'industry': industry,
            'total_net': 0,
            'total_change': 0,
            'stock_count': 0,
            'top_stocks': [],
            'foreign_net': 0,
            'avg_change': 0
        }
    
    # 累加（千股）
    industries[industry]['total_net'] += net
    industries[industry]['total_change'] += change
    industries[industry]['stock_count'] += 1
    
    # 轉為億顯示
    industries[industry]['foreign_net'] = round(industries[industry]['total_net'] / 1000, 2)
    
    if len(industries[industry]['top_stocks']) < 10:
        industries[industry]['top_stocks'].append({
            'code': code,
            'name': name,
            'net': round(net / 1000, 2),  # 轉億
            'change': change,
            'change_pct': change
        })

# 計算平均
for ind_data in industries.values():
    if ind_data['stock_count'] > 0:
        ind_data['avg_change'] = round(ind_data['total_change'] / ind_data['stock_count'], 2)

output = {
    'updated_at': datetime.now().isoformat(),
    'date': data.get('date'),
    'industries': industries
}

with open('data/industry_heatmap.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✓ 已生成 {len(industries)} 個產業")

# 驗證
if '金融保險' in industries:
    fin = industries['金融保險']
    print(f"\n金融保險產業:")
    print(f"  外資淨額: {fin['foreign_net']}億")
    print(f"  股票數: {fin['stock_count']}")

conn.close()
print("\n✓ 完成")

