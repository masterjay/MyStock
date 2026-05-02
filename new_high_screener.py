#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新高雷達 - 篩選成交量前200大中創新高的股票
分級: 20日 / 60日 / 120日 / 240日 / 歷史新高
加分條件: 突破當日量 > MA20 × 1.5 (爆量突破)
輸出: data/new_high_stocks.json
"""

import requests
import json
import time
import os
import sys
from datetime import datetime
from io import StringIO
import csv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUT_PATH = os.path.join(DATA_DIR, 'new_high_stocks.json')

os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9',
}

# 新高分級門檻（交易日）
HIGH_LEVELS = [
    ('high_20',  20,  '20日'),
    ('high_60',  60,  '60日'),
    ('high_120', 120, '120日'),
    ('high_240', 240, '240日'),
]

# 篩選池大小
TOP_N = 200

# 爆量突破門檻
VOLUME_BREAKOUT_RATIO = 1.5


# ─────────────────────────────────────────
# 1. 取得當日成交量前 N 大股票
# ─────────────────────────────────────────
def fetch_top_volume_stocks(top_n=TOP_N):
    """從 TWSE MI_INDEX20 API 取得當日成交量排行"""
    print(f'[1/3] 抓取當日成交量前 {top_n} 大股票…', flush=True)
    
    today = datetime.now().strftime('%Y%m%d')
    url = f'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX20?date={today}&response=json'
    
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        data = r.json()
        
        if data.get('stat') != 'OK' or not data.get('data'):
            # 假日或當日無資料 - 嘗試取最近交易日
            print('  當日無資料，嘗試前 5 日…', flush=True)
            from datetime import timedelta
            for i in range(1, 6):
                d = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
                url = f'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX20?date={d}&response=json'
                r = requests.get(url, headers=HEADERS, timeout=20)
                data = r.json()
                if data.get('stat') == 'OK' and data.get('data'):
                    print(f'  使用 {d} 的資料', flush=True)
                    break
            else:
                print('  ✗ 無法取得近期交易日資料', flush=True)
                return []
        
        # MI_INDEX20 格式: [rank, code, name, volume, trades, open, high, low, close, change_symbol, change_price, ...]
        # rank 是 int (依成交量排序)
        stocks = []
        for row in data['data']:
            try:
                rank = int(row[0])
                code = row[1].strip()
                name = row[2].strip()
                volume = int(str(row[3]).replace(',', ''))
                close = float(str(row[8]).replace(',', '')) if row[8] else 0
                
                stocks.append({
                    'rank': rank,
                    'code': code,
                    'name': name,
                    'volume': volume,
                    'close': close,
                    'amount_e': round(volume * close / 1e8, 2),  # 成交額(億)
                })
            except (ValueError, IndexError):
                continue
        
        # MI_INDEX20 只有 20 檔，需要再抓 STOCK_DAY_AVG_ALL 補足前 N 大
        # 先用這 20 檔，後面再補
        if len(stocks) < top_n:
            extra = fetch_extra_volume_stocks(top_n - len(stocks), exclude={s['code'] for s in stocks})
            stocks.extend(extra)
        
        stocks = stocks[:top_n]
        print(f'  ✓ 取得 {len(stocks)} 檔', flush=True)
        return stocks
        
    except Exception as e:
        print(f'  ✗ 抓取失敗: {e}', flush=True)
        return []


def fetch_extra_volume_stocks(need, exclude):
    """補抓前 N 大成交量股票（從 STOCK_DAY_ALL）"""
    today = datetime.now().strftime('%Y%m%d')
    url = f'https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json'
    
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        data = r.json()
        
        if not data.get('data'):
            return []
        
        # STOCK_DAY_ALL 格式: [code, name, trade_volume, transaction, trade_value, open, high, low, close, ...]
        candidates = []
        for row in data['data']:
            try:
                code = row[0].strip()
                if code in exclude:
                    continue
                # 跳過 ETF / 興櫃 / 特殊代號（一般 4 碼上市股）
                if not (len(code) == 4 and code.isdigit()):
                    continue
                
                name = row[1].strip()
                volume = int(str(row[2]).replace(',', '')) if row[2] else 0
                close = float(str(row[8]).replace(',', '')) if row[8] else 0
                
                if volume == 0 or close == 0:
                    continue
                
                candidates.append({
                    'code': code,
                    'name': name,
                    'volume': volume,
                    'close': close,
                    'amount_e': round(volume * close / 1e8, 2),
                })
            except (ValueError, IndexError):
                continue
        
        # 依成交量排序
        candidates.sort(key=lambda x: x['volume'], reverse=True)
        return candidates[:need]
        
    except Exception as e:
        print(f'  補抓失敗: {e}', flush=True)
        return []


# ─────────────────────────────────────────
# 2. 抓 Yahoo Finance K 線資料 (2 年 = 約 500 個交易日)
# ─────────────────────────────────────────
def fetch_yahoo_kline(stock_code, range_str='2y'):
    """從 Yahoo Finance 抓取 K 線資料"""
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
        volumes = quote.get('volume', [])
        
        # 過濾 None 值
        clean = []
        for ts, h, c, v in zip(timestamps, highs, closes, volumes):
            if h is not None and c is not None and v is not None:
                clean.append({
                    'ts': ts,
                    'high': h,
                    'close': c,
                    'volume': v,
                })
        
        return clean if len(clean) >= 20 else None
        
    except Exception:
        return None


# ─────────────────────────────────────────
# 3. 計算新高分級
# ─────────────────────────────────────────
def analyze_new_high(kline):
    """計算各週期新高狀態"""
    if not kline or len(kline) < 20:
        return None
    
    today = kline[-1]
    today_high = today['high']
    today_close = today['close']
    today_volume = today['volume']
    
    result = {
        'today_close': round(today_close, 2),
        'today_high':  round(today_high, 2),
    }
    
    # 各週期新高判定（不含當日）
    for key, days, label in HIGH_LEVELS:
        if len(kline) < days + 1:
            result[key] = None
            continue
        # 過去 N 日的最高（不含今天）
        past_highs = [k['high'] for k in kline[-(days+1):-1]]
        prev_max = max(past_highs)
        result[key] = today_high >= prev_max
        result[f'{key}_prev'] = round(prev_max, 2)
    
    # 歷史新高（用全部 K 線資料）
    past_all_highs = [k['high'] for k in kline[:-1]]
    if past_all_highs:
        all_time_max = max(past_all_highs)
        result['high_all'] = today_high >= all_time_max
        result['high_all_prev'] = round(all_time_max, 2)
    else:
        result['high_all'] = False
        result['high_all_prev'] = today_high
    
    # 新高強度評分（多少個級別創新高）
    levels_passed = sum(1 for key, _, _ in HIGH_LEVELS if result.get(key) is True)
    if result.get('high_all'):
        levels_passed += 1  # 歷史新高再加一星
    result['strength'] = levels_passed
    
    # 爆量突破判定
    if len(kline) >= 21:
        ma20_volume = sum(k['volume'] for k in kline[-21:-1]) / 20
        result['volume_ma20']   = int(ma20_volume)
        result['volume_ratio']  = round(today_volume / ma20_volume, 2) if ma20_volume > 0 else 0
        result['volume_breakout'] = result['volume_ratio'] >= VOLUME_BREAKOUT_RATIO
    else:
        result['volume_ratio'] = 0
        result['volume_breakout'] = False
    
    return result


# ─────────────────────────────────────────
# 4. 主流程
# ─────────────────────────────────────────
def main():
    start_time = time.time()
    
    # Step 1: 取得篩選池（成交量前 200 大）
    pool = fetch_top_volume_stocks(TOP_N)
    if not pool:
        print('✗ 篩選池為空，結束')
        return
    
    # Step 2: 對每檔抓 K 線並分析
    print(f'[2/3] 抓 Yahoo Finance K 線並分析新高（{len(pool)} 檔）…', flush=True)
    new_high_stocks = []
    failed = []
    
    for i, stock in enumerate(pool, 1):
        if i % 20 == 0:
            print(f'  進度 {i}/{len(pool)}', flush=True)
        
        kline = fetch_yahoo_kline(stock['code'])
        if not kline:
            failed.append(stock['code'])
            continue
        
        analysis = analyze_new_high(kline)
        if not analysis:
            failed.append(stock['code'])
            continue
        
        # 只保留至少創 20 日新高的股票
        if analysis.get('strength', 0) >= 1:
            stock_record = {
                'rank':       stock.get('rank', i),
                'code':       stock['code'],
                'name':       stock['name'],
                'volume':     stock['volume'],
                'amount_e':   stock['amount_e'],
                **analysis,
            }
            new_high_stocks.append(stock_record)
        
        time.sleep(0.15)  # 避免被 Yahoo 限流
    
    # 依強度 + 成交額排序
    new_high_stocks.sort(
        key=lambda x: (-x['strength'], -x['amount_e'])
    )
    
    # Step 3: 輸出 JSON
    print(f'[3/3] 輸出結果…', flush=True)
    output = {
        'updated_at':   datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'pool_size':    len(pool),
        'analyzed':     len(pool) - len(failed),
        'failed':       failed,
        'new_high_count': len(new_high_stocks),
        'breakdown': {
            'high_20':  sum(1 for s in new_high_stocks if s.get('high_20')),
            'high_60':  sum(1 for s in new_high_stocks if s.get('high_60')),
            'high_120': sum(1 for s in new_high_stocks if s.get('high_120')),
            'high_240': sum(1 for s in new_high_stocks if s.get('high_240')),
            'high_all': sum(1 for s in new_high_stocks if s.get('high_all')),
            'volume_breakout': sum(1 for s in new_high_stocks if s.get('volume_breakout')),
        },
        'stocks': new_high_stocks,
    }
    
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    elapsed = time.time() - start_time
    print(f'\n✓ 完成（耗時 {elapsed:.1f}s）')
    print(f'  輸出: {OUT_PATH}')
    print(f'  篩選池: {len(pool)} 檔，分析成功 {len(pool)-len(failed)} 檔')
    print(f'  創新高: {len(new_high_stocks)} 檔')
    print(f'    20日:  {output["breakdown"]["high_20"]}')
    print(f'    60日:  {output["breakdown"]["high_60"]}')
    print(f'    120日: {output["breakdown"]["high_120"]}')
    print(f'    240日: {output["breakdown"]["high_240"]}')
    print(f'    歷史:  {output["breakdown"]["high_all"]}')
    print(f'    爆量突破: {output["breakdown"]["volume_breakout"]}')
    
    # 顯示 top 10
    print('\n── 強度前 10 ──')
    for s in new_high_stocks[:10]:
        stars = '★' * s['strength']
        flags = []
        if s.get('high_20'):  flags.append('20')
        if s.get('high_60'):  flags.append('60')
        if s.get('high_120'): flags.append('120')
        if s.get('high_240'): flags.append('240')
        if s.get('high_all'): flags.append('歷史')
        vol_flag = ' 🔥爆量' if s.get('volume_breakout') else ''
        print(f'  {s["code"]} {s["name"]:8s} {stars} [{"/".join(flags)}日新高] '
              f'收{s["today_close"]} 量比{s["volume_ratio"]}{vol_flag}')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n中斷')
        sys.exit(1)
    except Exception as e:
        print(f'\n✗ 錯誤: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
