#!/usr/bin/env python3
"""
為處置股代號加上 Yahoo 股票連結
執行: cd ~/MyStock && python3 patch_yahoo_link.py
"""

with open('dashboard.html', 'r', encoding='utf-8') as f:
    h = f.read()

# 1. 替換 item-id (處置中 & 即將出關的股票代號)
old_item = "'<span class=\"item-id\">' + d.stock_id + '</span>'"
new_item = "'<a class=\"item-id\" href=\"https://tw.stock.yahoo.com/quote/' + d.stock_id + '\" target=\"_blank\" rel=\"noopener\">' + d.stock_id + '</a>'"

count1 = h.count(old_item)
h = h.replace(old_item, new_item)

# 2. 替換 chip-id (警示橫幅的股票代號)
old_chip = "'<span class=\"chip-id\">' + a.stock_id + '</span>'"
new_chip = "'<a class=\"chip-id\" href=\"https://tw.stock.yahoo.com/quote/' + a.stock_id + '\" target=\"_blank\" rel=\"noopener\">' + a.stock_id + '</a>'"

count2 = h.count(old_chip)
h = h.replace(old_chip, new_chip)

# 3. 加 CSS 讓連結樣式一致
css_add = """
/* 處置股 Yahoo 連結 */
.disposal-item a.item-id, .alert-chip a.chip-id {
    text-decoration: none;
    color: inherit;
    cursor: pointer;
    transition: opacity 0.15s;
}
.disposal-item a.item-id:hover, .alert-chip a.chip-id:hover {
    opacity: 0.7;
    text-decoration: underline;
}
"""

anchor = '/* ==================== 處置股監控區塊 ===================='
if anchor in h:
    h = h.replace(anchor, css_add + anchor)
    count3 = 1
else:
    count3 = 0
    print("⚠️ CSS 錨點未找到，請手動加入 CSS")

with open('dashboard.html', 'w', encoding='utf-8') as f:
    f.write(h)

print(f"✅ item-id 替換: {count1} 處")
print(f"✅ chip-id 替換: {count2} 處")
print(f"✅ CSS 插入: {count3} 處")
print("🎉 完成！股票代號點擊可開啟 Yahoo 股票頁面")
