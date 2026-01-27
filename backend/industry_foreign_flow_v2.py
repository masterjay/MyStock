#!/usr/bin/env python3
import json
import requests
from collections import defaultdict
from datetime import datetime
from industry_mapper import get_industry

def get_price_changes():
    """获取所有股票的涨跌幅"""
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
        print(f"取得涨跌幅失败: {e}")
        return {}

def collect_industry_foreign_flow():
    # 1. 获取外资数据
    with open('data/foreign_top_stocks.json', 'r') as f:
        foreign_data = json.load(f)
    
    # 2. 获取涨跌幅
    price_changes = get_price_changes()
    print(f"✓ 已取得 {len(price_changes)} 档股票涨跌幅")
    
    # 3. 统计各产业
    industry_stats = defaultdict(lambda: {
        'foreign_net': 0, 'stock_count': 0, 'total_change': 0, 'stocks': []
    })
    
    # 处理买超
    for stock in foreign_data['top_buy']:
        code = stock['code']
        name = stock['name']
        foreign_net = stock['foreign_net'] / 100000  # 转换为亿
        
        industry = get_industry(code, name)
        change_pct = price_changes.get(code, 0)
        
        industry_stats[industry]['foreign_net'] += foreign_net
        industry_stats[industry]['stock_count'] += 1
        industry_stats[industry]['total_change'] += change_pct
        industry_stats[industry]['stocks'].append({
            'code': code, 'name': name,
            'net': round(foreign_net, 2),
            'change_pct': round(change_pct, 2)
        })
    
    # 处理卖超
    for stock in foreign_data['top_sell']:
        code = stock['code']
        name = stock['name']
        foreign_net = stock['foreign_net'] / 100000
        
        industry = get_industry(code, name)
        change_pct = price_changes.get(code, 0)
        
        industry_stats[industry]['foreign_net'] += foreign_net
        industry_stats[industry]['stock_count'] += 1
        industry_stats[industry]['total_change'] += change_pct
        industry_stats[industry]['stocks'].append({
            'code': code, 'name': name,
            'net': round(foreign_net, 2),
            'change_pct': round(change_pct, 2)
        })
    
    # 4. 整理结果
    result = []
    for industry, data in industry_stats.items():
        if data['stock_count'] == 0:
            continue
        
        avg_change = data['total_change'] / data['stock_count']
        stocks_sorted = sorted(data['stocks'], key=lambda x: x['net'], reverse=True)
        
        result.append({
            'industry': industry,
            'foreign_net': round(data['foreign_net'], 2),
            'stock_count': data['stock_count'],
            'avg_change': round(avg_change, 2),
            'stocks': stocks_sorted
        })
    
    result.sort(key=lambda x: x['foreign_net'], reverse=True)
    
    output = {
        'updated_at': datetime.now().isoformat(),
        'date': foreign_data['date'],
        'industries': result
    }
    
    with open('data/industry_heatmap.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 产业外资流向已更新: {len(result)} 个产业")
    
    # 显示前10个产业
    print("\n=== 前10个产业 ===")
    for ind in result[:10]:
        print(f"{ind['industry']}: 外资 {ind['foreign_net']}亿, {ind['stock_count']}档")
    
    return output

if __name__ == '__main__':
    collect_industry_foreign_flow()
