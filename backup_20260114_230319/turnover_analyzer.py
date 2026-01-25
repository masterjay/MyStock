#!/usr/bin/env python3
import sqlite3, json
from datetime import datetime

def get_consecutive_overheat_days(stock_code, days=7):
    conn = sqlite3.connect('market_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT date, turnover_rate FROM turnover_history WHERE stock_code = ? ORDER BY date DESC LIMIT ?', (stock_code, days))
    records = cursor.fetchall()
    conn.close()
    consecutive = 0
    for date, rate in records:
        if rate >= 15: consecutive += 1
        else: break
    return consecutive

def get_all_stocks_classified():
    conn = sqlite3.connect('market_data.db')
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y%m%d')
    cursor.execute('SELECT stock_code, stock_name, industry, turnover_rate, volume FROM turnover_history WHERE date = ? ORDER BY volume DESC', (today,))
    all_stocks, active_stocks, normal_stocks = [], [], []
    for row in cursor.fetchall():
        code, name, industry, rate, volume = row
        stock_data = {'code': code, 'name': name, 'industry': industry, 'turnover_rate': rate, 'volume': volume}
        all_stocks.append(stock_data)
        if rate < 15:
            if 10 <= rate < 15: active_stocks.append(stock_data)
            elif 5 <= rate < 10: active_stocks.append(stock_data)
            elif rate < 5: normal_stocks.append(stock_data)
    conn.close()
    return {'all': all_stocks, 'active': active_stocks, 'normal': normal_stocks}

def get_all_stocks_classified():
    """取得所有股票並分類"""
    conn = sqlite3.connect('market_data.db')
    cursor = conn.cursor()
    
    today = datetime.now().strftime('%Y%m%d')
    
    # 取得今日所有股票
    cursor.execute('''
        SELECT stock_code, stock_name, industry, turnover_rate, volume
        FROM turnover_history 
        WHERE date = ?
        ORDER BY volume DESC
    ''', (today,))
    
    all_stocks = []
    active_stocks = []  # 5-10%
    normal_stocks = []  # <5%
    
    for row in cursor.fetchall():
        code, name, industry, rate, volume = row
        
        stock_data = {
            'code': code,
            'name': name,
            'industry': industry,
            'turnover_rate': rate,
            'volume': volume
        }
        
        all_stocks.append(stock_data)
        
        # 分類 (非過熱股票)
        if rate < 15:
            if 5 <= rate < 10:
                active_stocks.append(stock_data)
            elif rate < 5:
                normal_stocks.append(stock_data)
    
    conn.close()
    
    return {
        'all': all_stocks,
        'active': active_stocks,
        'normal': normal_stocks
    }

def analyze_and_export():
    conn = sqlite3.connect('market_data.db')
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y%m%d')
    cursor.execute('SELECT stock_code, stock_name, industry, turnover_rate, volume FROM turnover_history WHERE date = ? AND turnover_rate >= 15 ORDER BY turnover_rate DESC', (today,))
    overheat_stocks = []
    for row in cursor.fetchall():
        code, name, industry, rate, volume = row
        consecutive_days = get_consecutive_overheat_days(code, 7)
        overheat_stocks.append({'code': code, 'name': name, 'industry': industry, 'turnover_rate': rate, 'volume': volume, 'consecutive_days': consecutive_days})
    extreme_danger = [s for s in overheat_stocks if s['consecutive_days'] >= 5]
    severe = [s for s in overheat_stocks if s['consecutive_days'] == 4]
    overheat = [s for s in overheat_stocks if s['consecutive_days'] == 3]
    warning = [s for s in overheat_stocks if s['consecutive_days'] == 2]
    new = [s for s in overheat_stocks if s['consecutive_days'] == 1]
    cursor.execute('SELECT industry, COUNT(*) FROM turnover_history WHERE date = ? AND turnover_rate >= 15 GROUP BY industry ORDER BY COUNT(*) DESC', (today,))
    industry_stats = [{'industry': i, 'count': c} for i, c in cursor.fetchall()]
    cursor.execute('SELECT COUNT(CASE WHEN turnover_rate >= 15 THEN 1 END), COUNT(CASE WHEN turnover_rate >= 10 AND turnover_rate < 15 THEN 1 END), COUNT(CASE WHEN turnover_rate >= 5 AND turnover_rate < 10 THEN 1 END), COUNT(CASE WHEN turnover_rate < 5 THEN 1 END) FROM turnover_history WHERE date = ?', (today,))
    row = cursor.fetchone()
    stats = {'overheat': row[0], 'warning': row[1], 'active': row[2], 'normal': row[3]}
    conn.close()
    all_classified = get_all_stocks_classified()
    output = {'updated_at': datetime.now().isoformat(), 'statistics': stats, 'overheat_stocks': {'extreme_danger': extreme_danger, 'severe': severe, 'overheat': overheat, 'warning': warning, 'new': new}, 'industry_stats': industry_stats, 'all_stocks': all_classified['all'], 'active_stocks': all_classified['active'], 'normal_stocks': all_classified['normal']}
    with open('data/turnover_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✓ 完成: {len(overheat_stocks)}檔過熱, {len(all_classified['active'])}檔活躍, {len(all_classified['normal'])}檔正常")
    return output

if __name__ == '__main__':
    analyze_and_export()
