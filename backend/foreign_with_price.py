"""
外資買賣超 + 漲跌幅整合版
"""
import requests
from datetime import datetime, timedelta
import json
import sqlite3

print("=== 收集外資買賣超 + 漲跌幅 ===\n")

# 讀取股票主檔
conn = sqlite3.connect('data/market_data.db')
cursor = conn.cursor()
cursor.execute('SELECT stock_id, industry FROM stock_master')
stock_industry = dict(cursor.fetchall())
conn.close()

headers = {'User-Agent': 'Mozilla/5.0'}

# 找到有資料的日期
target_date = None
foreign_data = None

for days_ago in range(10):
    date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y%m%d')
    
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date}&selectType=ALL&response=json"
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        data = resp.json()
        
        if data.get('stat') == 'OK' and data.get('data'):
            target_date = date
            foreign_data = data['data']
            print(f"✓ 使用日期: {date}")
            break
    except:
        continue

if not foreign_data:
    print("✗ 無法取得外資數據")
    exit(1)

# 抓取當日收盤行情（含漲跌幅）
print("✓ 抓取收盤行情...")
price_url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={target_date}&type=ALL&response=json"

try:
    resp = requests.get(price_url, headers=headers, timeout=30)
    price_data = resp.json()
    
    # 建立股價對照表
    stock_prices = {}
    
    if price_data.get('stat') == 'OK':
        for row in price_data.get('data9', []):  # data9 是個股資料
            if len(row) >= 9:
                code = row[0].strip()
                # 漲跌幅在第 9 欄（索引 8）
                try:
                    change_pct = float(row[8].replace(',', '').replace('%', ''))
                    stock_prices[code] = change_pct
                except:
                    stock_prices[code] = 0
        
        print(f"✓ 已取得 {len(stock_prices)} 檔股票漲跌幅")
except Exception as e:
    print(f"✗ 無法取得股價資料: {e}")
    stock_prices = {}

# 整理外資數據
stocks = []
for row in foreign_data:
    if len(row) < 5:
        continue
    
    code = row[0].strip()
    name = row[1].strip()
    
    if len(code) != 4 or not code.isdigit():
        continue
    
    try:
        net_raw = row[4].replace(',', '').replace('，', '')
        net_zhang = float(net_raw) if net_raw and net_raw != '--' else 0
        
        # 取得漲跌幅
        change_pct = stock_prices.get(code, 0)
        
        stocks.append({
            'code': code,
            'name': name,
            'net': round(net_zhang, 0),  # 保持千股(張)
            'change': round(change_pct, 2),
            'industry': stock_industry.get(code, '其他')
        })
    except:
        continue

stocks.sort(key=lambda x: x['net'], reverse=True)

top_buy = [s for s in stocks if s['net'] > 0][:50]
top_sell = [s for s in stocks if s['net'] < 0][:50]

print(f"✓ 買超: {len(top_buy)} 檔")
print(f"✓ 賣超: {len(top_sell)} 檔")

# 輸出
output = {
    'updated_at': datetime.now().isoformat(),
    'date': target_date,
    'top_buy': top_buy,
    'top_sell': top_sell
}

with open('data/foreign_top_stocks.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✓ 已輸出\n")

# 顯示前5（含漲跌幅）
print("買超前5:")
for s in top_buy[:5]:
    net_wan = s['net'] / 10000
    print(f"  {s['code']} {s['name']}: {net_wan:,.2f}萬張, {s['change']:+.2f}%")

print("\n✓ 完成")

