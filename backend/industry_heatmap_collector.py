#!/usr/bin/env python3
import requests
import json
from collections import defaultdict
from datetime import datetime, timedelta

# 產業分類對照表
def get_industry_by_code(code, name):
    """根據股票代碼和名稱判斷產業"""
    prefix = code[:2]
    
    industry_map = {
        '23': '半導體', '24': '電腦週邊', '25': '光電', '26': '通訊網路',
        '27': '電子零組件', '28': '電子通路', '29': '資訊服務', '30': '其他電子',
        '31': '半導體', '32': '電腦週邊', '33': '電腦週邊', '34': '光電',
        '35': '電子零組件', '36': '通訊網路', '37': '電子零組件', '38': '電子零組件',
        '39': '其他電子', '40': '生技醫療', '41': '生技醫療', '42': '半導體',
        '43': '電腦週邊', '44': '電子零組件', '45': '電子零組件', '46': '電子零組件',
        '47': '電腦週邊', '48': '電子零組件', '49': '電子零組件',
        '14': '建材營造', '15': '航運', '17': '鋼鐵', '18': '橡膠',
        '19': '汽車', '20': '食品', '21': '化工', '16': '觀光',
        '13': '電機', '11': '水泥', '12': '塑膠',
        '50': '電子通路', '51': '貿易百貨', '52': '貿易百貨', '53': '貿易百貨',
        '54': '貿易百貨', '55': '貿易百貨', '56': '文化創意', '57': '油電燃氣',
        '61': '其他電子', '62': '生技醫療', '63': '其他電子', '64': '生技醫療',
        '65': '生技醫療', '66': '其他電子', '80': '金融', '91': '其他'
    }
    
    if prefix in industry_map:
        return industry_map[prefix]
    
    if any(kw in name for kw in ['銀行', '金控', '保險', '證券']):
        return '金融'
    elif any(kw in name for kw in ['生技', '醫療', '製藥', '藥華', '藥品']):
        return '生技醫療'
    
    return '其他'

def find_trading_dates():
    """找到最近兩個有資料的交易日（使用 FMTQIK 月成交資訊）"""
    import time
    today = datetime.now()
    trading_days = []
    
    print("尋找最近的交易日...")
    
    # 搜尋最近兩個月的交易日
    for month_offset in range(3):
        check_date = today - timedelta(days=30 * month_offset)
        date_str = check_date.strftime('%Y%m%d')
        
        url = f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={date_str}&response=json"
        try:
            if month_offset > 0:
                time.sleep(1)
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if data.get('stat') == 'OK' and 'data' in data:
                for row in data['data']:
                    # 民國日期轉西元: 115/02/23 -> 20260223
                    roc_date = row[0].strip()
                    parts = roc_date.split('/')
                    if len(parts) == 3:
                        y = int(parts[0]) + 1911
                        m = int(parts[1])
                        d = int(parts[2])
                        western = f"{y}{m:02d}{d:02d}"
                        # 只取今天以前（含今天）的
                        if western <= today.strftime('%Y%m%d'):
                            trading_days.append(western)
        except Exception as e:
            print(f"  ✗ 取得月資料錯誤: {e}")
    
    # 排序取最近兩天
    trading_days = sorted(set(trading_days), reverse=True)
    
    if len(trading_days) >= 2:
        print(f"✓ 今日交易日: {trading_days[0]}")
        print(f"✓ 前一交易日: {trading_days[1]}")
        return trading_days[0], trading_days[1]
    elif len(trading_days) == 1:
        print(f"✓ 只找到一個交易日: {trading_days[0]}")
        return trading_days[0], None
    else:
        print("✗ 無法找到交易日")
        return None, None

def get_all_stocks_amount(date_str):
    """取得指定日期所有股票的成交金額"""
    amounts = {}
    
    # 上市
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?date={date_str}&response=json"
    try:
        response = requests.get(url, timeout=30)
        data = response.json()
        if data.get('stat') == 'OK':
            for row in data['data']:
                code = row[0].strip()
                if code.isdigit() and len(code) == 4 and not code.startswith('00'):
                    amount_str = row[3].replace(',', '')
                    if amount_str not in ['--', '']:
                        amounts[code] = float(amount_str) / 100000000
    except Exception as e:
        print(f"✗ 上市資料錯誤: {e}")
    
    # 上櫃 - 只有今天的資料
    if date_str == datetime.now().strftime('%Y%m%d') or \
       date_str == (datetime.now() - timedelta(days=1)).strftime('%Y%m%d'):
        try:
            otc_url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
            response = requests.get(otc_url, timeout=30)
            otc_data = response.json()
            
            dt = datetime.strptime(date_str, '%Y%m%d')
            roc_date = f"{dt.year - 1911:03d}{dt.month:02d}{dt.day:02d}"
            
            for item in otc_data:
                if item.get('Date') == roc_date:
                    code = item['SecuritiesCompanyCode'].strip()
                    if code.isdigit() and len(code) == 4 and not code.startswith('00'):
                        amount_str = item.get('TransactionAmount', '0').replace(',', '')
                        if amount_str:
                            amounts[code] = float(amount_str) / 100000000
        except:
            pass
    
    return amounts

def collect_industry_heatmap():
    """收集產業資金流向"""
    
    # 找到最近兩個交易日
    today, yesterday = find_trading_dates()
    
    if not today or not yesterday:
        print("使用備用方案")
        return collect_from_turnover_data()
    
    print(f"\n比較日期: {today} vs {yesterday}")
    
    # 取得兩天的資料
    today_amounts = get_all_stocks_amount(today)
    yesterday_amounts = get_all_stocks_amount(yesterday)
    
    print(f"✓ 今天: {len(today_amounts)} 檔")
    print(f"✓ 昨天: {len(yesterday_amounts)} 檔")
    
    # 取得今天的漲跌幅
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?date={today}&response=json"
    response = requests.get(url, timeout=30)
    data = response.json()
    
    # 統計各產業
    industry_data = defaultdict(lambda: {
        'stocks': [], 'total_change': 0, 'count': 0,
        'money_in': 0, 'money_out': 0, 'total_amount': 0
    })
    
    # 處理上市
    for row in data['data']:
        try:
            code = row[0].strip()
            name = row[1].strip()
            
            if not code.isdigit() or len(code) != 4 or code.startswith('00'):
                continue
            
            close_str = row[7].replace(',', '')
            change_str = row[8].replace(',', '')
            
            if close_str in ['--', ''] or change_str in ['--', '', 'X']:
                continue
            
            close_price = float(close_str)
            change_value = float(change_str.replace('+', ''))
            change_pct = (change_value / (close_price - change_value)) * 100
            
            # 計算資金流向
            amount_today = today_amounts.get(code, 0)
            amount_yesterday = yesterday_amounts.get(code, 0)
            real_flow = amount_today - amount_yesterday
            
            industry = get_industry_by_code(code, name)
            
            industry_data[industry]['stocks'].append({
                'code': code, 'name': name, 'change_pct': change_pct,
                'amount': amount_today, 'real_flow': real_flow
            })
            industry_data[industry]['total_change'] += change_pct
            industry_data[industry]['count'] += 1
            industry_data[industry]['total_amount'] += amount_today
            
            if real_flow > 0:
                industry_data[industry]['money_in'] += real_flow
            else:
                industry_data[industry]['money_out'] += abs(real_flow)
                
        except (IndexError, ValueError, ZeroDivisionError):
            continue
    
    print(f"✓ 處理完成")
    
    # 計算各產業統計
    result = []
    for industry, data in industry_data.items():
        if data['count'] == 0:
            continue
        
        avg_change = data['total_change'] / data['count']
        up_count = sum(1 for s in data['stocks'] if s['change_pct'] > 0)
        up_ratio = (up_count / data['count'] * 100) if data['count'] > 0 else 0
        net_inflow = data['money_in'] - data['money_out']
        
        result.append({
            'industry': industry,
            'avg_change': round(avg_change, 2),
            'up_ratio': round(up_ratio, 1),
            'stock_count': data['count'],
            'up_count': up_count,
            'down_count': data['count'] - up_count,
            'total_amount': round(data['total_amount'], 2),
            'money_in': round(data['money_in'], 2),
            'money_out': round(data['money_out'], 2),
            'net_inflow': round(net_inflow, 2),
            'stocks': data['stocks']
        })
    
    result.sort(key=lambda x: x['net_inflow'], reverse=True)
    
    output = {
        'date': today,
        'compare_date': yesterday,
        'updated_at': datetime.now().isoformat(),
        'source': 'TSE_COMPARISON',
        'industries': result
    }
    
    with open('data/industry_heatmap.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    total_stocks = sum(r['stock_count'] for r in result)
    print(f"✓ 產業熱圖已更新: {len(result)} 個產業, {total_stocks} 檔股票")
    
    return output

def collect_from_turnover_data():
    """備用方案"""
    print("使用備用方案: 周轉率數據")
    # ... 保持原樣
    return {}

if __name__ == '__main__':
    collect_industry_heatmap()
