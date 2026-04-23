#!/usr/bin/env python3
"""
Watchlist API Server
提供 /api/watchlist GET/POST 給 dashboard 使用
port: 5001
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
import urllib.request
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env')

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
CHAIN_INDEX_DB_ID = "68c1ed96abac4e05a708d4169cee93d1"  # 📡 產業鏈索引
WATCHLIST_PATH = Path(__file__).parent / 'data' / 'watchlist.json'

def _notion_text(prop):
    t = prop.get("type", "")
    if t == "title":
        return "".join(x["plain_text"] for x in prop.get("title", []))
    if t == "rich_text":
        return "".join(x["plain_text"] for x in prop.get("rich_text", []))
    return ""

class WatchlistHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # 關閉 access log

    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers()

    def do_GET(self):
        if self.path.startswith('/api/chains'):
            self._handle_chains()
            return

        if self.path == "/etf/" or self.path == "/etf":
            self._serve_etf_index()
            return
        if self.path == "/etf/signals":
            self._serve_etf_signals_page()
            return
        if self.path.startswith("/etf/") and not self.path.startswith("/etf/api"):
            self._serve_etf_page()
            return
        if self.path.startswith("/api/etf/") and self.path.endswith("/holdings"):
            etf_code = self.path.split("/")[3].upper()
            self._handle_etf_holdings(etf_code)
            return
        if self.path.startswith("/api/etf/") and self.path.endswith("/changes"):
            etf_code = self.path.split("/")[3].upper()
            self._handle_etf_changes(etf_code)
            return
        if self.path == "/api/etf/daily_signals" or self.path.startswith("/api/etf/daily_signals?"):
            self._handle_etf_daily_signals()
            return
        if self.path != "/api/watchlist":
            self._set_headers(404)
            return
        try:
            if WATCHLIST_PATH.exists():
                data = json.loads(WATCHLIST_PATH.read_text(encoding='utf-8'))
            else:
                data = []
            self._set_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def do_POST(self):
        if self.path == '/api/scan':
            try:
                import subprocess
                subprocess.Popen(
                    ['python3', str(Path(__file__).parent / 'macd_signal_scanner.py')],
                    cwd=str(Path(__file__).parent)
                )
                self._set_headers()
                self.wfile.write(json.dumps({'ok': True, 'msg': '掃描已啟動'}).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
            return

        if self.path.startswith('/api/chains'):
            self._handle_chains()
            return

        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body)
            WATCHLIST_PATH.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            self._set_headers()
            self.wfile.write(json.dumps({'ok': True}).encode())
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({'error': str(e)}).encode())


    def _handle_chains(self):
        url = f"https://api.notion.com/v1/databases/{CHAIN_INDEX_DB_ID}/query"
        payload = json.dumps({
            "filter": {"property": "啟用", "checkbox": {"equals": True}},
            "sorts": [{"property": "排序", "direction": "ascending"}],
        }).encode('utf-8')
        req = urllib.request.Request(url, data=payload, method='POST')
        req.add_header("Authorization", f"Bearer {NOTION_TOKEN}")
        req.add_header("Notion-Version", "2022-06-28")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            self._set_headers(502)
            self.wfile.write(json.dumps({'error': str(e)}).encode())
            return
        chains = []
        for page in data.get("results", []):
            props = page["properties"]
            chains.append({
                "name": _notion_text(props.get("產業鏈名稱", {})),
                "icon": _notion_text(props.get("圖示", {})),
                "url": props.get("Notion連結", {}).get("url", ""),
                "order": props.get("排序", {}).get("number", 99),
            })
        self._set_headers(200)
        self.wfile.write(json.dumps(chains, ensure_ascii=False).encode('utf-8'))


    def _serve_etf_index(self):
        template_path = Path(__file__).parent.parent / 'templates' / 'etf_index.html'
        try:
            html = template_path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html)
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def _serve_etf_page(self):
        template_path = Path(__file__).parent.parent / 'templates' / 'etf_holdings.html'
        try:
            html = template_path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html)
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def _handle_etf_holdings(self, etf_code='00981A'):
        import sqlite3
        db_path = Path(__file__).parent.parent / 'data' / 'market_data.db'
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT data_date FROM etf_holdings_history WHERE etf_code=? ORDER BY data_date DESC LIMIT 1", (etf_code,)).fetchone()
            if not row:
                self._set_headers()
                self.wfile.write(json.dumps({'holdings': [], 'data_date': None}, ensure_ascii=False).encode())
                return
            latest_date = row['data_date']
            holdings = conn.execute("SELECT stock_code, stock_name, ratio, shares FROM etf_holdings_history WHERE etf_code=? AND data_date=? ORDER BY ratio DESC", (etf_code, latest_date)).fetchall()
            conn.close()
            self._set_headers()
            self.wfile.write(json.dumps({'data_date': latest_date, 'holdings': [dict(h) for h in holdings]}, ensure_ascii=False).encode())
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def _handle_etf_changes(self, etf_code='00981A'):
        import sqlite3
        db_path = Path(__file__).parent.parent / 'data' / 'market_data.db'
        try:
            conn = sqlite3.connect(str(db_path))
            dates = [r[0] for r in conn.execute("SELECT DISTINCT data_date FROM etf_holdings_history WHERE etf_code=? ORDER BY data_date DESC LIMIT 2", (etf_code,))]
            if len(dates) < 2:
                self._set_headers()
                self.wfile.write(json.dumps({'changes': [], 'date_new': None, 'date_old': None}, ensure_ascii=False).encode())
                return
            d_new, d_old = dates[0], dates[1]
            conn.row_factory = sqlite3.Row
            changes = conn.execute("SELECT n.stock_code, n.stock_name, n.ratio AS ratio_new, o.ratio AS ratio_old, n.shares AS shares_new, o.shares AS shares_old, (n.shares - COALESCE(o.shares,0)) AS shares_delta FROM (SELECT * FROM etf_holdings_history WHERE etf_code=? AND data_date=?) n LEFT JOIN (SELECT * FROM etf_holdings_history WHERE etf_code=? AND data_date=?) o ON n.stock_code=o.stock_code WHERE shares_delta!=0 ORDER BY ABS(shares_delta) DESC", (etf_code, d_new, etf_code, d_old)).fetchall()
            conn.close()
            self._set_headers()
            self.wfile.write(json.dumps({'date_new': d_new, 'date_old': d_old, 'changes': [dict(c) for c in changes]}, ensure_ascii=False).encode())
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def _handle_etf_daily_signals(self):
        """ETF 共識訊號 API：新建倉、強共識加碼、共識減碼"""
        import sqlite3
        ACTIVE_ETFS = ('00980A', '00981A', '00991A', '00992A')
        CONSENSUS_THRESHOLD = 3
        db_path = Path(__file__).parent.parent / 'data' / 'market_data.db'
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            placeholders = ','.join('?' * len(ACTIVE_ETFS))

            common_dates = conn.execute(
                f"""
                SELECT data_date, COUNT(DISTINCT etf_code) AS c
                FROM etf_holdings_history
                WHERE etf_code IN ({placeholders})
                GROUP BY data_date
                HAVING c >= 3
                ORDER BY data_date DESC LIMIT 2
                """,
                ACTIVE_ETFS
            ).fetchall()

            if len(common_dates) < 2:
                conn.close()
                self._send_json({
                    "error": "資料不足，至少需要兩個共同日期",
                    "signals": {"new_positions": [], "consensus_buy": [], "consensus_sell": [],
                                "summary": {"new_positions_count": 0, "consensus_buy_count": 0, "consensus_sell_count": 0}}
                })
                return

            d_new = common_dates[0]['data_date']
            d_old = common_dates[1]['data_date']

            new_positions_rows = conn.execute(
                f"""
                SELECT n.etf_code, n.stock_code, n.stock_name,
                       n.shares AS shares_new, n.ratio AS ratio_new
                FROM etf_holdings_history n
                LEFT JOIN etf_holdings_history o
                  ON n.etf_code = o.etf_code
                 AND n.stock_code = o.stock_code
                 AND o.data_date = ?
                WHERE n.data_date = ?
                  AND n.etf_code IN ({placeholders})
                  AND o.shares IS NULL
                  AND n.shares > 0
                ORDER BY n.ratio DESC
                """,
                (d_old, d_new, *ACTIVE_ETFS)
            ).fetchall()

            changes_rows = conn.execute(
                f"""
                SELECT n.etf_code, n.stock_code, n.stock_name,
                       n.shares AS shares_new, COALESCE(o.shares, 0) AS shares_old,
                       (n.shares - COALESCE(o.shares, 0)) AS delta,
                       n.ratio AS ratio_new
                FROM etf_holdings_history n
                LEFT JOIN etf_holdings_history o
                  ON n.etf_code = o.etf_code
                 AND n.stock_code = o.stock_code
                 AND o.data_date = ?
                WHERE n.data_date = ?
                  AND n.etf_code IN ({placeholders})
                  AND (n.shares - COALESCE(o.shares, 0)) != 0
                """,
                (d_old, d_new, *ACTIVE_ETFS)
            ).fetchall()

            stock_groups = {}
            for r in changes_rows:
                code = r['stock_code']
                if code not in stock_groups:
                    stock_groups[code] = {
                        'stock_name': r['stock_name'],
                        'buy_etfs': [],
                        'sell_etfs': [],
                    }
                entry = {
                    'etf': r['etf_code'],
                    'delta': r['delta'],
                    'shares_old': r['shares_old'],
                    'shares_new': r['shares_new'],
                    'ratio_new': r['ratio_new'],
                }
                if r['delta'] > 0:
                    stock_groups[code]['buy_etfs'].append(entry)
                else:
                    stock_groups[code]['sell_etfs'].append(entry)

            consensus_buy = []
            consensus_sell = []
            for code, g in stock_groups.items():
                if len(g['buy_etfs']) >= CONSENSUS_THRESHOLD:
                    consensus_buy.append({
                        'stock_code': code,
                        'stock_name': g['stock_name'],
                        'etf_count': len(g['buy_etfs']),
                        'total_delta': sum(e['delta'] for e in g['buy_etfs']),
                        'etfs': sorted([e['etf'] for e in g['buy_etfs']]),
                        'details': g['buy_etfs'],
                    })
                if len(g['sell_etfs']) >= CONSENSUS_THRESHOLD:
                    consensus_sell.append({
                        'stock_code': code,
                        'stock_name': g['stock_name'],
                        'etf_count': len(g['sell_etfs']),
                        'total_delta': sum(e['delta'] for e in g['sell_etfs']),
                        'etfs': sorted([e['etf'] for e in g['sell_etfs']]),
                        'details': g['sell_etfs'],
                    })

            consensus_buy.sort(key=lambda x: (-x['etf_count'], -x['total_delta']))
            consensus_sell.sort(key=lambda x: (-x['etf_count'], x['total_delta']))

            new_pos_list = [{
                'stock_code': r['stock_code'],
                'stock_name': r['stock_name'],
                'etf': r['etf_code'],
                'shares_new': r['shares_new'],
                'ratio_new': r['ratio_new'],
            } for r in new_positions_rows]

            conn.close()
            self._send_json({
                'date_new': d_new,
                'date_old': d_old,
                'active_etfs': list(ACTIVE_ETFS),
                'signals': {
                    'new_positions': new_pos_list,
                    'consensus_buy': consensus_buy,
                    'consensus_sell': consensus_sell,
                    'summary': {
                        'new_positions_count': len(new_pos_list),
                        'consensus_buy_count': len(consensus_buy),
                        'consensus_sell_count': len(consensus_sell),
                    },
                },
            })
        except Exception as e:
            import traceback
            self._send_json({'error': str(e), 'trace': traceback.format_exc()}, status=500)

    def _serve_etf_signals_page(self):
        """提供 ETF 共識訊號儀表板頁面"""
        template_path = Path(__file__).parent.parent / 'templates' / 'etf_signals.html'
        if template_path.exists():
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(template_path.read_bytes())
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write('<h1>etf_signals.html 尚未建立</h1>'.encode('utf-8'))

    def _send_json(self, data, status=200):
        """統一 JSON 回傳"""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))


if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 5001), WatchlistHandler)
    print('Watchlist API server running on port 5001')
    server.serve_forever()

# ── 暫存補丁（貼在檔案尾端，Python 不會執行到 if __name__ 裡面的內容）
# 這段不會被執行，真正的方法需要縮排插入
