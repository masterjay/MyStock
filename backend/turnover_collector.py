#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
周轉率數據收集器 v2.1
1. 抓取全部股票計算周轉率 TOP N
2. 計算爆量倍數 (vs 近5日均量)
3. 新增股價、漲跌%
"""

import requests
import sqlite3
from datetime import datetime, timedelta

# TWSE 產業代碼對照表
INDUSTRY_CODE_MAP = {
    '01': '水泥', '02': '食品', '03': '塑膠', '04': '紡織',
    '05': '電機', '06': '電器電纜', '08': '玻璃陶瓷', '09': '造紙',
    '10': '鋼鐵', '11': '橡膠', '12': '汽車', '14': '建材營造',
    '15': '航運', '16': '觀光', '17': '金融', '18': '貿易百貨',
    '20': '其他', '21': '化工', '22': '生技醫療', '23': '油電燃氣',
    '24': '半導體', '25': '電腦週邊', '26': '光電', '27': '通訊網路',
    '28': '電子零組件', '29': '電子通路', '30': '資訊服務', '31': '其他電子',
    '35': '綠能環保', '36': '數位雲端', '37': '運動休閒', '38': '居家生活',
    '91': 'DR'
}

def get_industry_name(code):
    """將產業代碼轉換為名稱"""
    return INDUSTRY_CODE_MAP.get(code, '其他')


def get_all_stocks_volume():
    """取得所有股票當日成交量、股價、漲跌% (剔除 ETF)"""
    try:
        url = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALL"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        data = r.json()
        
        table8 = data['tables'][8]
        stocks = {}
        
        for stock in table8['data']:
            code = stock[0]
            name = stock[1]
            volume_str = stock[2].replace(',', '')
            
            if volume_str and volume_str.isdigit():
                # 剔除 ETF/ETN
                is_etf = (
                    code.startswith('00') or 
                    'ETF' in name or 
                    'etf' in name or
                    'ETN' in name
                )
                
                if not is_etf:
                    # 解析股價和漲跌
                    close_price = None
                    change_pct = None
                    
                    try:
                        # 收盤價 [8]
                        close_str = stock[8].replace(',', '')
                        if close_str and close_str != '--':
                            close_price = float(close_str)
                        
                        # 漲跌方向 [9] - 解析 HTML
                        change_dir = stock[9]
                        is_down = 'green' in change_dir or '-' in change_dir
                        
                        # 漲跌價差 [10]
                        change_str = stock[10].replace(',', '')
                        if close_price and change_str and change_str != '--':
                            change_val = float(change_str)
                            if is_down:
                                change_val = -change_val
                            # 計算漲跌%
                            prev_price = close_price - change_val
                            if prev_price > 0:
                                change_pct = round((change_val / prev_price) * 100, 2)
                    except:
                        pass
                    
                    stocks[code] = {
                        'code': code,
                        'name': name,
                        'volume': int(volume_str),
                        'close_price': close_price,
                        'change_pct': change_pct
                    }
        
        return stocks
    
    except Exception as e:
        print(f"✗ 抓取成交量失敗: {e}")
        return {}

def get_issued_shares():
    """取得所有上市公司發行股數和產業"""
    try:
        url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        data = r.json()
        
        shares_dict = {}
        industry_dict = {}
        for item in data:
            code = item.get('公司代號', '')
            shares = item.get('已發行普通股數或TDR原股發行股數', '0')
            industry_code = item.get('產業別', '')
            if code and shares:
                shares_dict[code] = int(shares)
                industry_dict[code] = get_industry_name(industry_code)
        
        return shares_dict, industry_dict
    
    except Exception as e:
        print(f"✗ 抓取發行股數失敗: {e}")
        return {}, {}

def get_avg_volume(cursor, code, days=5):
    """取得近N日平均成交量"""
    cursor.execute('''
        SELECT AVG(volume) FROM (
            SELECT volume FROM turnover_history 
            WHERE stock_code = ? 
            ORDER BY date DESC 
            LIMIT ?
        )
    ''', (code, days))
    result = cursor.fetchone()
    return result[0] if result and result[0] else None
def get_industry_from_db(cursor, code):
    """從資料庫取得產業分類"""
    cursor.execute('SELECT industry FROM turnover_history WHERE stock_code = ? LIMIT 1', (code,))
    result = cursor.fetchone()
    return result[0] if result else '其他'

def calculate_turnover_and_surge(stocks_volume, shares_dict, industry_dict, cursor):
    """計算周轉率和爆量倍數（雙時間軸）"""
    results = []
    
    for code, stock in stocks_volume.items():
        issued_shares = shares_dict.get(code, 0)
        if issued_shares <= 0:
            continue
        
        volume = stock['volume']
        turnover_rate = (volume / issued_shares) * 100
        
        # 計算雙時間軸爆量倍數
        avg_volume_5d = get_avg_volume(cursor, code, 5)
        avg_volume_20d = get_avg_volume(cursor, code, 20)
        
        surge_5d = (volume / avg_volume_5d) if avg_volume_5d and avg_volume_5d > 0 else None
        surge_20d = (volume / avg_volume_20d) if avg_volume_20d and avg_volume_20d > 0 else None
        
        # 判斷爆量類型（多層次分級）
        if surge_5d and surge_5d >= 5:
            surge_type = "super"     # 超級爆量 (5日 >= 5倍)
        elif surge_5d and surge_5d >= 3 and surge_20d and surge_20d >= 2:
            surge_type = "both"      # 強爆量 (5日 >= 3倍 且 20日 >= 2倍)
        elif surge_5d and surge_5d >= 2:
            surge_type = "short"     # 短線異動 (5日 >= 2倍)
        elif surge_20d and surge_20d >= 1.5:
            surge_type = "mid"       # 中線放量 (20日 >= 1.5倍)
        else:
            surge_type = None
        
        # 取得產業 (優先用 API，其次用 DB)
        industry = industry_dict.get(code) or get_industry_from_db(cursor, code) or '其他'
        
        results.append({
            'code': code,
            'name': stock['name'],
            'industry': industry,
            'volume': volume,
            'issued_shares': issued_shares,
            'turnover_rate': turnover_rate,
            'surge_5d': surge_5d,
            'surge_20d': surge_20d,
            'surge_type': surge_type,
            'close_price': stock.get('close_price'),
            'change_pct': stock.get('change_pct')
        })
    
    return results

def save_to_database(date, stocks_data):
    """儲存周轉率資料到資料庫"""
    conn = sqlite3.connect('data/market_data.db')
    cursor = conn.cursor()
    
    # 確保表格有新欄位
    for col in ['surge_5d REAL', 'surge_20d REAL', 'surge_type TEXT', 'close_price REAL', 'change_pct REAL']:
        try:
            cursor.execute(f'ALTER TABLE turnover_history ADD COLUMN {col}')
        except:
            pass  # 欄位已存在
    
    saved_count = 0
    
    for stock in stocks_data:
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO turnover_history 
                (date, stock_code, stock_name, industry, volume, issued_shares, turnover_rate, surge_5d, surge_20d, surge_type, close_price, change_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (date, stock['code'], stock['name'], stock['industry'], 
                  stock['volume'], stock['issued_shares'], stock['turnover_rate'], 
                  stock['surge_5d'], stock['surge_20d'], stock['surge_type'], stock['close_price'], stock['change_pct']))
            saved_count += 1
        except Exception as e:
            print(f"✗ 儲存 {stock['code']} 失敗: {e}")
    
    conn.commit()
    conn.close()
    
    return saved_count

def clean_old_data(days=30):
    """清理超過N天的舊資料"""
    conn = sqlite3.connect('data/market_data.db')
    cursor = conn.cursor()
    
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
    cursor.execute('DELETE FROM turnover_history WHERE date < ?', (cutoff_date,))
    deleted_count = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    return deleted_count

def collect_turnover_data():
    """主函數:收集周轉率資料"""
    print("="*60)
    print("📊 周轉率數據收集 v2.1 (含股價/漲跌%)")
    print("="*60)
    
    today = datetime.now().strftime('%Y%m%d')
    print(f"日期: {today}\n")
    
    # Step 1: 抓取全部股票成交量
    print("[1/5] 抓取全部股票成交量、股價、漲跌%...")
    stocks_volume = get_all_stocks_volume()
    
    if not stocks_volume:
        print("✗ 無法取得成交量資料")
        return False
    
    print(f"✓ 已取得 {len(stocks_volume)} 檔股票")
    
    # Step 2: 抓取發行股數
    print("\n[2/5] 抓取發行股數...")
    shares_dict, industry_dict = get_issued_shares()
    
    if not shares_dict:
        print("✗ 無法取得發行股數")
        return False
    
    print(f"✓ 已取得 {len(shares_dict)} 檔股票發行股數")
    
    # Step 3: 計算周轉率和爆量倍數
    print("\n[3/5] 計算周轉率和爆量倍數...")
    conn = sqlite3.connect('data/market_data.db')
    cursor = conn.cursor()
    stocks_data = calculate_turnover_and_surge(stocks_volume, shares_dict, industry_dict, cursor)
    conn.close()
    
    # 篩選: 周轉率 >= 5% 或 爆量 >= 2倍
    filtered = [s for s in stocks_data if s['turnover_rate'] >= 5 or (s['surge_5d'] and s['surge_5d'] >= 2)]
    
    # 排序: 周轉率優先
    filtered.sort(key=lambda x: x['turnover_rate'], reverse=True)
    
    # 取 TOP 50
    top_stocks = filtered[:50]
    
    print(f"✓ 篩選出 {len(top_stocks)} 檔 (周轉率>=5% 或 爆量>=2倍)")
    
    # Step 4: 儲存到資料庫
    print("\n[4/5] 儲存到資料庫...")
    saved_count = save_to_database(today, top_stocks)
    print(f"✓ 已儲存 {saved_count} 筆資料")
    
    # Step 5: 清理舊資料
    print("\n[5/5] 清理舊資料 (保留30天)...")
    deleted_count = clean_old_data(30)
    print(f"✓ 已刪除 {deleted_count} 筆舊資料")
    
    # 顯示摘要
    print("\n" + "-"*60)
    print("📋 今日摘要:")
    overheat = [s for s in top_stocks if s['turnover_rate'] >= 15]
    surge = [s for s in top_stocks if s['surge_5d'] and s['surge_5d'] >= 3]
    both = [s for s in top_stocks if s['turnover_rate'] >= 15 and s['surge_5d'] and s['surge_5d'] >= 3]
    
    print(f"   高周轉 (>=15%): {len(overheat)} 檔")
    print(f"   爆量 (>=3倍): {len(surge)} 檔")
    print(f"   兩者皆是: {len(both)} 檔")
    
    print("\n" + "="*60)
    print("✓ 周轉率數據收集完成!")
    print("="*60)
    
    return True

if __name__ == '__main__':
    collect_turnover_data()
