#!/usr/bin/env python3
"""
處置股資料抓取腳本 (disposal_stocks.py)
- 抓取 TWSE (上市) 和 TPEx (上櫃) 處置股公告
- 抓取注意股公告 (風險股)
- 與持股/觀察名單比對，輸出 JSON 供 dashboard 使用
- 外連處置大師做進階預測

放置路徑: ~/MyStock/backend/disposal_stocks.py
輸出路徑: ~/MyStock/backend/data/disposal_stocks.json
"""

import requests
import json
import re
import os
import sys
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# ============================================================
# 設定區
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'data')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'disposal_stocks.json')

# 持股 + 觀察名單
# TODO: 改成讀取 watchlist_notion.json 自動同步
WATCHLIST_FILE = os.path.join(SCRIPT_DIR, '..', 'watchlist_notion.json')

def load_watchlist():
    """從 Notion watchlist JSON 或 hardcode 載入觀察名單"""
    # 嘗試讀取 Notion 同步的 watchlist
    try:
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 根據你的 watchlist_notion.json 格式調整
            watchlist = {}
            if isinstance(data, list):
                for item in data:
                    sid = str(item.get('stock_id', item.get('代號', item.get('id', '')))).strip()
                    sname = item.get('stock_name', item.get('名稱', item.get('name', ''))).strip()
                    if sid:
                        watchlist[sid] = sname
            elif isinstance(data, dict):
                # 可能是 { "stocks": [...] } 格式
                stocks = data.get('stocks', data.get('data', []))
                if isinstance(stocks, list):
                    for item in stocks:
                        sid = str(item.get('stock_id', item.get('代號', ''))).strip()
                        sname = item.get('stock_name', item.get('名稱', '')).strip()
                        if sid:
                            watchlist[sid] = sname
                else:
                    watchlist = data  # 直接就是 {"代號": "名稱"} 格式
            if watchlist:
                print(f"[Watchlist] 從 {WATCHLIST_FILE} 載入 {len(watchlist)} 檔")
                return watchlist
    except Exception as e:
        print(f"[Watchlist] 讀取 watchlist_notion.json 失敗: {e}")

    # Fallback: 硬編碼
    print("[Watchlist] 使用硬編碼名單")
    return {
        "2330": "台積電",
        "2449": "京元電子",
        "1560": "中砂",
        "4979": "華星光",
        "4772": "台特化",
        "8150": "南茂",
        "2492": "華新科",
        "3044": "健鼎",
        "3016": "嘉晶",
        "3374": "精材",
        "8086": "宏捷科",
        "6197": "佳必琪",
        "3305": "昇貿",
        "3265": "台星科",
        "3163": "波若威",
    }


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/html',
    'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
}


# ============================================================
# TWSE 上市處置股
# ============================================================
def fetch_twse_disposal():
    """抓取 TWSE 處置有價證券"""
    url = 'https://www.twse.com.tw/announcement/punish'
    params = {'response': 'json'}
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = resp.json()
        if data.get('stat') != 'OK' or not data.get('data'):
            print(f"[TWSE處置] 無資料或狀態異常: {data.get('stat')}")
            return []

        results = []
        for row in data['data']:
            stock_id = row[2].strip() if len(row) > 2 else ''
            stock_name = row[3].strip() if len(row) > 3 else ''
            announce_date = row[1].strip() if len(row) > 1 else ''
            condition = row[5].strip() if len(row) > 5 else ''
            period = row[6].strip() if len(row) > 6 else ''
            measure = row[7].strip() if len(row) > 7 else ''
            content = row[8].strip() if len(row) > 8 else ''

            start_date, end_date = parse_period(period)
            match_freq = extract_match_frequency(content)

            results.append({
                'stock_id': stock_id,
                'stock_name': stock_name,
                'market': '上市',
                'announce_date': announce_date,
                'condition': condition,
                'period': period,
                'start_date': start_date,
                'end_date': end_date,
                'measure': measure,
                'match_frequency': match_freq,
            })
        print(f"[TWSE處置] 抓到 {len(results)} 筆")
        return results
    except Exception as e:
        print(f"[TWSE處置] 錯誤: {e}")
        return []


# ============================================================
# TPEx 上櫃處置股 (修正版)
# ============================================================
def fetch_tpex_disposal():
    """
    抓取 TPEx 上櫃處置股
    方案一: OpenAPI /tpex_cmode (變更交易/分盤交易)
    方案二: 傳統網頁 API
    """
    results = []

    # --- 方案一: OpenAPI tpex_cmode ---
    try:
        url = 'https://www.tpex.org.tw/openapi/v1/tpex_cmode'
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                # 先看一下欄位名稱 (debug 用)
                sample_keys = list(data[0].keys()) if data else []
                print(f"[TPEx處置] OpenAPI 欄位: {sample_keys}")

                for row in data:
                    row_text = json.dumps(row, ensure_ascii=False)

                    # 取 stock_id & name (嘗試各種欄位名稱)
                    stock_id = ''
                    stock_name = ''
                    for k in ['SecuritiesCompanyCode', 'Code', '證券代號', 'stkno']:
                        if k in row and row[k]:
                            stock_id = str(row[k]).strip()
                            break
                    for k in ['CompanyName', 'Name', '證券名稱', 'stkname']:
                        if k in row and row[k]:
                            stock_name = str(row[k]).strip()
                            break

                    if not stock_id:
                        vals = list(row.values())
                        if len(vals) >= 2:
                            stock_id = str(vals[0]).strip()
                            stock_name = str(vals[1]).strip()

                    # 撮合頻率
                    match_freq = extract_match_frequency(row_text)

                    # 處置期間
                    period = ''
                    for k in ['DisposalPeriod', '處置期間', 'Period']:
                        if k in row and row[k]:
                            period = str(row[k]).strip()
                            break
                    start_date, end_date = parse_period(period)

                    # 備註/措施
                    measure = ''
                    for k in ['Remark', '備註', '措施', 'Measure']:
                        if k in row and row[k]:
                            measure = str(row[k]).strip()
                            break

                    results.append({
                        'stock_id': stock_id,
                        'stock_name': stock_name,
                        'market': '上櫃',
                        'announce_date': '',
                        'condition': '',
                        'period': period,
                        'start_date': start_date,
                        'end_date': end_date,
                        'measure': measure,
                        'match_frequency': match_freq,
                    })

                print(f"[TPEx處置] OpenAPI 抓到 {len(results)} 筆")
                return results
    except Exception as e:
        print(f"[TPEx處置] OpenAPI 失敗: {e}")

    # --- 方案二: 傳統 web API ---
    try:
        today = datetime.now()
        roc_date = f"{today.year - 1911}/{today.month:02d}/{today.day:02d}"
        url = 'https://www.tpex.org.tw/web/bulletin/disposal/disposal_result.php'
        params = {'l': 'zh-tw', 'd': roc_date, 'o': 'json'}
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)

        try:
            data = resp.json()
            rows = (data.get('reportList') or data.get('aaData') or
                    data.get('data') or [])
            for row in rows:
                if isinstance(row, list):
                    stock_id = str(row[1]).strip() if len(row) > 1 else ''
                    stock_name = str(row[2]).strip() if len(row) > 2 else ''
                    period = str(row[4]).strip() if len(row) > 4 else ''
                    measure = str(row[5]).strip() if len(row) > 5 else ''
                elif isinstance(row, dict):
                    stock_id = (row.get('SecuritiesCompanyCode', '') or
                                row.get('stkno', '')).strip()
                    stock_name = (row.get('CompanyName', '') or
                                  row.get('stkname', '')).strip()
                    period = row.get('DisposalPeriod', '').strip()
                    measure = row.get('DisposalMeasures', '').strip()
                else:
                    continue

                start_date, end_date = parse_period(period)
                match_freq = extract_match_frequency(measure + period)
                results.append({
                    'stock_id': stock_id,
                    'stock_name': stock_name,
                    'market': '上櫃',
                    'announce_date': '',
                    'condition': '',
                    'period': period,
                    'start_date': start_date,
                    'end_date': end_date,
                    'measure': measure,
                    'match_frequency': match_freq,
                })
            if results:
                print(f"[TPEx處置] Web JSON 抓到 {len(results)} 筆")
                return results
        except (json.JSONDecodeError, ValueError):
            pass

        # HTML fallback
        soup = BeautifulSoup(resp.text, 'html.parser')
        for table in soup.find_all('table'):
            trs = table.find_all('tr')
            if len(trs) < 2:
                continue
            header_text = trs[0].get_text()
            if '證券' not in header_text and '代號' not in header_text:
                continue
            for tr in trs[1:]:
                tds = tr.find_all('td')
                if len(tds) < 4:
                    continue
                stock_id = tds[1].get_text(strip=True)
                stock_name = tds[2].get_text(strip=True)
                period = tds[4].get_text(strip=True) if len(tds) > 4 else ''
                measure = tds[5].get_text(strip=True) if len(tds) > 5 else ''
                start_date, end_date = parse_period(period)
                match_freq = extract_match_frequency(measure)
                results.append({
                    'stock_id': stock_id,
                    'stock_name': stock_name,
                    'market': '上櫃',
                    'announce_date': '',
                    'condition': '',
                    'period': period,
                    'start_date': start_date,
                    'end_date': end_date,
                    'measure': measure,
                    'match_frequency': match_freq,
                })
            if results:
                print(f"[TPEx處置] HTML 抓到 {len(results)} 筆")
                return results

    except Exception as e:
        print(f"[TPEx處置] Web API 錯誤: {e}")

    print("[TPEx處置] 所有方案均無資料")
    return []


# ============================================================
# 注意股
# ============================================================
def fetch_twse_notice():
    """TWSE 注意交易資訊"""
    url = 'https://www.twse.com.tw/announcement/notice'
    params = {'response': 'json'}
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = resp.json()
        if data.get('stat') != 'OK' or not data.get('data'):
            print(f"[TWSE注意] 無資料: {data.get('stat')}")
            return []
        results = []
        for row in data['data']:
            stock_id = row[2].strip() if len(row) > 2 else ''
            stock_name = row[3].strip() if len(row) > 3 else ''
            announce_date = row[1].strip() if len(row) > 1 else ''
            results.append({
                'stock_id': stock_id,
                'stock_name': stock_name,
                'market': '上市',
                'announce_date': announce_date,
            })
        print(f"[TWSE注意] 抓到 {len(results)} 筆")
        return results
    except Exception as e:
        print(f"[TWSE注意] 錯誤: {e}")
        return []


def fetch_tpex_notice():
    """TPEx 上櫃注意股"""
    try:
        url = 'https://www.tpex.org.tw/openapi/v1/tpex_trading_warning_information'
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                results = []
                for row in data:
                    stock_id = ''
                    stock_name = ''
                    for k in ['SecuritiesCompanyCode', 'Code', '證券代號']:
                        if k in row and row[k]:
                            stock_id = str(row[k]).strip()
                            break
                    for k in ['CompanyName', 'Name', '證券名稱']:
                        if k in row and row[k]:
                            stock_name = str(row[k]).strip()
                            break
                    if not stock_id:
                        vals = list(row.values())
                        stock_id = str(vals[0]).strip() if vals else ''
                        stock_name = str(vals[1]).strip() if len(vals) > 1 else ''
                    results.append({
                        'stock_id': stock_id,
                        'stock_name': stock_name,
                        'market': '上櫃',
                        'announce_date': '',
                    })
                print(f"[TPEx注意] 抓到 {len(results)} 筆")
                return results
    except Exception as e:
        print(f"[TPEx注意] 錯誤: {e}")
    return []


# ============================================================
# 工具函數
# ============================================================
def parse_period(period_str):
    """解析處置期間字串"""
    match = re.search(r'(\d{2,3})/(\d{1,2})/(\d{1,2})\s*[～~至\-]\s*(\d{2,3})/(\d{1,2})/(\d{1,2})', period_str)
    if match:
        y1, m1, d1, y2, m2, d2 = match.groups()
        start = f"{int(y1)+1911}/{int(m1):02d}/{int(d1):02d}"
        end = f"{int(y2)+1911}/{int(m2):02d}/{int(d2):02d}"
        return start, end
    return '', ''


def extract_match_frequency(content):
    """提取撮合頻率"""
    match = re.search(r'每([\u4e00-\u9fff]+)分鐘撮合一次', content)
    if match:
        cn_num = match.group(1)
        num_map = {
            '五': '5分盤', '十': '10分盤', '二十': '20分盤',
            '四十五': '45分盤', '六十': '60分盤',
        }
        return num_map.get(cn_num, f'{cn_num}分盤')
    # 也嘗試阿拉伯數字
    match2 = re.search(r'(\d+)\s*分鐘', content)
    if match2:
        num = match2.group(1)
        return f'{num}分盤'
    return ''


def roc_to_date(date_str):
    """日期字串轉 datetime"""
    match = re.match(r'(\d{4})/(\d{1,2})/(\d{1,2})', date_str)
    if match:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    match = re.match(r'(\d{2,3})/(\d{1,2})/(\d{1,2})', date_str)
    if match:
        y = int(match.group(1))
        if y < 1911:
            y += 1911
        return datetime(y, int(match.group(2)), int(match.group(3)))
    return None


def check_watchlist_alerts(disposal_list, notice_list, watchlist):
    """比對觀察名單"""
    alerts = []
    disposal_ids = {d['stock_id'] for d in disposal_list}
    notice_ids = {n['stock_id'] for n in notice_list}

    for sid, sname in watchlist.items():
        status = []
        detail = None
        if sid in disposal_ids:
            detail = next((d for d in disposal_list if d['stock_id'] == sid), None)
            status.append('處置中')
        if sid in notice_ids:
            status.append('注意股')
        if status:
            alerts.append({
                'stock_id': sid,
                'stock_name': sname,
                'status': status,
                'disposal_detail': detail,
            })
    return alerts


def compute_active_disposals(disposal_list):
    """篩選仍在處置中的股票"""
    today = datetime.now()
    active = []
    upcoming_release = []

    # 按 stock_id 取最新一筆
    latest = {}
    for d in disposal_list:
        sid = d['stock_id']
        if sid not in latest or d.get('end_date', '') > latest[sid].get('end_date', ''):
            latest[sid] = d

    for sid, d in latest.items():
        end_dt = roc_to_date(d.get('end_date', ''))
        if not end_dt:
            active.append(d)
            continue

        days_left = (end_dt - today).days
        d['days_left'] = days_left
        d['end_date_str'] = end_dt.strftime('%m/%d')

        if days_left >= 0:
            active.append(d)
            if days_left <= 3:
                upcoming_release.append(d)

    active.sort(key=lambda x: x.get('days_left', 999))
    upcoming_release.sort(key=lambda x: x.get('days_left', 999))
    return active, upcoming_release


# ============================================================
# 主流程
# ============================================================
def main():
    print(f"=== 處置股資料抓取 {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")

    # 載入觀察名單
    watchlist = load_watchlist()

    # 抓取資料
    twse_disposal = fetch_twse_disposal()
    tpex_disposal = fetch_tpex_disposal()
    twse_notice = fetch_twse_notice()
    tpex_notice = fetch_tpex_notice()

    all_disposal = twse_disposal + tpex_disposal
    all_notice = twse_notice + tpex_notice

    # 篩選處置中
    active, upcoming_release = compute_active_disposals(all_disposal)

    # 比對觀察名單
    alerts = check_watchlist_alerts(all_disposal, all_notice, watchlist)

    # 輸出 JSON
    output = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'active_disposals': active,
        'upcoming_release': upcoming_release,
        'watchlist_alerts': alerts,
        'notice_stocks': all_notice[:30],
        'total_disposal_count': len(active),
        'attstock_url': 'https://attstock.tw/risk',
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"=== 完成！輸出: {OUTPUT_FILE} ===")
    print(f"  處置中: {len(active)} 檔")
    print(f"  即將出關: {len(upcoming_release)} 檔")
    print(f"  觀察名單警示: {len(alerts)} 檔")

    if alerts:
        print("\n⚠️ 觀察名單中的處置/注意股:")
        for a in alerts:
            print(f"  {a['stock_id']} {a['stock_name']}: {', '.join(a['status'])}")

    return output


if __name__ == '__main__':
    main()
