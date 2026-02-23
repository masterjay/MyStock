#!/usr/bin/env python3
"""
產業熱力圖後處理：合併外資流向數據，轉換為前端格式
"""
import json
import requests
from datetime import datetime

NAME_MAP = {
    '水泥': '水泥工業',
    '塑膠': '塑膠工業',
    '化工': '化學工業',
    '橡膠': '橡膠工業',
    '鋼鐵': '鋼鐵工業',
    '食品': '食品工業',
    '電機': '電機機械',
    '汽車': '汽車工業',
    '航運': '航運業',
    '觀光': '觀光餐旅',
    '金融': '金融保險',
    '電腦週邊': '電腦及週邊',
    '通訊網路': '通信網路',
    '文化創意': '文化創意業',
}

def get_all_foreign_net(date_str):
    """用 T86 API 取得所有個股外資買賣超 (單位:千股=張)"""
    stock_net = {}
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date_str}&selectType=ALL&response=json"
    try:
        resp = requests.get(url, timeout=30)
        data = resp.json()
        if data.get('stat') == 'OK' and 'data' in data:
            for row in data['data']:
                code = row[0].strip()
                if len(code) == 4 and code.isdigit():
                    try:
                        buy = float(row[3].replace(',', '')) if row[3] != '--' else 0
                        sell = float(row[4].replace(',', '')) if row[4] != '--' else 0
                        net = buy - sell  # 千股 = 張
                        stock_net[code] = net / 10000  # 轉萬張
                    except:
                        pass
        print(f"  ✓ 取得 {len(stock_net)} 檔個股外資數據")
    except Exception as e:
        print(f"  ✗ T86 API 錯誤: {e}")
    return stock_net

def main():
    with open('data/industry_heatmap.json', 'r', encoding='utf-8') as f:
        heatmap = json.load(f)
    
    with open('data/industry_foreign_flow.json', 'r', encoding='utf-8') as f:
        flow = json.load(f)
    flow_data = flow.get('industries', {})
    
    # 取得所有個股外資買賣超
    date_str = heatmap.get('date', datetime.now().strftime('%Y%m%d'))
    stock_net = get_all_foreign_net(date_str)
    
    # 轉換為前端格式
    industries_dict = {}
    matched = 0
    
    for industry in heatmap.get('industries', []):
        name = industry['industry']
        flow_name = NAME_MAP.get(name, name)
        
        foreign_net = 0
        if flow_name in flow_data:
            foreign_net = round(flow_data[flow_name].get('net', 0) / 10000, 2)
            matched += 1
        
        top_stocks = []
        for stock in industry.get('stocks', []):
            code = stock['code']
            net = stock_net.get(code, 0)
            top_stocks.append({
                'code': code,
                'name': stock['name'],
                'net': round(net, 2),
                'change_pct': round(stock.get('change_pct', 0), 2)
            })
        
        top_stocks.sort(key=lambda x: x['net'], reverse=True)
        
        industries_dict[name] = {
            'industry': name,
            'foreign_net': foreign_net,
            'avg_change': round(industry.get('avg_change', 0), 2),
            'stock_count': industry.get('stock_count', len(top_stocks)),
            'top_stocks': top_stocks
        }
    
    output = {
        'date': heatmap.get('date', ''),
        'updated_at': datetime.now().isoformat(),
        'industries': industries_dict
    }
    
    with open('data/industry_heatmap.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 已轉換產業熱力圖為前端格式")
    print(f"  產業數: {len(industries_dict)}")
    print(f"  匹配外資: {matched} 個產業")

if __name__ == '__main__':
    main()
