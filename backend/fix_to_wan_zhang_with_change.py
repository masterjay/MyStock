import json
import sqlite3
from datetime import datetime

print("=== 重新生成（單位：萬張，含漲跌幅）===\n")

conn = sqlite3.connect('data/market_data.db')
cursor = conn.cursor()
cursor.execute('SELECT stock_id, industry FROM stock_master')
stock_industry = dict(cursor.fetchall())
conn.close()

with open('data/foreign_top_stocks.json', 'r') as f:
    data = json.load(f)

stocks = data.get('top_buy', []) + data.get('top_sell', [])

industries = {}
for stock in stocks:
    industry = stock_industry.get(stock['code'], '其他') or '其他'
    
    if industry not in industries:
        industries[industry] = {
            'industry': industry,
            'total_net': 0,
            'total_change': 0,  # 累加漲跌幅
            'stock_count': 0,
            'top_stocks': []
        }
    
    net_zhang = stock.get('net', 0) or 0
    net_wan_zhang = net_zhang / 10000
    change = stock.get('change', 0) or 0
    
    industries[industry]['total_net'] += net_wan_zhang
    industries[industry]['total_change'] += change
    industries[industry]['stock_count'] += 1
    
    if len(industries[industry]['top_stocks']) < 10:
        industries[industry]['top_stocks'].append({
            'code': stock['code'],
            'name': stock['name'],
            'net': round(net_wan_zhang, 2),
            'change': change,
            'change_pct': change
        })

final = {}
for name, ind in industries.items():
    # 計算平均漲跌幅
    avg_change = round(ind['total_change'] / ind['stock_count'], 2) if ind['stock_count'] > 0 else 0
    
    final[name] = {
        'industry': name,
        'foreign_net': round(ind['total_net'], 2),
        'avg_change': avg_change,  # 平均漲跌幅
        'stock_count': ind['stock_count'],
        'top_stocks': ind['top_stocks'],
        'total_net': ind['total_net'],
        'total_change': ind['total_change']
    }

output = {
    'updated_at': datetime.now().isoformat(),
    'date': data['date'],
    'industries': final
}

with open('data/industry_heatmap.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✓ 已生成 {len(final)} 個產業\n")

# 驗證
for ind_name in ['光電', '半導體', '金融保險']:
    if ind_name in final:
        ind = final[ind_name]
        print(f"{ind_name}:")
        print(f"  外資: {ind['foreign_net']:,.2f} 萬張")
        print(f"  平均漲跌幅: {ind['avg_change']:+.2f}%")
        if ind['top_stocks']:
            s = ind['top_stocks'][0]
            print(f"  第一檔: {s['code']} {s['name']} {s['net']:,.2f}萬張 {s['change']:+.2f}%\n")

