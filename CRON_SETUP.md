# 台股監控系統 - 定時任務設定指南

## 📋 前提條件

你的 Mac 需要:
- 每天晚上 8:30 左右**保持開機**
- 不需要登入,休眠狀態也可以運行

---

## 🚀 方法 1: 使用 Mac 內建的 launchd (推薦)

### 步驟 1: 安裝到正確位置

```bash
# 1. 移動整個專案到你的家目錄
mv taiwan-stock-monitor-complete ~/

# 2. 進入目錄
cd ~/taiwan-stock-monitor-complete/backend

# 3. 給執行腳本權限
chmod +x run_daily.py

# 4. 建立 logs 目錄
mkdir -p logs
```

### 步驟 2: 安裝 launchd 任務

```bash
# 1. 複製 plist 檔案到 LaunchAgents
cp ~/taiwan-stock-monitor-complete/com.jay.stock-monitor.plist ~/Library/LaunchAgents/

# 2. 載入任務
launchctl load ~/Library/LaunchAgents/com.jay.stock-monitor.plist

# 3. 檢查是否成功
launchctl list | grep stock-monitor
```

### 步驟 3: 測試執行

```bash
# 手動觸發一次測試
launchctl start com.jay.stock-monitor

# 查看日誌
tail -f ~/taiwan-stock-monitor-complete/backend/logs/cron.log
```

### 管理指令

```bash
# 停止任務
launchctl stop com.jay.stock-monitor

# 卸載任務
launchctl unload ~/Library/LaunchAgents/com.jay.stock-monitor.plist

# 重新載入 (修改設定後)
launchctl unload ~/Library/LaunchAgents/com.jay.stock-monitor.plist
launchctl load ~/Library/LaunchAgents/com.jay.stock-monitor.plist
```

---

## 🌩️ 方法 2: 使用雲端服務器 (不需要電腦開機)

### 選項 A: Google Cloud (免費額度)

```bash
# 1. 在 Google Cloud 建立免費 VM
# 2. 上傳專案
# 3. 設定 cron
crontab -e
# 加入: 30 20 * * * cd ~/backend && python3 run_daily.py >> logs/cron.log 2>&1
```

### 選項 B: AWS EC2 (付費,約 $3-5/月)

### 選項 C: Heroku (付費,約 $7/月)

---

## 🔍 常見問題

### Q: 如何確認任務有在運行?

```bash
# 檢查日誌
cat ~/taiwan-stock-monitor-complete/backend/logs/cron.log

# 檢查資料庫最後更新時間
sqlite3 ~/taiwan-stock-monitor-complete/backend/market_data.db "SELECT date, timestamp FROM margin_data ORDER BY timestamp DESC LIMIT 1;"
```

### Q: Mac 休眠時會執行嗎?

**會!** launchd 會在 Mac 喚醒後自動執行錯過的任務。

### Q: 我可以修改執行時間嗎?

可以!編輯 `com.jay.stock-monitor.plist`:
```xml
<key>Hour</key>
<integer>21</integer>  <!-- 改成 21 就是晚上 9 點 -->
<key>Minute</key>
<integer>0</integer>   <!-- 改成 0 就是整點 -->
```

然後重新載入:
```bash
launchctl unload ~/Library/LaunchAgents/com.jay.stock-monitor.plist
launchctl load ~/Library/LaunchAgents/com.jay.stock-monitor.plist
```

### Q: 我想收到通知怎麼辦?

可以加 LINE Notify 或 Email 通知,需要改 `run_daily.py`。

---

## 📊 檢查數據

### 查看最新數據

```bash
cd ~/taiwan-stock-monitor-complete/backend
python3 -c "import json; print(json.dumps(json.load(open('data/market_data.json')), indent=2, ensure_ascii=False))"
```

### 查看網站

```bash
cd ~/taiwan-stock-monitor-complete/frontend
python3 -m http.server 8000
# 然後開啟瀏覽器: http://localhost:8000
```

---

## ⚠️ 重要提醒

1. **電腦需要開機**: Mac 必須在執行時間保持開機或休眠狀態
2. **網路連線**: 需要網路才能抓取數據
3. **定期檢查**: 建議每週檢查一次日誌,確保運作正常
4. **備份資料**: 定期備份 `market_data.db` 和 `market_data.json`

---

## 🎯 推薦方案

**如果你每天都會開 Mac** → 用方法 1 (launchd)
**如果 Mac 常常關機** → 考慮方法 2 (雲端服務器)
**如果有樹莓派或 NAS** → 可以部署在上面

需要我提供更詳細的設定說明嗎? 🚀
