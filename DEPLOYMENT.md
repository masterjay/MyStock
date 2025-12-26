# 部署指南

## 🚀 本地開發部署

### 環境需求
- Python 3.8+
- 任何現代瀏覽器

### 快速啟動 (本地測試)

1. **安裝依賴**
```bash
cd backend
pip install -r requirements.txt
```

2. **執行數據收集**
```bash
python data_collector.py
```

3. **啟動前端**
```bash
# 方法1: 直接開啟 HTML
open frontend/index.html  # macOS
# 或
start frontend/index.html  # Windows

# 方法2: 用簡易 HTTP server
cd frontend
python -m http.server 8000
# 瀏覽器開啟 http://localhost:8000
```

## ☁️ 雲端部署方案

### 方案 A: GitHub Pages (前端) + PythonAnywhere (後端)

**優點**: 完全免費
**適合**: 個人使用

#### 1. 後端 (PythonAnywhere)

a. 註冊 [PythonAnywhere](https://www.pythonanywhere.com) 免費帳號

b. 上傳 backend 資料夾

c. 在 PythonAnywhere 終端機執行:
```bash
pip install requests schedule
cd backend
python data_collector.py
```

d. 設定定時任務 (Scheduled tasks):
- Command: `cd /home/你的帳號/backend && python data_collector.py`
- Time: 15:30 (每天)

e. 設定 Web app 提供 JSON 檔案:
```python
# 在 PythonAnywhere Web app 設定
from flask import Flask, send_file
app = Flask(__name__)

@app.route('/data/market_data.json')
def get_data():
    return send_file('data/market_data.json')
```

#### 2. 前端 (GitHub Pages)

a. 建立 GitHub repository

b. 上傳 frontend 資料夾

c. 修改 `index.html` 的數據來源:
```javascript
// 改成你的 PythonAnywhere URL
const response = await fetch('https://你的帳號.pythonanywhere.com/data/market_data.json');
```

d. 在 GitHub repo 設定中啟用 GitHub Pages

e. 訪問 `https://你的帳號.github.io/專案名稱`

---

### 方案 B: Vercel (全棧)

**優點**: 部署簡單、自動 HTTPS
**適合**: 需要分享給他人

#### 1. 建立 Vercel 專案

```bash
npm install -g vercel
cd frontend
vercel
```

#### 2. 設定 Serverless Function (後端)

在 `api/update.py`:
```python
from backend.data_collector import DataCollector

def handler(request):
    collector = DataCollector()
    data = collector.collect_daily_data()
    return {
        'statusCode': 200,
        'body': data
    }
```

#### 3. 設定 Cron Job

在 `vercel.json`:
```json
{
  "crons": [{
    "path": "/api/update",
    "schedule": "30 15 * * *"
  }]
}
```

---

### 方案 C: Railway (最簡單)

**優點**: 一鍵部署、包含後端
**適合**: 想要最快上線

#### 1. 連接 GitHub

a. 推送專案到 GitHub

b. 訪問 [Railway](https://railway.app)

c. 選擇 "Deploy from GitHub"

#### 2. 設定環境

Railway 會自動偵測 Python 專案

#### 3. 設定定時任務

使用 Railway 的 Cron Jobs 功能

---

## 🔒 安全建議

1. **不要暴露數據庫**: 只分享 JSON 檔案
2. **設定 CORS**: 限制前端來源
3. **Rate Limiting**: 避免被濫用
4. **API Key**: 如果需要認證

## 📊 監控與維護

### 檢查數據更新

```bash
# 查看最新數據時間
sqlite3 backend/market_data.db "SELECT date, timestamp FROM margin_data ORDER BY date DESC LIMIT 1"
```

### 查看執行日誌

```bash
# 如果有設定 logging
tail -f backend/logs/collector.log
```

### 備份數據

```bash
# 定期備份數據庫
cp backend/market_data.db backup/market_data_$(date +%Y%m%d).db
```

## 🐛 故障排除

### 問題: 數據收集失敗

**解決方案**:
1. 檢查是否為交易日
2. 確認網路連線
3. 查看官方網站是否正常

### 問題: 前端顯示舊數據

**解決方案**:
1. 清除瀏覽器快取
2. 檢查 JSON 檔案更新時間
3. 確認後端定時任務執行

### 問題: 圖表不顯示

**解決方案**:
1. 檢查瀏覽器 Console 錯誤
2. 確認 Recharts CDN 載入
3. 驗證 JSON 數據格式

## 📱 行動裝置優化

前端已使用 Tailwind 響應式設計，在手機上也能正常顯示。

如需 PWA (Progressive Web App):

1. 加入 `manifest.json`
2. 註冊 Service Worker
3. 加入離線快取

## 🔄 持續整合 (CI/CD)

### GitHub Actions 範例

`.github/workflows/update-data.yml`:
```yaml
name: Update Market Data
on:
  schedule:
    - cron: '30 7 * * *'  # UTC 15:30 = 台灣 23:30
jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
      - name: Install dependencies
        run: pip install -r backend/requirements.txt
      - name: Run collector
        run: python backend/data_collector.py
      - name: Commit data
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add data/market_data.json
          git commit -m "Update market data" || echo "No changes"
          git push
```

---

**選擇建議**:
- 🏠 **本地使用**: 方案 A
- 👥 **分享給朋友**: 方案 B 或 C  
- 🚀 **正式產品**: 方案 C + 自訂網域

有任何部署問題,歡迎詢問!
