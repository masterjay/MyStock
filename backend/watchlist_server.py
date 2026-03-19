#!/usr/bin/env python3
"""
Watchlist API Server
提供 /api/watchlist GET/POST 給 dashboard 使用
port: 5001
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from pathlib import Path

WATCHLIST_PATH = Path(__file__).parent / 'data' / 'watchlist.json'

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

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 5001), WatchlistHandler)
    print('Watchlist API server running on port 5001')
    server.serve_forever()
