# 微台指整合檢查清單 ✅

## 📦 檔案清單

解壓縮 `mxf_integration.zip` 後應該有這些檔案：

```
mxf_integration/
├── README_INTEGRATION.md          # 📖 完整整合指南
├── scraper_taifex_new.py          # 🆕 新版爬蟲（支援 MXF）
├── data_collector_v2.py           # 🔄 主收集器（雙資料源）
├── run_daily_v2.py               # ⏰ 定時腳本
├── retail_ratio_collector_v2.py  # 📊 歷史收集器
├── upgrade_database.py           # 🔧 資料庫升級（執行一次）
├── collect_mxf_history.py        # 📅 批量歷史收集
└── verify_scraper.py             # ✅ 驗證工具
```

---

## 🎯 整合步驟速查

### 1️⃣ 備份 (5 分鐘)
```bash
cd ~/MyStock/backend
cp data/market_data.db data/market_data.db.backup_$(date +%Y%m%d)
```

### 2️⃣ 複製檔案 (5 分鐘)
```bash
# 解壓縮到 backend 目錄
unzip mxf_integration.zip -d ~/MyStock/backend/

# 重命名檔案（覆蓋舊版）
cd ~/MyStock/backend
mv scraper_taifex_new.py scraper_taifex_v2.py
mv data_collector_v2.py data_collector.py.v2
mv run_daily_v2.py run_daily.py.v2
mv retail_ratio_collector_v2.py retail_ratio_collector.py.v2

# 備份舊檔案
mv scraper_taifex.py scraper_taifex.py.old
mv data_collector.py data_collector.py.old

# 使用新版
mv scraper_taifex_v2.py scraper_taifex.py
mv data_collector.py.v2 data_collector.py
```

### 3️⃣ 升級資料庫 (2 分鐘)
```bash
python upgrade_database.py
```

預期輸出：
```
✓ 已備份至: data/market_data.db.backup_20260213_xxxxx
✓ mxf_futures_data 表創建成功
✓ Schema 升級完成
```

### 4️⃣ 測試收集 (5 分鐘)
```bash
python data_collector.py
```

檢查輸出是否有：
```
[4/6] 抓取 MXF 微台指 (散戶指標)...
  ✓ 微台指散戶多空比: -22.17%
  ✓ 收盤價: 33,691
  ✓ 未平倉量: 69,324
```

### 5️⃣ 驗證數據 (2 分鐘)
```bash
python verify_scraper.py
```

應該看到：
```
✅ 所有驗證通過！爬蟲數據與官方一致
```

### 6️⃣ 收集歷史（可選，10 分鐘）
```bash
python collect_mxf_history.py
# 選擇 1: 過去 30 天
```

### 7️⃣ 檢查 JSON 輸出 (1 分鐘)
```bash
cat data/futures_data.json | python -m json.tool | head -30
```

---

## ⚠️ 常見問題速查

### ❌ 問題: `ModuleNotFoundError: No module named 'scraper_taifex_v2'`
**解決:** 檔案名稱錯誤
```bash
cd ~/MyStock/backend
mv scraper_taifex_new.py scraper_taifex_v2.py
```

### ❌ 問題: `Table mxf_futures_data doesn't exist`
**解決:** 忘記升級資料庫
```bash
python upgrade_database.py
```

### ❌ 問題: 驗證失敗，數據不一致
**可能原因:**
1. 期交所網站結構改變 → 等我更新解析邏輯
2. 查詢的日期沒有交易 → 換個日期試試
3. 網路連線問題 → 檢查網路

**除錯步驟:**
```bash
python -c "from scraper_taifex_v2 import TAIFEXScraper; s=TAIFEXScraper(); s.get_retail_ratio('2026/02/11', 'MXF', debug=True)"
```

### ❌ 問題: JSON 檔案沒有 MXF 資料
**解決:** 手動執行收集器
```bash
python retail_ratio_collector_v2.py
```

---

## 📊 資料驗證清單

執行完成後，請驗證以下項目：

- [ ] 資料庫有 `mxf_futures_data` 表
- [ ] 最近一個交易日有 MXF 數據
- [ ] `data/futures_data.json` 包含 `mxf` 欄位
- [ ] 散戶多空比數值合理（-30% ~ +30%）
- [ ] 未平倉量 > 50,000
- [ ] 收盤價在 30,000 ~ 40,000 範圍

驗證指令：
```bash
sqlite3 data/market_data.db "SELECT date, retail_ratio, total_oi FROM mxf_futures_data ORDER BY date DESC LIMIT 5;"
```

---

## 🚀 部署到生產

### 更新定時任務

如果使用 launchd (macOS):
```bash
# 編輯 plist
nano ~/Library/LaunchAgents/com.mystock.daily.plist

# 確認執行的是 run_daily.py (新版)
# 重新載入
launchctl unload ~/Library/LaunchAgents/com.mystock.daily.plist
launchctl load ~/Library/LaunchAgents/com.mystock.daily.plist
```

如果使用 cron (Linux):
```bash
crontab -e
# 30 20 * * * cd /path/to/backend && python run_daily.py >> logs/daily.log 2>&1
```

---

## 🎨 前端更新要點

1. **讀取新的 JSON 格式**
   ```javascript
   const data = await fetch('/data/futures_data.json').then(r => r.json());
   const mxfHistory = data.history.mxf;  // 微台指
   const txHistory = data.history.tx;     // 大台
   ```

2. **顯示微台指圖表**（類似第二張圖）
   - X 軸: 日期
   - Y 軸: 散戶多空比 (%)
   - 0 線為分界線
   - 正值 = 綠色柱（偏多）
   - 負值 = 紅色柱（偏空）

3. **背離提示**
   ```javascript
   if (mxf.retail_ratio > 15 && tx.retail_ratio < -5) {
     alert('⚠️ 散戶追高，法人保守，注意短線風險');
   }
   ```

---

## 📞 需要協助？

整合過程中遇到任何問題：

1. 先檢查本清單的「常見問題」
2. 執行 `verify_scraper.py` 確認爬蟲
3. 查看 `logs/` 目錄的錯誤訊息
4. 提供完整錯誤訊息讓我協助

---

## ✅ 完成確認

全部整合完成後，您應該能：

- ✅ 每日自動收集 MXF 微台指數據
- ✅ 在 `data/futures_data.json` 看到最新數據
- ✅ 資料庫有過去 30 天的歷史數據
- ✅ 驗證腳本通過所有檢查

**恭喜！您現在擁有 TX + MXF 雙期貨監控系統！** 🎉
