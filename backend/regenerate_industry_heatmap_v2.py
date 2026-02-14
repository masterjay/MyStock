"""
從 JSON 生成產業熱力圖
"""
import json
import sqlite3
from datetime import datetime

# 1. 讀取股票主檔
print("[1/2] 讀取股票主檔...")
conn = sqlite3.connect('data/market_data.db')
cursor = conn.cursor()
cursor.execute('SELECT stock_id, industry FROM stock_master')
stock_industry = {row[0]: row[1] for row in cursor.fetchall()}
conn.close()
print(f"  ✓ 已載入 {len(stock_industry)} 檔")

# 2. 讀取外資買賣超 JSON
print("\n[2/2] 從 JSON 讀取外資數據...")
with open('data/foreign_top_stocks.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 合併買超和賣超
all_stocks = data.get('top_buy', []) + data.get('top_sell', [])
print(f"  ✓ 已取得 {len(all_stocks)} 檔")

# 3. 依產業彙總
print("\n[3/3] 依產業彙總...")
industries = {}

for stock in all_stocks:
    code = stock.get('code', '')
    name = stock.get('name', '')
    net = float(stock.get('net', 0))
    change = float(stock.get('change', 0))
    
    # 從主檔取得產業
    industry = stock_industry.get(code, '其他')
    if not industry:
        industry = '其他'
    
    if industry not in industries:
        industries[industry] = {
            'total_net': 0,
            'total_change': 0,
            'stock_count': 0,
            'top_stocks': []
        }
    
    industries[industry]['total_net'] += net
    industries[industry]['total_change'] += change
    industries[industry]['stock_count'] += 1
    
    if len(industries[industry]['top_stocks']) < 10:
        industries[industry]['top_stocks'].append({
            'code': code,
            'name': name,
            'net': net,
            'change': change
        })

# 計算平均
for ind in industries.values():
    if ind['stock_count'] > 0:
        ind['avg_change'] = round(ind['total_change'] / ind['stock_count'], 2)

print(f"  ✓ 涵蓋 {len(industries)} 個產業")

# 輸出
output = {
    'updated_at': datetime.now().isoformat(),
    'date': data.get('date', datetime.now().strftime('%Y%m%d')),
    'industries': industries
}

with open('data/industry_heatmap.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("\n✓ 已輸出至 data/industry_heatmap.json")

# 驗證金融股
print("\n驗證金融保險產業:")
if '金融保險' in industries:
    fin = industries['金融保險']
    print(f"  股票數: {fin['stock_count']}")
    print(f"  Top 5:")
    for s in fin['top_stocks'][:5]:
        print(f"    {s['code']} {s['name']}")
else:
    print("  ✗ 未找到金融保險產業")

print("\n✓ 完成！請重新整理網頁 (Ctrl+F5 強制刷新)")

