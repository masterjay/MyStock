#!/usr/bin/env python3
import json
from collections import defaultdict

def get_price_changes():
    """從TWSE取得所有股票的漲跌幅"""
    from datetime import datetime
    import requests
    
    today = datetime.now().strftime('%Y%m%d')
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?date={today}&response=json"
    
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
        data = response.json()
        
        price_map = {}
        for row in data.get('data', []):
            try:
                code = row[0].strip()
                if not code.isdigit() or len(code) != 4:
                    continue
                    
                close_price = float(row[7].replace(',', ''))
                change_str = row[8].replace(',', '').strip()
                
                # 處理漲跌符號
                if change_str.startswith('+'):
                    change_value = float(change_str[1:])
                elif change_str.startswith('-'):
                    change_value = -float(change_str[1:])
                elif change_str == 'X':
                    change_value = 0
                else:
                    change_value = float(change_str) if change_str else 0
                
                if close_price - change_value != 0:
                    change_pct = (change_value / (close_price - change_value)) * 100
                else:
                    change_pct = 0
                    
                price_map[code] = round(change_pct, 2)
                
            except (IndexError, ValueError, ZeroDivisionError):
                continue
                
        return price_map
        
    except Exception as e:
        print(f"取得漲跌幅失敗: {e}")
        return {}

from datetime import datetime

def get_industry_by_code(code, name):
    prefix = code[:2]
    industry_map = {
        '23': '半導體', '24': '電腦週邊', '25': '光電', '26': '通訊網路',
        '27': '電子零組件', '28': '電子通路', '29': '資訊服務', '30': '其他電子',
        '14': '建材營造', '15': '航運', '17': '鋼鐵', '18': '橡膠',
        '19': '汽車', '20': '食品', '21': '化工', '16': '觀光',
        '13': '電機', '11': '水泥', '12': '塑膠'
    }
    if prefix in industry_map:
        return industry_map[prefix]
    if any(kw in name for kw in ['銀行', '金控', '保險', '證券']):
        return '金融'
    elif any(kw in name for kw in ['生技', '醫療', '製藥']):
        return '生技醫療'
    return '其他'

def collect_industry_foreign_flow():
    with open('data/foreign_top_stocks.json', 'r') as f:
        foreign_data = json.load(f)
    with open('data/turnover_analysis.json', 'r') as f:
        market_data = json.load(f)
    
    # 直接從TWSE取得漲跌幅
    price_changes = get_price_changes()
    print(f"✓ 已取得 {len(price_changes)} 檔股票漲跌幅")
    
    industry_stats = defaultdict(lambda: {
        'foreign_net': 0, 'foreign_buy': 0, 'foreign_sell': 0,
        'stock_count': 0, 'total_change': 0, 'stocks': []
    })
    
    for stock in foreign_data['top_buy']:
        code = stock['code']
        name = stock['name']
        foreign_net = stock['foreign_net'] / 100000
        
        if code in price_changes:
            change_pct = price_changes[code]
            industry = get_industry_by_code(code, name)
        else:
            industry = get_industry_by_code(code, name)
            change_pct = 0
        
        industry_stats[industry]['foreign_net'] += foreign_net
        industry_stats[industry]['foreign_buy'] += stock['foreign_buy'] / 100000
        industry_stats[industry]['foreign_sell'] += stock['foreign_sell'] / 100000
        industry_stats[industry]['stock_count'] += 1
        industry_stats[industry]['total_change'] += change_pct
        industry_stats[industry]['stocks'].append({
            'code': code, 'name': name,
            'net': round(foreign_net, 2),
            'change_pct': round(change_pct, 2)
        })
    
    for stock in foreign_data['top_sell']:
        code = stock['code']
        name = stock['name']
        foreign_net = stock['foreign_net'] / 100000
        
        if code in price_changes:
            change_pct = price_changes[code]
            industry = get_industry_by_code(code, name)
        else:
            industry = get_industry_by_code(code, name)
            change_pct = 0
        
        industry_stats[industry]['foreign_net'] += foreign_net
        industry_stats[industry]['foreign_buy'] += stock['foreign_buy'] / 100000
        industry_stats[industry]['foreign_sell'] += stock['foreign_sell'] / 100000
        industry_stats[industry]['stock_count'] += 1
        industry_stats[industry]['total_change'] += change_pct
        industry_stats[industry]['stocks'].append({
            'code': code, 'name': name,
            'net': round(foreign_net, 2),
            'change_pct': round(change_pct, 2)
        })
    
    result = []
    for industry, data in industry_stats.items():
        if data['stock_count'] == 0:
            continue
        
        avg_change = data['total_change'] / data['stock_count']
        stocks_detail = sorted(data['stocks'], key=lambda x: x['net'], reverse=True)
        
        result.append({
            'industry': industry,
            'foreign_net': round(data['foreign_net'], 2),
            'foreign_buy': round(data['foreign_buy'], 2),
            'foreign_sell': round(data['foreign_sell'], 2),
            'stock_count': data['stock_count'],
            'avg_change': round(avg_change, 2),
            'stocks': stocks_detail
        })
    
    result.sort(key=lambda x: x['foreign_net'], reverse=True)
    
    output = {
        'updated_at': datetime.now().isoformat(),
        'date': foreign_data['date'],
        'industries': result
    }
    
    with open('data/industry_heatmap.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 產業外資流向已更新: {len(result)} 個產業")
    return output

if __name__ == '__main__':
    collect_industry_foreign_flow()
