#!/usr/bin/env python3
"""
MACD 訊號掃描器 v1.0
從外資50檔 + 週轉率名單中篩選符合交易策略的股票

策略條件:
1. 只買多頭股（股價在 MA20 之上）
2. 日線量縮（近5日均量 < 近20日均量）
3. MACD 柱狀體縮小，有機會翻紅（DIF-MACD 負值縮小中）
4. MACD 有機會金叉但不離0軸太遠（DIF 和 MACD 都在 0 軸附近）
5. 標記：金叉在0軸下 → 短線 / 金叉在0軸上 → 長線

輸出: data/macd_signal_stocks.json
"""

import json
import os
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================
# 設定
# ============================================================
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / 'data'

# MACD 參數
FAST_PERIOD = 12
SLOW_PERIOD = 26
SIGNAL_PERIOD = 9

# 篩選閾值（可調整）
MACD_ZERO_THRESHOLD = 2.0      # DIF/MACD 離 0 軸的最大距離（百分比化後）
VOLUME_SHRINK_RATIO = 0.85     # 近5日均量 / 近20日均量 < 此值視為量縮
HISTOGRAM_SHRINK_DAYS = 3      # 連續幾天柱狀體在縮小

# K線天數
KLINE_DAYS = 80  # 需要足夠天數計算 MACD(26) + Signal(9) + 判斷趨勢

# ============================================================
# K 線資料抓取（使用 TWSE API，不需要額外套件）
# ============================================================
def fetch_kline_twse(stock_code, days=80):
    """
    從 TWSE API 抓取個股日K線
    回傳 list of dict: [{'date', 'open', 'high', 'low', 'close', 'volume'}, ...]
    """
    import requests
    
    klines = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 需要抓多個月份的資料
    today = datetime.now()
    months_to_fetch = 5  # 抓近5個月確保有足夠資料
    
    for m in range(months_to_fetch):
        # 從上個月開始往回抓，避免當月無資料
        target = today.replace(day=1) - timedelta(days=30 * m + 1)
        date_str = target.strftime('%Y%m01')
        
        url = f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date={date_str}&stockNo={stock_code}&response=json"
        
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            data = resp.json()
            
            if data.get('stat') != 'OK' or not data.get('data'):
                continue
            
            for row in data['data']:
                try:
                    # 民國轉西元
                    date_parts = row[0].split('/')
                    year = int(date_parts[0]) + 1911
                    date_str_formatted = f"{year}/{date_parts[1]}/{date_parts[2]}"
                    
                    volume = int(row[1].replace(',', ''))
                    open_price = float(row[3].replace(',', ''))
                    high_price = float(row[4].replace(',', ''))
                    low_price = float(row[5].replace(',', ''))
                    close_price = float(row[6].replace(',', ''))
                    
                    klines.append({
                        'date': date_str_formatted,
                        'open': open_price,
                        'high': high_price,
                        'low': low_price,
                        'close': close_price,
                        'volume': volume
                    })
                except (ValueError, IndexError):
                    continue
            
            time.sleep(0.5)  # 避免被封
            
        except Exception as e:
            print(f"    ⚠ 抓取 {stock_code} {date_str} 失敗: {e}")
            continue
    
    # 去重並按日期排序
    seen = set()
    unique_klines = []
    for k in klines:
        if k['date'] not in seen:
            seen.add(k['date'])
            unique_klines.append(k)
    
    unique_klines.sort(key=lambda x: x['date'])
    return unique_klines


def fetch_kline_yahoo(stock_code, days=80):
    """
    備用方案：使用 yfinance 抓取 K 線
    需要 pip install yfinance
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(f"{stock_code}.TW")
        df = ticker.history(period=f"{days}d")
        
        if df.empty:
            return []
        
        klines = []
        for idx, row in df.iterrows():
            klines.append({
                'date': idx.strftime('%Y/%m/%d'),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': int(row['Volume'])
            })
        return klines
    except ImportError:
        return []
    except Exception:
        return []


def fetch_kline(stock_code, days=80):
    """優先用 Yahoo (穩定)，失敗用 TWSE"""
    klines = fetch_kline_yahoo(stock_code, days)
    if len(klines) < 35:
        print(f"    Yahoo 資料不足({len(klines)}筆)，嘗試 TWSE...")
        klines = fetch_kline_twse(stock_code, days)
    return klines


# ============================================================
# 技術指標計算
# ============================================================
def calc_ema(prices, period):
    """計算 EMA"""
    if len(prices) < period:
        return []
    
    ema = [0.0] * len(prices)
    multiplier = 2.0 / (period + 1)
    
    # 初始值用 SMA
    sma = sum(prices[:period]) / period
    ema[period - 1] = sma
    
    for i in range(period, len(prices)):
        ema[i] = (prices[i] - ema[i - 1]) * multiplier + ema[i - 1]
    
    return ema


def calc_macd(closes, fast=12, slow=26, signal=9):
    """
    計算 MACD
    回傳: dif[], macd_signal[], histogram[]
    """
    ema_fast = calc_ema(closes, fast)
    ema_slow = calc_ema(closes, slow)
    
    # DIF = EMA(fast) - EMA(slow)
    dif = [0.0] * len(closes)
    for i in range(slow - 1, len(closes)):
        dif[i] = ema_fast[i] - ema_slow[i]
    
    # MACD Signal = EMA(DIF, signal)
    dif_valid = dif[slow - 1:]
    macd_signal_raw = calc_ema(dif_valid, signal)
    
    macd_signal = [0.0] * len(closes)
    histogram = [0.0] * len(closes)
    
    start_idx = slow - 1
    for i in range(len(macd_signal_raw)):
        macd_signal[start_idx + i] = macd_signal_raw[i]
        histogram[start_idx + i] = dif[start_idx + i] - macd_signal_raw[i]
    
    return dif, macd_signal, histogram


def calc_ma(prices, period):
    """計算簡單移動平均"""
    if len(prices) < period:
        return []
    
    ma = [0.0] * len(prices)
    for i in range(period - 1, len(prices)):
        ma[i] = sum(prices[i - period + 1:i + 1]) / period
    return ma


# ============================================================
# 訊號判斷
# ============================================================
def analyze_stock(stock_code, stock_name, klines):
    """
    分析單檔股票是否符合 MACD 策略條件
    
    回傳: None (不符合) 或 dict (符合，包含訊號資訊)
    """
    if len(klines) < 40:
        return None
    
    closes = [k['close'] for k in klines]
    volumes = [k['volume'] for k in klines]
    current_price = closes[-1]
    
    # ---- 1. 多頭判斷：股價在 MA20 之上 ----
    ma20 = calc_ma(closes, 20)
    if not ma20 or ma20[-1] == 0:
        return None
    
    if current_price < ma20[-1]:
        return None  # 不是多頭，跳過
    
    # ---- 2. 量縮判斷 ----
    if len(volumes) < 20:
        return None
    
    vol_5 = sum(volumes[-5:]) / 5
    vol_20 = sum(volumes[-20:]) / 20
    
    if vol_20 == 0:
        return None
    
    vol_ratio = vol_5 / vol_20
    is_volume_shrink = vol_ratio < VOLUME_SHRINK_RATIO
    
    if not is_volume_shrink:
        return None  # 沒有量縮，跳過
    
    # ---- 3. MACD 計算 ----
    dif, macd_signal, histogram = calc_macd(closes, FAST_PERIOD, SLOW_PERIOD, SIGNAL_PERIOD)
    
    valid_start = SLOW_PERIOD + SIGNAL_PERIOD - 1
    if len(closes) <= valid_start:
        return None
    
    current_dif = dif[-1]
    current_macd = macd_signal[-1]
    current_hist = histogram[-1]
    
    # ---- 4. MACD 柱狀體縮小（有機會翻紅/金叉）----
    # 柱狀體為負且在縮小中（絕對值減小）
    is_hist_shrinking = False
    
    if len(histogram) >= valid_start + HISTOGRAM_SHRINK_DAYS + 1:
        recent_hists = histogram[-(HISTOGRAM_SHRINK_DAYS + 1):]
        
        # 柱狀體為負值（DIF < MACD，死叉狀態）
        if current_hist < 0:
            # 檢查是否在縮小（負值的絕對值在減少）
            shrinking = True
            for i in range(1, len(recent_hists)):
                if abs(recent_hists[i]) >= abs(recent_hists[i - 1]):
                    shrinking = False
                    break
            is_hist_shrinking = shrinking
        
        # 或者柱狀體剛翻紅（從負轉正）
        elif current_hist > 0 and len(histogram) >= 2 and histogram[-2] < 0:
            is_hist_shrinking = True  # 剛金叉
    
    if not is_hist_shrinking:
        return None
    
    # ---- 5. 不離 0 軸太遠 ----
    # 用 DIF 佔股價的百分比來判斷
    dif_pct = abs(current_dif / current_price * 100) if current_price > 0 else 999
    macd_pct = abs(current_macd / current_price * 100) if current_price > 0 else 999
    
    if dif_pct > MACD_ZERO_THRESHOLD or macd_pct > MACD_ZERO_THRESHOLD:
        return None  # 離 0 軸太遠
    
    # ---- 6. 判斷短線/長線 ----
    if current_dif > 0 and current_macd > 0:
        trade_type = "長線"  # 0軸上金叉
    else:
        trade_type = "短線"  # 0軸下金叉
    
    # ---- 7. 金叉狀態 ----
    is_golden_cross = current_dif > current_macd
    is_about_to_cross = (current_hist < 0 and abs(current_hist) < abs(histogram[-2]) * 0.5)
    
    if is_golden_cross:
        cross_status = "已金叉"
    elif is_about_to_cross:
        cross_status = "即將金叉"
    else:
        cross_status = "柱體縮小中"
    
    # ---- 組合結果 ----
    return {
        'code': stock_code,
        'name': stock_name,
        'price': current_price,
        'ma20': round(ma20[-1], 2),
        'dif': round(current_dif, 4),
        'macd': round(current_macd, 4),
        'histogram': round(current_hist, 4),
        'dif_pct': round(dif_pct, 4),
        'volume_ratio': round(vol_ratio, 2),
        'trade_type': trade_type,
        'cross_status': cross_status,
        'signal_strength': calc_signal_strength(
            vol_ratio, dif_pct, current_hist, histogram[-2] if len(histogram) >= 2 else 0
        ),
        'date': klines[-1]['date']
    }


def calc_signal_strength(vol_ratio, dif_pct, current_hist, prev_hist):
    """
    計算訊號強度 (1-5 顆星)
    量縮越明顯、離0軸越近、柱體縮小越快 = 越強
    """
    score = 0
    
    # 量縮程度（越縮越好）
    if vol_ratio < 0.6:
        score += 2
    elif vol_ratio < 0.75:
        score += 1
    
    # 離 0 軸距離（越近越好）
    if dif_pct < 0.5:
        score += 2
    elif dif_pct < 1.0:
        score += 1
    
    # 柱體縮小速度
    if prev_hist != 0:
        shrink_rate = 1 - abs(current_hist / prev_hist)
        if shrink_rate > 0.5:
            score += 1
    
    return min(max(score, 1), 5)


# ============================================================
# 主程式
# ============================================================
def load_stock_list():
    """從外資50檔(買+賣) + 週轉率名單 + 產業外資動向個股讀取股票清單"""
    stocks = {}
    
    # 1. 外資買超 + 賣超 Top 50
    foreign_path = DATA_DIR / 'foreign_top_stocks.json'
    if foreign_path.exists():
        try:
            with open(foreign_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for stock in data.get('top_buy', []):
                code = stock.get('code', '')
                if code and len(code) == 4 and code.isdigit():
                    stocks[code] = {
                        'name': stock.get('name', ''),
                        'source': '外資買超'
                    }
            buy_count = len(data.get('top_buy', []))
            
            for stock in data.get('top_sell', []):
                code = stock.get('code', '')
                if code and len(code) == 4 and code.isdigit():
                    if code not in stocks:
                        stocks[code] = {
                            'name': stock.get('name', ''),
                            'source': '外資賣超'
                        }
                    else:
                        stocks[code]['source'] += '+外資賣超'
            sell_count = len(data.get('top_sell', []))
            
            print(f"  ✓ 外資買超: {buy_count} 檔, 賣超: {sell_count} 檔")
        except Exception as e:
            print(f"  ✗ 讀取外資買賣超失敗: {e}")
    else:
        print(f"  ✗ 找不到 {foreign_path}")
    
    # 2. 週轉率名單
    turnover_path = DATA_DIR / 'turnover_analysis.json'
    if turnover_path.exists():
        try:
            with open(turnover_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            stock_list = []
            if isinstance(data, list):
                stock_list = data
            elif isinstance(data, dict):
                stock_list = (data.get('all_stocks', []) or 
                            data.get('active_stocks', []) or
                            data.get('stocks', []) or
                            data.get('data', []))
            
            count = 0
            for stock in stock_list:
                code = stock.get('code', stock.get('stock_id', ''))
                if code and len(code) == 4 and code.isdigit():
                    if code not in stocks:
                        stocks[code] = {
                            'name': stock.get('name', stock.get('stock_name', '')),
                            'source': '週轉率'
                        }
                    else:
                        stocks[code]['source'] += '+週轉率'
                    count += 1
            
            print(f"  ✓ 週轉率: {count} 檔")
        except Exception as e:
            print(f"  ✗ 讀取週轉率失敗: {e}")
    else:
        print(f"  ✗ 找不到 {turnover_path}")
    
    # 3. 產業外資動向個股（從 industry_heatmap.json）
    heatmap_path = DATA_DIR / 'industry_heatmap.json'
    if heatmap_path.exists():
        try:
            with open(heatmap_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            count = 0
            for industry_name, industry_data in data.get('industries', {}).items():
                for stock in industry_data.get('top_stocks', []):
                    code = stock.get('code', '')
                    if code and len(code) == 4 and code.isdigit():
                        if code not in stocks:
                            stocks[code] = {
                                'name': stock.get('name', ''),
                                'source': '產業外資'
                            }
                        else:
                            stocks[code]['source'] += '+產業外資'
                        count += 1
            
            print(f"  ✓ 產業外資動向: {count} 檔")
        except Exception as e:
            print(f"  ✗ 讀取產業外資動向失敗: {e}")
    else:
        print(f"  ✗ 找不到 {heatmap_path}")
    
    return stocks


def main():
    print(f"\n{'=' * 60}")
    print(f"📊 MACD 訊號掃描器 v1.0")
    print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}\n")
    
    # 1. 載入股票清單
    print("[1/3] 載入股票清單...")
    stocks = load_stock_list()
    
    if not stocks:
        print("  ✗ 沒有找到任何股票，請確認 JSON 檔案")
        return
    
    total = len(stocks)
    print(f"  → 合計 {total} 檔不重複股票\n")
    
    # 2. 逐檔分析
    print(f"[2/3] 逐檔抓取K線並分析 MACD 訊號...")
    print(f"  （預估需要 {total * 2} ~ {total * 3} 秒）\n")
    
    signals = []
    errors = []
    
    for i, (code, info) in enumerate(stocks.items(), 1):
        name = info['name']
        source = info['source']
        
        progress = f"[{i}/{total}]"
        print(f"  {progress} {code} {name} ({source})...", end=' ', flush=True)
        
        try:
            klines = fetch_kline(code, KLINE_DAYS)
            
            if len(klines) < 35:
                print(f"資料不足({len(klines)}筆)")
                continue
            
            result = analyze_stock(code, name, klines)
            
            if result:
                result['source'] = source
                signals.append(result)
                print(f"✅ {result['cross_status']} ({result['trade_type']}) ⭐{'⭐' * (result['signal_strength'] - 1)}")
            else:
                print("—")
            
            # 控制請求頻率，避免被封
            time.sleep(0.3)
            
        except Exception as e:
            print(f"✗ 錯誤: {e}")
            errors.append({'code': code, 'name': name, 'error': str(e)})
            continue
    
    # 3. 輸出結果
    print(f"\n[3/3] 輸出結果...")
    
    # 按訊號強度排序
    signals.sort(key=lambda x: (-x['signal_strength'], x['cross_status'] == '已金叉'))
    
    output = {
        'updated_at': datetime.now().isoformat(),
        'scan_date': datetime.now().strftime('%Y-%m-%d'),
        'total_scanned': total,
        'signal_count': len(signals),
        'signals': signals,

        'config': {
            'macd_params': f"{FAST_PERIOD},{SLOW_PERIOD},{SIGNAL_PERIOD}",
            'volume_shrink_ratio': VOLUME_SHRINK_RATIO,
            'macd_zero_threshold': MACD_ZERO_THRESHOLD,
            'histogram_shrink_days': HISTOGRAM_SHRINK_DAYS
        }
    }
    
    if errors:
        output['errors'] = errors
    
    
    # === 概念股標籤 ===
    try:
        from concept_stock_collector import enrich_signals_with_concepts
        signals = enrich_signals_with_concepts(signals)
        concept_tagged = sum(1 for s in signals if s.get('concepts'))
        print(f"  → {concept_tagged} 檔有概念股標籤")
    except ImportError:
        print("  ℹ concept_stock_collector 不存在，跳過概念標籤")
    except Exception as e:
        print(f"  ⚠ 概念標籤失敗: {e}")


    # === 概念股 meta ===
    try:
        concept_file = DATA_DIR / 'concept_stocks.json'
        if concept_file.exists():
            with open(concept_file, 'r', encoding='utf-8') as _f:
                _cdata = json.load(_f)
            output['concepts_meta'] = {
                cid: {'label': cd['label'], 'color': cd['color']}
                for cid, cd in _cdata.get('concepts', {}).items()
            }
    except Exception:
        pass
    output_path = DATA_DIR / 'macd_signal_stocks.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 保存歷史檔案（保留3天）
    scan_date_str = output["scan_date"].replace("-", "")
    history_path = DATA_DIR / f"macd_signal_{scan_date_str}.json"
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    # 清理超過3天的歷史檔案
    import glob
    history_files = sorted(glob.glob(str(DATA_DIR / "macd_signal_2*.json")), reverse=True)
    for old_file in history_files[3:]:
        os.remove(old_file)
        print(f"  🗑 清理舊檔: {os.path.basename(old_file)}")
    
    # 印出摘要
    print(f"\n{'=' * 60}")
    print(f"📊 掃描結果")
    print(f"{'=' * 60}")
    print(f"  掃描股票數: {total}")
    print(f"  符合條件: {len(signals)} 檔")
    if errors:
        print(f"  錯誤: {len(errors)} 檔")
    
    if signals:
        print(f"\n{'─' * 60}")
        print(f"  {'代碼':6s} {'名稱':8s} {'股價':>8s} {'DIF%':>8s} {'量縮比':>8s} {'狀態':10s} {'類型':4s} {'強度':6s}")
        print(f"{'─' * 60}")
        for s in signals:
            stars = '⭐' * s['signal_strength']
            print(f"  {s['code']:6s} {s['name']:8s} {s['price']:8.2f} {s['dif_pct']:7.3f}% {s['volume_ratio']:8.2f} {s['cross_status']:10s} {s['trade_type']:4s} {stars}")
    
    print(f"\n✓ 已輸出至 {output_path}")
    print(f"{'=' * 60}\n")


if __name__ == '__main__':
    main()
