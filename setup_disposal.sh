#!/bin/bash
# ============================================================
# 處置股功能部署指南
# 在 GCP server 上執行以下步驟
# ============================================================

# ----- Step 1: 上傳檔案 -----
# 將 disposal_stocks.py 放到 backend/
cp disposal_stocks.py ~/MyStock/backend/disposal_stocks.py

# ----- Step 2: 安裝依賴 (如尚未安裝) -----
pip install beautifulsoup4 --break-system-packages 2>/dev/null || pip3 install beautifulsoup4

# ----- Step 3: 建立 data 目錄 -----
mkdir -p ~/MyStock/data

# ----- Step 4: 測試執行 -----
cd ~/MyStock && python3 backend/disposal_stocks.py

# 確認輸出檔案
cat ~/MyStock/data/disposal_stocks.json | python3 -m json.tool | head -30

# ----- Step 5: 加入 dashboard.html -----
# 把 disposal_card.html 的三個部分 (HTML/CSS/JS) 分別插入 dashboard.html:
#   - HTML: 插入主內容區的適當位置
#   - CSS: 加入 <style> 區 或 css 檔
#   - JS: 加入 <script> 區 或 js 檔
#
# 如果你想用 heredoc 一鍵插入 (需要根據你實際的 dashboard.html 調整錨點):
# python3 -c "
# import re
# with open('dashboard.html','r') as f: html=f.read()
# # 在某個錨點後插入... 
# # 這部分需要你看 dashboard.html 的結構決定插入位置
# "

# ----- Step 6: 加入 run_daily.py -----
# 在 run_daily.py 的 steps 列表中加入:
#   {'name': '處置股資料', 'cmd': 'python3 backend/disposal_stocks.py'},
#
# 或者加獨立 cron (每日 18:30 執行，在收盤後、你的 19:00 大批次前):
# crontab -e
# 30 18 * * 1-5 cd ~/MyStock && python3 backend/disposal_stocks.py >> logs/disposal.log 2>&1

# ----- Step 7: nginx 確認 data/ 可被存取 -----
# 確認 nginx 設定中 dashboard 的 root 指向 ~/MyStock/
# 這樣前端就能 fetch('data/disposal_stocks.json')
# 如果 nginx root 不是 ~/MyStock，需要加 alias:
#   location /data/ {
#       alias /home/s0971417/MyStock/data/;
#   }

# ----- Step 8: 更新觀察名單 -----
# disposal_stocks.py 頂部的 MY_WATCHLIST 字典要保持更新
# 你可以改成從 Notion watchlist 同步的 JSON 檔讀取:
#   - 修改 MY_WATCHLIST 為讀取 data/notion_watchlist.json
#   - 這樣 notion_watchlist.py 更新後，處置股比對也會跟著更新

# ----- Step 9: commit -----
cd ~/MyStock
git add backend/disposal_stocks.py data/
git commit -m "feat: 處置股監控功能 - 後端抓取 + dashboard 卡片"
git push origin main

echo "✅ 部署完成！"
