#!/usr/bin/env python3
"""
修正處置股代號 Yahoo 連結
"""

with open('dashboard.html', 'r', encoding='utf-8') as f:
    h = f.read()

# 實際的字串格式 (行 7150, 7163)
old = """<span class="item-id">' + d.stock_id + '</span>"""
new = """<a class="item-id" href="https://tw.stock.yahoo.com/quote/' + d.stock_id + '" target="_blank" rel="noopener">' + d.stock_id + '</a>"""

count = h.count(old)
h = h.replace(old, new)

with open('dashboard.html', 'w', encoding='utf-8') as f:
    f.write(h)

print(f"✅ 替換 {count} 處")
