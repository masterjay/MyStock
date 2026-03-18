#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主流股雷達 - 成交市值排名篩選器
爬取近5日成交金額 TOP 30，計算主流股6條件評分
輸出: data/top_volume_stocks.json
"""

import requests
import json
import time
import sqlite3
import os
import sys
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH  = os.path.join(BASE_DIR, 'stock_data.db')
OUT_PATH = os.path.join(DATA_DIR, 'top_volume_stocks.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://goodinfo.tw/',
    'Accept-Language': 'zh-TW,zh;q=0.9',
}

# ─────────────────────────────────────────
# 1. 爬 Goodinfo 成交金額排行 TOP 30
# ─────────────────────────────────────────
def fetch_goodinfo_top30():
    """爬取 Goodinfo 成交金額排行榜（今日 & 近幾日均值）"""
    url = 'https://goodinfo.tw/tw/StockList.asp?MARKET_CAT=上市&INDUSTRY_CAT=ALL&SHEET=交易&FILTER_COLUMN=TRADING_PRICE&FILTER_INFO=&FILTER_START=&FILTER_END=&ORDER_COL=AMOUNT&ORDER_TYPE=DESC&SHEET2=&MEMO='
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        stocks = []
        table = soup.find('table', id='tblStockList')
        if not table:
            # fallback: 找第一個有股票代號的大表
            tables = soup.find_all('table', class_=re.compile('b1'))
            table = tables[0] if tables else None
        
        if not table:
            print("  ⚠ 找不到排行表格，嘗試備用解析")
            return fetch_twse_top30_fallback()
        
        rows = table.find_all('tr')
        for row in rows[2:]:  # 跳過表頭
            cols = row.find_all('td')
            if len(cols) < 8:
                continue
            try:
                rank  = len(stocks) + 1
                code  = cols[0].get_text(strip=True)
                name  = cols[1].get_text(strip=True)
                price = cols[2].get_text(strip=True).replace(',', '')
                chg   = cols[3].get_text(strip=True)
                vol   = cols[5].get_text(strip=True).replace(',', '')
                amt   = cols[6].get_text(strip=True).replace(',', '')  # 成交金額(億)
                
                if not re.match(r'^\d{4}', code):
                    continue
                
                stocks.append({
                    'rank': rank,
                    'code': code,
                    'name': name,
                    'price': float(price) if price else 0,
                    'change_pct': chg,
                    'volume': float(vol) if vol else 0,
                    'amount_b': float(amt) if amt else 0,  # 億元
                })
                
                if len(stocks) >= 30:
                    break
            except:
                continue
        
        print(f"  → Goodinfo 爬到 {len(stocks)} 檔")
        return stocks
    
    except Exception as e:
        print(f"  ⚠ Goodinfo 爬蟲失敗: {e}")
        return fetch_twse_top30_fallback()


def fetch_twse_top30_fallback():
    """備用：TWSE MI_INDEX 全量資料，自己排序取 TOP 30"""
    today = datetime.now().strftime('%Y%m%d')
    url = f'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={today}&type=ALLBUT0999&response=json'
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        data = resp.json()
        stocks = []
        
        if data.get('stat') != 'OK':
            print(f"  ⚠ TWSE MI_INDEX 回應異常: {data.get('stat')}")
            return []
        
        # MI_INDEX 回傳多個 tables，找欄位數 >= 16 的個股明細表
        tables = data.get('tables', [])
        target_rows = []
        for table in tables:
            rows = table.get('data', [])
            if rows and len(rows[0]) >= 16:
                target_rows = rows
                break
        
        # fallback: 直接找頂層 data（舊版格式）
        if not target_rows:
            target_rows = data.get('data', [])
        
        for row in target_rows:
            if len(row) < 9:
                continue
            try:
                code      = str(row[0]).strip()
                name      = str(row[1]).strip()
                vol_str   = str(row[2]).replace(',', '')
                amt_str   = str(row[4]).replace(',', '')   # 成交金額(元)
                price_str = str(row[8]).replace(',', '').replace('--', '0')
                chg_str   = str(row[10]).replace(',', '') if len(row) > 10 else '0'
                
                if not re.match(r'^\d{4}', code):
                    continue
                
                vol   = float(vol_str)   if vol_str.replace('.','').isdigit()   else 0
                amt   = float(amt_str)   if amt_str.replace('.','').isdigit()   else 0
                price = float(price_str) if price_str.replace('.','').isdigit() else 0
                amt_b = amt / 1e8
                
                stocks.append({
                    'code': code, 'name': name,
                    'price': price, 'change_pct': chg_str,
                    'volume': vol, 'amount_b': amt_b,
                })
            except:
                continue
        
        # 依成交金額排序，過濾 ETF，取 TOP 30
        stocks.sort(key=lambda x: x['amount_b'], reverse=True)
        stocks = [s for s in stocks if not str(s['code']).startswith('00')]
        for i, s in enumerate(stocks[:30]):
            s['rank'] = i + 1
        
        print(f"  → TWSE fallback 爬到 {len(stocks[:30])} 檔（全市場排序）")
        return stocks[:30]
    
    except Exception as e:
        print(f"  ⚠ TWSE MI_INDEX fallback 失敗: {e}")
        return []


# ─────────────────────────────────────────
# 2. 讀歷史資料計算各項條件
# ─────────────────────────────────────────
# Yahoo Finance K線快取（避免重複爬）
_yahoo_cache = {}

def fetch_yahoo_kline(stock_code, days=30):
    """爬 Yahoo Finance 取個股K線（含MA20/volume_ratio計算）"""
    if stock_code in _yahoo_cache:
        return _yahoo_cache[stock_code]
    
    ticker = stock_code + '.TW'
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=60d'
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        data = resp.json()
        result_data = data['chart']['result'][0]
        quotes = result_data['indicators']['quote'][0]
        closes  = quotes.get('close', [])
        volumes = quotes.get('volume', [])
        
        # 過濾 None
        closes  = [c for c in closes  if c is not None]
        volumes = [v for v in volumes if v is not None]
        
        if len(closes) < 5:
            _yahoo_cache[stock_code] = {}
            return {}
        
        # 計算 MA20
        ma20 = sum(closes[-20:]) / min(len(closes), 20)
        
        # volume_ratio：今日量 / 近20日均量
        avg_vol = sum(volumes[-20:]) / min(len(volumes), 20) if volumes else 0
        vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 0
        
        # 近3日量是否持續上揚
        vol_rising = len(volumes) >= 3 and volumes[-1] > volumes[-2] > volumes[-3]
        
        result = {
            'price':        closes[-1],
            'ma20':         round(ma20, 2),
            'volume_ratio': round(vol_ratio, 2),
            'vol_rising':   vol_rising,
            'closes':       closes,
            'volumes':      volumes,
        }
        _yahoo_cache[stock_code] = result
        time.sleep(0.3)  # 避免被封
        return result
    except Exception as e:
        _yahoo_cache[stock_code] = {}
        return {}


def load_history_from_db(stock_code, days=25):
    return []

def load_institutional_from_db(stock_code, days=5):
    return []


def calc_ema(prices, period):
    """計算 EMA"""
    if len(prices) < period:
        return []
    k = 2 / (period + 1)
    emas = [sum(prices[:period]) / period]
    for p in prices[period:]:
        emas.append(p * k + emas[-1] * (1 - k))
    return emas


def calc_ma(values, period):
    """計算 MA（移動平均）"""
    if len(values) < period:
        return []
    return [sum(values[i:i+period]) / period for i in range(len(values) - period + 1)]


# ─────────────────────────────────────────
# 3. 六條件判斷邏輯
# ─────────────────────────────────────────
def check_conditions(stock, history, inst_data, top30_history, macd_signals=None, inst_lookup=None):
    if inst_lookup is None: inst_lookup = {}
    # 從 macd_signals 補充 volume_ratio / ma20 / source
    if macd_signals and stock['code'] in macd_signals:
        m = macd_signals[stock['code']]
        if 'volume_ratio' not in stock: stock['volume_ratio'] = m.get('volume_ratio')
        if 'ma20'         not in stock: stock['ma20']         = m.get('ma20')
        if 'source'       not in stock: stock['source']       = m.get('source', '')
    """
    回傳各條件的判斷結果
    條件:
    1. 近5日是否連續出現在成交金額前30
    2. 均量20是否持續翻揚（非一日衝量）
    3. 回檔時是否守住 EMA10/EMA20
    4. 外資或投信近5日是否持續買超
    5. 是否有明確基本面催化劑（非概念股）→ 人工標記
    6. 類股中是否為領漲股（非跟漲）→ 人工標記
    """
    code = stock['code']
    result = {
        'cond1_top30_5d': None,   # True/False/None(無資料)
        'cond2_vol_ma20': None,
        'cond3_ema_support': None,
        'cond4_institutional': None,
        'cond5_fundamental': None,  # 需人工標記
        'cond6_sector_leader': None,  # 需人工標記
        'details': {}
    }
    
    # ── 條件1：近5日連續上榜前30 ──
    if top30_history:
        appeared_days = sum(1 for day_list in top30_history if code in day_list)
        result['cond1_top30_5d'] = appeared_days >= 5
        result['details']['top30_days'] = appeared_days
    else:
        # 今天有上榜就算1天，其餘未知
        result['details']['top30_days'] = 1
        result['cond1_top30_5d'] = None  # 需觀察
    
    # ── 爬 Yahoo Finance 取K線資料 ──
    ydata = fetch_yahoo_kline(stock['code'])
    
    # ── 條件2：近3日量持續上揚（非一日衝量）──
    if ydata:
        result['cond2_vol_ma20'] = ydata.get('vol_rising', False)
        result['details']['volume_ratio'] = ydata.get('volume_ratio')
    else:
        # fallback: macd_signal_stocks
        vr = stock.get('volume_ratio')
        if vr is not None:
            result['cond2_vol_ma20'] = float(vr) >= 1.0
            result['details']['volume_ratio'] = vr
    
    # ── 條件3：收盤 > MA20 ──
    if ydata:
        price = ydata.get('price', 0)
        ma20  = ydata.get('ma20', 0)
        if price and ma20:
            result['cond3_ema_support'] = price > ma20
            result['details']['ma20'] = ma20
            result['details']['current_price'] = price
    else:
        price = stock.get('price', 0)
        ma20  = stock.get('ma20', 0)
        if price and ma20:
            result['cond3_ema_support'] = float(price) > float(ma20)
            result['details']['ma20'] = ma20
    
    # ── 條件4：法人買超（foreign_top_stocks.json）──
    inst_info = inst_lookup.get(stock['code'], {})
    if inst_info:
        foreign_buy = (inst_info.get('net') or 0) > 0
        trust_buy   = (inst_info.get('trust_net') or 0) > 0
        result['cond4_institutional'] = foreign_buy or trust_buy
        result['details']['foreign_net'] = inst_info.get('net', 0)
        result['details']['trust_net']   = inst_info.get('trust_net', 0)
    else:
        # fallback: macd source 欄位
        source = stock.get('source', '')
        if source:
            result['cond4_institutional'] = '外資' in source or '投信' in source
            result['details']['source'] = source
    
    # 條件5,6 預設 None（需人工確認）
    result['cond5_fundamental'] = None
    result['cond6_sector_leader'] = None
    
    # ── 計算自動分數（4條自動 + 2條人工）──
    auto_scores = [result['cond1_top30_5d'], result['cond2_vol_ma20'],
                   result['cond3_ema_support'], result['cond4_institutional']]
    auto_pass = sum(1 for c in auto_scores if c is True)
    result['auto_score'] = auto_pass  # 滿分4
    
    return result


# ─────────────────────────────────────────
# 4. 讀取既有的人工標記（保留上次確認）
# ─────────────────────────────────────────
def load_manual_marks():
    """讀取之前手動勾選的結果"""
    if not os.path.exists(OUT_PATH):
        return {}
    try:
        with open(OUT_PATH) as f:
            old = json.load(f)
        marks = {}
        for s in old.get('stocks', []):
            code = s['code']
            marks[code] = {
                'cond5_fundamental': s.get('conditions', {}).get('cond5_fundamental'),
                'cond6_sector_leader': s.get('conditions', {}).get('cond6_sector_leader'),
                'note': s.get('note', ''),
            }
        return marks
    except:
        return {}


# ─────────────────────────────────────────
# 5. 主流程
# ─────────────────────────────────────────
def run():
    os.makedirs(DATA_DIR, exist_ok=True)
    print("\n[主流股雷達] 開始執行...")
    
    # Step1: 爬今日 TOP 30
    print("  → 爬取成交金額 TOP 30...")
    top30_today = fetch_goodinfo_top30()
    
    # 過濾掉 ETF（00 開頭）
    top30_today = [s for s in top30_today if not str(s["code"]).startswith("00")]

    if not top30_today:
        print("  ✗ 無法取得排行資料，跳過")
        return False
    
    # Step2: 讀取並更新 top30 近5日歷史（存在 JSON 裡）
    top30_history_path = os.path.join(DATA_DIR, 'top30_history.json')
    try:
        with open(top30_history_path) as f:
            top30_hist = json.load(f)
    except:
        top30_hist = []
    
    today_codes = [s['code'] for s in top30_today]
    today_str = datetime.now().strftime('%Y%m%d')
    
    # 加入今日
    if not top30_hist or top30_hist[-1].get('date') != today_str:
        top30_hist.append({'date': today_str, 'codes': today_codes})
    else:
        top30_hist[-1]['codes'] = today_codes  # 更新同日
    
    # 只保留近10日
    top30_hist = top30_hist[-10:]
    with open(top30_history_path, 'w') as f:
        json.dump(top30_hist, f, ensure_ascii=False, indent=2)
    
    # 近5日每日的 codes list
    recent5 = [d['codes'] for d in top30_hist[-5:]]
    
    # Step3: 計算每檔的條件
    manual_marks = load_manual_marks()
    result_stocks = []

    # 載入 foreign_top_stocks.json 建立法人查找表
    inst_lookup = {}
    try:
        with open(os.path.join(DATA_DIR, 'foreign_top_stocks.json')) as f:
            fdata = json.load(f)
        for s in fdata.get('top_buy', []) + fdata.get('top_sell', []) +                  fdata.get('trust_top_buy', []) + fdata.get('trust_top_sell', []):
            code = s['code']
            if code not in inst_lookup:
                inst_lookup[code] = s
            else:
                # 合併 trust_net
                if s.get('trust_net'): inst_lookup[code]['trust_net'] = s['trust_net']
        print(f"  → 載入法人資料 {len(inst_lookup)} 檔")
    except Exception as e:
        print(f"  ⚠ 法人資料載入失敗: {e}")

    # 載入 macd_signal_stocks.json 作為補充資料源
    macd_signals = {}
    try:
        with open(os.path.join(DATA_DIR, 'macd_signal_stocks.json')) as f:
            macd_data = json.load(f)
        for s in macd_data.get('signals', []):
            macd_signals[s['code']] = s
        print(f"  → 載入 MACD 資料 {len(macd_signals)} 檔")
    except:
        pass

    print(f"  → 計算 {len(top30_today)} 檔條件分數...")
    for stock in top30_today:
        code = stock['code']
        history  = load_history_from_db(code, days=25)
        inst     = load_institutional_from_db(code, days=5)
        conds    = check_conditions(stock, history, inst, recent5, macd_signals, inst_lookup)
        
        # 還原人工標記
        if code in manual_marks:
            conds['cond5_fundamental']  = manual_marks[code].get('cond5_fundamental')
            conds['cond6_sector_leader']= manual_marks[code].get('cond6_sector_leader')
        
        # 計算總分
        all_conds = [conds['cond1_top30_5d'], conds['cond2_vol_ma20'],
                     conds['cond3_ema_support'], conds['cond4_institutional'],
                     conds['cond5_fundamental'], conds['cond6_sector_leader']]
        total_pass = sum(1 for c in all_conds if c is True)
        total_known = sum(1 for c in all_conds if c is not None)
        
        result_stocks.append({
            'rank': stock['rank'],
            'code': code,
            'name': stock['name'],
            'price': stock['price'],
            'change_pct': stock['change_pct'],
            'amount_b': stock['amount_b'],
            'conditions': conds,
            'total_pass': total_pass,
            'total_known': total_known,
            'is_mainstream': total_pass >= 4,  # 4條以上通過 = 主流股
            'note': manual_marks.get(code, {}).get('note', ''),
        })
    
    # 依「通過條件數」排序
    result_stocks.sort(key=lambda x: (x['total_pass'], x['amount_b']), reverse=True)
    # 重新編排排名
    for i, s in enumerate(result_stocks):
        s['rank'] = i + 1
    
    output = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'date': today_str,
        'total_stocks': len(result_stocks),
        'mainstream_count': sum(1 for s in result_stocks if s['is_mainstream']),
        'stocks': result_stocks,
        'condition_labels': {
            'cond1_top30_5d':    '近5日連續出現在成交前30',
            'cond2_vol_ma20':    '均量20持續翻揚（非一日衝量）',
            'cond3_ema_support': '回檔守住 EMA10/EMA20',
            'cond4_institutional':'外資或投信近5日持續買超',
            'cond5_fundamental': '有明確基本面催化劑（非概念股）',
            'cond6_sector_leader':'類股中為領漲股（非跟漲）',
        }
    }
    
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"  ✓ 完成！主流股 {output['mainstream_count']} 檔 / 共 {len(result_stocks)} 檔")
    print(f"  → 輸出: {OUT_PATH}")
    return True


if __name__ == '__main__':
    run()
