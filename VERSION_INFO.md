# 台股監控系統 - 雙情緒指標版本 v1.0

## 📦 版本資訊

**版本**: v1.0 - 雙情緒指標系統
**日期**: 2025-12-27
**狀態**: ✅ 穩定版,已部署測試

---

## ✨ 功能清單

### 🎯 核心功能

1. **台股數據監控**
   - ✅ 融資使用率 (30天歷史)
   - ✅ 融資餘額
   - ✅ 期貨多空比
   - ✅ 外資淨部位
   - ✅ 歷史趨勢圖表

2. **雙市場情緒指標** (NEW!)
   - ✅ 🇹🇼 台股情緒指數 (0-100)
     - 融資使用率權重: 40%
     - 期貨多空比權重: 40%
     - 外資淨部位權重: 20%
   
   - ✅ 🇺🇸 美股恐慌貪婪指數 (CNN Fear & Greed)
     - 即時指數
     - 歷史對比 (前一日/週/月)

3. **自動化數據收集**
   - ✅ 每天 20:30 自動執行
   - ✅ 台股數據 (TWSE + TAIFEX)
   - ✅ 台股情緒計算
   - ✅ 美股情緒抓取

4. **視覺化介面**
   - ✅ 深色科技風格儀表板
   - ✅ 情緒指標圓環圖
   - ✅ 趨勢線圖
   - ✅ 響應式設計 (手機/平板/桌面)

---

## 📂 檔案結構

```
taiwan-stock-monitor-sentiment-v1/
├── dashboard.html                    # 主儀表板 (含雙情緒指標)
├── backend/
│   ├── scraper_twse.py              # 證交所爬蟲 (融資)
│   ├── scraper_taifex.py            # 期交所爬蟲 (期貨)
│   ├── scraper_us_sentiment.py      # CNN Fear & Greed 爬蟲
│   ├── sentiment_tw.py              # 台股情緒計算
│   ├── data_collector.py            # 主數據收集器
│   ├── run_daily.py                 # 每日執行腳本
│   └── requirements.txt             # Python 套件
├── deploy.sh                        # 部署腳本
└── README.md                        # 說明文件
```

---

## 🚀 部署步驟 (已在 VM 完成)

### 1. 上傳檔案
```bash
# 上傳 taiwan-stock-sentiment-v1.zip 到 VM
unzip taiwan-stock-sentiment-v1.zip
cd taiwan-stock-monitor-sentiment-v1
```

### 2. 安裝依賴
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 測試運行
```bash
python3 run_daily.py
```

### 4. 設定 Nginx
```bash
sudo nano /etc/nginx/sites-available/stock-monitor
```

配置:
```nginx
server {
    listen 80;
    server_name 34.169.83.2;
    
    root /home/s0971417/taiwan-stock-monitor-sentiment-v1;
    index dashboard.html;
    
    location /data/ {
        alias /home/s0971417/taiwan-stock-monitor-sentiment-v1/backend/data/;
    }
}
```

### 5. 設定 Cron
```bash
crontab -e
```

加入:
```
30 20 * * * cd /home/s0971417/taiwan-stock-monitor-sentiment-v1/backend && /home/s0971417/taiwan-stock-monitor-sentiment-v1/backend/venv/bin/python3 run_daily.py >> logs/cron.log 2>&1
```

---

## 📊 數據格式

### market_data.json
```json
{
  "latest": {
    "margin": {
      "date": "20251226",
      "ratio": 0.57,
      "balance": 3403.37
    },
    "futures": {
      "date": "20251226",
      "ratio": 0.98,
      "foreign_net": -23476
    }
  },
  "sentiment": {
    "taiwan": {
      "score": 51,
      "rating": "中性",
      "components": {
        "margin": {"score": 62, "weight": 0.4},
        "futures": {"score": 49, "weight": 0.4},
        "foreign": {"score": 31, "weight": 0.2}
      }
    },
    "us": {
      "score": 55.51,
      "rating": "greed",
      "previous_close": 57.74,
      "previous_week": 49.69,
      "previous_month": 17.66,
      "timestamp": "2025-12-26T23:59:48+00:00"
    }
  },
  "history": {
    "margin": [...],
    "futures": [...]
  },
  "updated_at": "2025-12-27T12:56:01.985760"
}
```

---

## 🔧 技術細節

### 後端
- Python 3.x
- BeautifulSoup4 (HTML 解析)
- Requests (HTTP 請求)
- SQLite (數據存儲)

### 前端
- 純 HTML/CSS/JavaScript
- Chart.js (圖表)
- SVG (圓環圖)
- 響應式設計

### 部署
- Google Cloud VM (e2-micro, 免費)
- Ubuntu 22.04 LTS
- Nginx
- Cron

---

## 📈 情緒指標解讀

### 台股情緒指數 (0-100)
- **0-24**: 極度恐慌 (紅色)
- **25-44**: 恐慌 (橙色)
- **45-55**: 中性 (黃色)
- **56-75**: 貪婪 (淺綠)
- **76-100**: 極度貪婪 (綠色)

### 美股恐慌貪婪指數
- **Extreme Fear**: 極度恐慌
- **Fear**: 恐慌
- **Neutral**: 中性
- **Greed**: 貪婪
- **Extreme Greed**: 極度貪婪

---

## 🐛 已知問題

無

---

## 📝 下一步規劃

### v2.0 功能
- [ ] 散戶多空比 (逆向指標)
- [ ] 三大法人買賣超
- [ ] 選擇權 Put/Call Ratio
- [ ] 前五/十大交易人
- [ ] LINE 通知功能

---

## 📞 聯絡資訊

**網站**: http://34.169.83.2
**更新時間**: 每天 20:30 (台灣時間)

---

## 🎉 版本歷史

### v1.0 (2025-12-27)
- ✅ 初始版本
- ✅ 台股數據監控
- ✅ 雙情緒指標系統
- ✅ 自動化數據收集
- ✅ 視覺化儀表板

---

**Last Updated**: 2025-12-27
**Status**: Production Ready ✅
