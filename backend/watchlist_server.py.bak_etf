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

        if self.path != '/api/watchlist':
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

        if self.path != '/api/watchlist':
            self._set_headers(404)
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

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 5001), WatchlistHandler)
    print('Watchlist API server running on port 5001')
    server.serve_forever()
