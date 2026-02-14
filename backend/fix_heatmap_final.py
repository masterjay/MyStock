import json
import sqlite3
from datetime import datetime

print("=== 重新生成產業熱力圖（修正單位）===\n")

# 讀取主檔
conn = sqlite3.connect('data/market_data.db')
cursor = conn.cursor()
cursor.execute('SELECT stock_id, industry FROM stock_master')
stock_industry = dict(cursor.fetchall())
conn.close()

# 讀取外資數據
with open('data/foreign_top_stocks.json', 'r') as f:
    data = json.load(f)

stocks = data.get('top_buy', []) + data.get('top_sell', [])

print(f"處理 {len(stocks)} 檔股票")

# 彙總
industries = {}
for stock in stocks:
    industry = stock_industry.get(stock['code'], '其他') or '其他'
    
    if industry not in industries:
        industries[industry] = {
            'industry': industry,
            'total_net_k': 0,  # 千股（累加用）
            'stock_count': 0,
            'top_stocks': []
        }
    
    # 原始數值是千股
    net_k = stock.get('net', 0) or 0
    industries[industry]['total_net_k'] += net_k
    industries[industry]['stock_count'] += 1
    
    if len(industries[industry]['top_stocks']) < 10:
        industries[industry]['top_stocks'].append({
            'code': stock['code'],
            'name': stock['name'],
            'net': round(net_k / 1000, 2),  # 千股 → 億
            'change': 0,
            'change_pct': 0
        })

# 轉換為最終格式（億）
final = {}
for name, ind in industries.items():
    final[name] = {
        'industry': name,
        'foreign_net': round(ind['total_net_k'] / 1000, 2),  # 千股 → 億
        'avg_change': 0,
        'stock_count': ind['stock_count'],
        'top_stocks': ind['top_stocks'],
        'total_net': ind['total_net_k'],  # 保留原始千股
        'total_change': 0
    }

output = {
    'updated_at': datetime.now().isoformat(),
    'date': data['date'],
    'industries': final
}

with open('data/industry_heatmap.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✓ 已生成 {len(final)} 個產業")

# 驗證
print("\n驗證數值:")
for ind_name in ['光電', '半導體', '金融保險']:
    if ind_name in final:
        ind = final[ind_name]
        print(f"  {ind_name}:")
        print(f"    原始: {ind['total_net']:,.0f} 千股")
        print(f"    顯示: {ind['foreign_net']:.2f} 億")
        if ind['top_stocks']:
            s = ind['top_stocks'][0]
            print(f"    第一檔: {s['code']} {s['name']} {s['net']:.2f}億")

