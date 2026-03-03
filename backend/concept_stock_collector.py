#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
概念股收集器 (Concept Stock Collector) v2
==========================================
從公開網站爬取概念股分類，建立 stock_id -> [概念標籤] 的對照表。

資料來源:
  1. Yahoo 股市概念股分類 (有分類頁的題材)
  2. 內建成分股清單 (Yahoo 沒有分類頁的題材, 如 CoWoS / CPO)
  3. 本地 JSON 手動補充 (覆蓋/微調)

輸出: data/concept_stocks.json
"""

import json
import os
import re
import time
import requests
from datetime import datetime
from pathlib import Path

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    print("⚠ beautifulsoup4 未安裝，Yahoo 爬蟲功能無法使用")

DATA_DIR = Path(__file__).parent / 'data'
OUTPUT_FILE = DATA_DIR / 'concept_stocks.json'
MANUAL_FILE = DATA_DIR / 'concept_stocks_manual.json'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
}

# yahoo_category: Yahoo 股市 class-quote 的 category 參數 (需完全匹配)
# builtin_stocks: 內建成分股 (Yahoo 沒有分類頁時使用)
CONCEPT_DEFINITIONS = {
    'low_orbit_satellite': {
        'label': '低軌衛星',
        'color': '#3B82F6',
        'yahoo_category': '衛星/低軌衛星',
        'builtin_stocks': [],
    },
    'ai_robot': {
        'label': 'AI / 機器人',
        'color': '#8B5CF6',
        'yahoo_category': 'AI人工智慧',
        'builtin_stocks': [],
    },
    'cowos': {
        'label': 'CoWoS / 先進封裝',
        'color': '#F59E0B',
        'yahoo_category': '',
        'builtin_stocks': [
            '2330', '3711', '2449', '3037', '2316', '3374', '1560', '3680',
            '6187', '3583', '3131', '6640', '6223', '6515', '2467', '6510',
            '8027', '2404', '6691', '6196', '6207', '2303', '2464', '5443',
        ],
    },
    'cpo': {
        'label': 'CPO 矽光子',
        'color': '#10B981',
        'yahoo_category': '',
        'builtin_stocks': [
            '3363', '3163', '4979', '3081', '3450', '2393', '3714', '6285',
            '4966', '2379', '3037', '5347', '2330', '3711', '2345',
        ],
    },
}


def fetch_yahoo_concept(category_label):
    if not HAS_BS4:
        return []
    stocks = []
    try:
        url = 'https://tw.stock.yahoo.com/class-quote'
        params = {'category': category_label, 'categoryLabel': '概念股'}
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            resp.text
        )
        if match:
            next_data = json.loads(match.group(1))
            stocks = _extract_stocks(next_data)
            if stocks:
                return _dedupe(stocks)

        soup = BeautifulSoup(resp.text, 'html.parser')
        for link in soup.find_all('a', href=True):
            m = re.search(r'/quote/(\d{4,6})(?:\.TW)?', link.get('href', ''))
            if m and len(m.group(1)) == 4:
                stocks.append({'stock_id': m.group(1), 'name': link.get_text(strip=True)})
        return _dedupe(stocks)
    except Exception as e:
        print(f"  ⚠ Yahoo爬取失敗 ({category_label}): {e}")
        return []


def _extract_stocks(data):
    stocks = []
    if isinstance(data, dict):
        if 'symbolId' in data or 'symbol' in data:
            sid = data.get('symbolId', data.get('symbol', ''))
            name = data.get('symbolName', data.get('shortName', ''))
            sid = sid.replace('.TW', '').replace('.TWO', '')
            if sid and re.match(r'^\d{4,6}$', sid):
                stocks.append({'stock_id': sid, 'name': name})
        for v in data.values():
            stocks.extend(_extract_stocks(v))
    elif isinstance(data, list):
        for item in data:
            stocks.extend(_extract_stocks(item))
    return stocks


def _dedupe(stocks):
    seen = set()
    unique = []
    for s in stocks:
        if s['stock_id'] not in seen:
            seen.add(s['stock_id'])
            unique.append(s)
    return unique


def load_manual_overrides():
    if not MANUAL_FILE.exists():
        sample = {"_comment": "手動維護概念股: add=加入, remove=排除"}
        for cid in CONCEPT_DEFINITIONS:
            sample[cid] = {"add": [], "remove": []}
        with open(MANUAL_FILE, 'w', encoding='utf-8') as f:
            json.dump(sample, f, ensure_ascii=False, indent=2)
        print(f"  → 已建立手動對照表: {MANUAL_FILE}")
        return {}
    with open(MANUAL_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def collect_concept_stocks():
    print("=" * 50)
    print("概念股收集器 v2")
    print("=" * 50)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    manual = load_manual_overrides()

    previous = {}
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                previous = json.load(f).get('concepts', {})
        except:
            pass

    concepts = {}
    stock_concepts = {}

    for concept_id, config in CONCEPT_DEFINITIONS.items():
        print(f"\n[{config['label']}]")
        stock_ids = set()
        source = ''

        # 1. Yahoo 爬蟲
        yahoo_cat = config.get('yahoo_category', '')
        if yahoo_cat:
            print(f"  嘗試 Yahoo ({yahoo_cat})...")
            yahoo_stocks = fetch_yahoo_concept(yahoo_cat)
            if yahoo_stocks:
                for s in yahoo_stocks:
                    stock_ids.add(s['stock_id'])
                print(f"  ✓ Yahoo: {len(yahoo_stocks)} 檔")
                source = 'yahoo'
            else:
                print(f"  ✗ Yahoo 無資料")
            time.sleep(1.5)

        # 2. 內建清單
        if not stock_ids and config.get('builtin_stocks'):
            stock_ids = set(config['builtin_stocks'])
            print(f"  ✓ 內建清單: {len(stock_ids)} 檔")
            source = 'builtin'

        # 3. 上次資料
        if not stock_ids and concept_id in previous:
            prev = previous[concept_id].get('stocks', [])
            if prev:
                stock_ids = set(prev)
                print(f"  ℹ 使用上次資料: {len(stock_ids)} 檔")
                source = 'cache'

        # 4. 手動覆蓋
        mc = manual.get(concept_id, {})
        if isinstance(mc, dict):
            adds = mc.get('add', [])
            removes = mc.get('remove', [])
            if adds:
                stock_ids.update(adds)
                print(f"  + 手動加入: {len(adds)} 檔")
            if removes:
                stock_ids -= set(removes)
                print(f"  - 手動排除: {len(removes)} 檔")

        sorted_ids = sorted(stock_ids)
        concepts[concept_id] = {
            'label': config['label'],
            'color': config['color'],
            'count': len(sorted_ids),
            'source': source,
            'stocks': sorted_ids,
        }
        for sid in sorted_ids:
            if sid not in stock_concepts:
                stock_concepts[sid] = []
            stock_concepts[sid].append(concept_id)
        print(f"  → 最終: {len(sorted_ids)} 檔 ({source})")

    output = {
        'updated_at': datetime.now().isoformat(),
        'concept_count': len(concepts),
        'total_stocks': len(stock_concepts),
        'concepts': concepts,
        'stock_concepts': stock_concepts,
    }
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 50}")
    print(f"✓ 已輸出: {OUTPUT_FILE}")
    for cid, cd in concepts.items():
        print(f"  • {cd['label']}: {cd['count']} 檔 ({cd['source']})")
    return output


def enrich_signals_with_concepts(signals):
    """為 MACD 訊號股加上概念標籤"""
    if not OUTPUT_FILE.exists():
        return signals
    try:
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        sc = data.get('stock_concepts', {})
        cm = data.get('concepts', {})
        for signal in signals:
            sid = signal.get('code', signal.get('stock_id', ''))
            cids = sc.get(sid, [])
            signal['concepts'] = [
                {'id': c, 'label': cm.get(c, {}).get('label', c), 'color': cm.get(c, {}).get('color', '#6B7280')}
                for c in cids
            ]
        return signals
    except Exception as e:
        print(f"  ⚠ 概念股標籤失敗: {e}")
        return signals


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--enrich-test':
        macd_file = DATA_DIR / 'macd_signal_stocks.json'
        if macd_file.exists():
            with open(macd_file, 'r', encoding='utf-8') as f:
                md = json.load(f)
            signals = enrich_signals_with_concepts(md.get('signals', []))
            tagged = [s for s in signals if s.get('concepts')]
            print(f"\n有概念標籤: {len(tagged)}/{len(md.get('signals', []))}")
            for s in tagged[:10]:
                print(f"  {s['stock_id']} {s.get('name','')} → {', '.join(c['label'] for c in s['concepts'])}")
        else:
            print("尚無 MACD 訊號資料")
    else:
        collect_concept_stocks()
