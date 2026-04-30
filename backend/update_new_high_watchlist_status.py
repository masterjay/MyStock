#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新高觀察清單狀態更新器
每日由 run_daily.py 呼叫，更新 new_high_watchlist.json 中每檔的當前狀態
與舊有 watchlist.json (MACD) 完全獨立

讀取/寫入: data/new_high_watchlist.json
"""

import requests
import json
import os
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# ⚠️ 與舊 watchlist.json 隔離
NHWL_PATH = os.path.join(DATA_DIR, 'new_high_watchlist.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}


def fetch_yahoo_kline(stock_code, range_str='1y'):
    """抓 Yahoo Finance K 線"""
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{stock_code}.TW?interval=1d&range={range_str}'
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        data = r.json()
        result = data.get('chart', {}).get('result', [])
        if not result:
            return None
        chart = result[0]
        timestamps = chart.get('timestamp', [])
        quote = chart.get('indicators', {}).get('quote', [{}])[0]
        highs   = quote.get('high', [])
        closes  = quote.get('close', [])
        
        clean = []
        for ts, h, c in zip(timestamps, highs, closes):
            if h is not None and c is not None:
                clean.append({
                    'date': datetime.fromtimestamp(ts).strftime('%Y-%m-%d'),
                    'high': h,
                    'close': c,
                })
        return clean if clean else None
    except Exception:
        return None


def update_stock_status(stock):
    """更新單檔狀態"""
    code = stock['code']
    added_date = stock.get('added_date', '')
    
    kline = fetch_yahoo_kline(code, range_str='1y')
    if not kline:
        return stock
    
    today = kline[-1]
    today_close = today['close']
    today_high  = today['high']
    
    stock['current_price'] = round(today_close, 2)
    stock['last_updated']  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 漲跌幅
    if stock.get('added_price'):
        added_price = float(stock['added_price'])
        if added_price > 0:
            stock['pct_change'] = round((today_close - added_price) / added_price * 100, 2)
    
    # 加入後最高/最低
    after_kline = [k for k in kline if k['date'] >= added_date] if added_date else kline
    if after_kline:
        stock['highest_after'] = round(max(k['high']  for k in after_kline), 2)
        stock['lowest_after']  = round(min(k['close'] for k in after_kline), 2)
    
    # 是否仍創 240 日新高
    if len(kline) >= 241:
        past_240 = [k['high'] for k in kline[-241:-1]]
        stock['still_new_high'] = today_high >= max(past_240)
    elif len(kline) >= 21:
        past_all = [k['high'] for k in kline[:-1]]
        stock['still_new_high'] = today_high >= max(past_all) if past_all else None
    else:
        stock['still_new_high'] = None
    
    # 從加入後最高的回檔幅度
    if stock.get('highest_after') and stock['highest_after'] > 0:
        pullback = (stock['highest_after'] - today_close) / stock['highest_after'] * 100
        stock['pullback_from_peak'] = round(pullback, 2)
    
    return stock


def main():
    if not os.path.exists(NHWL_PATH):
        print('  新高觀察清單尚未建立，略過')
        return
    
    with open(NHWL_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 兼容性檢查
    if isinstance(data, list):
        print('  ⚠ 偵測到舊格式 list，跳過更新（請檢查檔案格式）')
        return
    
    stocks = data.get('stocks', [])
    if not stocks:
        print('  新高觀察清單為空，略過')
        return
    
    print(f'  更新 {len(stocks)} 檔新高觀察清單…', flush=True)
    for i, stock in enumerate(stocks, 1):
        try:
            update_stock_status(stock)
            print(f'    [{i}/{len(stocks)}] {stock["code"]} {stock.get("name","")} '
                  f'{stock.get("current_price","-")} '
                  f'({stock.get("pct_change","-")}%)',
                  flush=True)
        except Exception as e:
            print(f'    [{i}/{len(stocks)}] {stock["code"]} 失敗: {e}', flush=True)
        time.sleep(0.2)
    
    data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    tmp = NHWL_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, NHWL_PATH)
    
    print(f'  ✓ 完成')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'✗ 錯誤: {e}')
        import traceback
        traceback.print_exc()
