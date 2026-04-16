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

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 5001), WatchlistHandler)
    print('Watchlist API server running on port 5001')
    server.serve_forever()

# ── 暫存補丁（貼在檔案尾端，Python 不會執行到 if __name__ 裡面的內容）
# 這段不會被執行，真正的方法需要縮排插入
