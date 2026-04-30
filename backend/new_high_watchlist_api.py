#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新高觀察清單 API Server
專門服務「新高雷達」的 ⭐ 收藏功能
與舊有 watchlist.json (MACD) 完全獨立

啟動: python3 new_high_watchlist_api.py
背景: nohup python3 new_high_watchlist_api.py > new_high_watchlist_api.log 2>&1 &
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from datetime import datetime
from threading import Lock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# ⚠️ 重要：與舊 watchlist.json (MACD) 區隔開來
NHWL_PATH = os.path.join(DATA_DIR, 'new_high_watchlist.json')

os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app)

_write_lock = Lock()


def load_watchlist():
    """讀取新高觀察清單"""
    if not os.path.exists(NHWL_PATH):
        return {
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'stocks': [],
        }
    try:
        with open(NHWL_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 兼容性檢查：確保是新格式
            if isinstance(data, list):
                # 萬一有人不小心放成 list，自動包成 dict
                return {'updated_at': '', 'stocks': data}
            return data
    except (json.JSONDecodeError, IOError):
        return {'updated_at': '', 'stocks': []}


def save_watchlist(data):
    """寫入新高觀察清單（原子操作）"""
    with _write_lock:
        data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        tmp_path = NHWL_PATH + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, NHWL_PATH)


# ─────────────────────────────────────────
# API endpoints (路徑包含 new_high_watchlist 避免混淆)
# ─────────────────────────────────────────

@app.route('/api/new_high_watchlist', methods=['GET'])
def get_watchlist():
    """取得新高觀察清單"""
    return jsonify(load_watchlist())


@app.route('/api/new_high_watchlist/add', methods=['POST'])
def add_to_watchlist():
    """加入新高觀察清單
    Body: {"code":"2330","name":"台積電","price":1080,"trigger":"240日新高+爆量"}
    """
    body = request.get_json()
    if not body or not body.get('code'):
        return jsonify({'error': 'missing code'}), 400
    
    code = str(body['code']).strip()
    data = load_watchlist()
    
    for s in data['stocks']:
        if s['code'] == code:
            return jsonify({'error': 'already exists', 'stock': s}), 409
    
    new_stock = {
        'code':       code,
        'name':       body.get('name', ''),
        'added_date': datetime.now().strftime('%Y-%m-%d'),
        'added_price': float(body.get('price', 0)) if body.get('price') else 0,
        'trigger':    body.get('trigger', ''),
        # 由 update_new_high_watchlist_status.py 每日更新
        'current_price':    None,
        'pct_change':       None,
        'still_new_high':   None,
        'highest_after':    None,
        'lowest_after':     None,
        'pullback_from_peak': None,
        'last_updated':     None,
    }
    
    data['stocks'].append(new_stock)
    save_watchlist(data)
    return jsonify({'ok': True, 'stock': new_stock})


@app.route('/api/new_high_watchlist/remove', methods=['POST', 'DELETE'])
def remove_from_watchlist():
    """從新高觀察清單移除
    Body: {"code":"2330"}
    """
    body = request.get_json()
    if not body or not body.get('code'):
        return jsonify({'error': 'missing code'}), 400
    
    code = str(body['code']).strip()
    data = load_watchlist()
    
    before = len(data['stocks'])
    data['stocks'] = [s for s in data['stocks'] if s['code'] != code]
    after = len(data['stocks'])
    
    if before == after:
        return jsonify({'error': 'not found'}), 404
    
    save_watchlist(data)
    return jsonify({'ok': True, 'removed': code})


@app.route('/api/new_high_watchlist/clear', methods=['POST'])
def clear_watchlist():
    """清空新高觀察清單（謹慎使用）"""
    save_watchlist({'updated_at': '', 'stocks': []})
    return jsonify({'ok': True})


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'ok': True,
        'service': 'new_high_watchlist_api',
        'count': len(load_watchlist().get('stocks', [])),
        'data_file': NHWL_PATH,
    })


if __name__ == '__main__':
    # ⚠️ Port 5002（避開舊 watchlist_server.py 佔用的 5001）
    app.run(host='0.0.0.0', port=5002, debug=False)
