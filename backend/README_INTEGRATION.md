# 微台指 (MXF) 整合指南 v2.0

## 📋 整合概覽

本次更新將您的系統升級為支援 **TX (大台) + MXF (微台)** 雙期貨資料源：

- **TX 台指期貨** → 反映法人/機構態度（原有）
- **MXF 微型台指** → 反映散戶情緒（新增）⭐

兩者交叉比對可以：
1. 驗證趨勢強度
2. 發現背離訊號（反轉前兆）
3. 更準確判斷進出場時機

---

## 🚀 整合步驟

### Step 1: 備份現有資料

```bash
cd ~/MyStock/backend
cp data/market_data.db data/market_data.db.backup_$(date +%Y%m%d)
```

### Step 2: 更新檔案

複製以下檔案到您的 backend 目錄：

```bash
# 核心檔案
scraper_taifex_v2.py        → scraper_taifex.py (覆蓋舊版)
data_collector_v2.py        → data_collector.py (覆蓋舊版)
run_daily_v2.py            → run_daily.py (覆蓋舊版)
retail_ratio_collector_v2.py → retail_ratio_collector.py (覆蓋)

# 新增檔案
upgrade_database.py        → 執行一次即可
```

### Step 3: 升級資料庫

```bash
python upgrade_database.py
```

這會：
- 自動備份現有資料庫
- 新增 `mxf_futures_data` 表格
- 保留所有舊資料

### Step 4: 測試收集資料

```bash
python data_collector.py
```

預期輸出：
```
[1/6] 抓取融資餘額... ✓
[2/6] 抓取市值資料... ✓
[3/6] 抓取 TX 台指期 (大台)... ✓
[4/6] 抓取 MXF 微台指 (散戶指標)... ✓
  ✓ 微台指散戶多空比: -22.17%
  ✓ 收盤價: 33,691
  ✓ 未平倉量: 69,324
[5/6] 抓取選擇權 PCR... ✓
[6/6] 收集其他市場數據... ✓
```

### Step 5: 驗證數據正確性

```bash
python verify_scraper.py
```

這會比對期交所官方數據，確保爬蟲邏輯正確。

### Step 6: 收集歷史數據（可選）

如果您想要過去 30 天的微台指數據：

```bash
python collect_mxf_history.py
```

### Step 7: 檢查 JSON 輸出

```bash
cat data/futures_data.json
```

新的 JSON 格式：
```json
{
  "latest": {
    "mxf_futures": {
      "date": "20260211",
      "close_price": 33691,
      "retail_ratio": -22.17,
      "retail_long": 29462,
      "retail_short": 39862,
      "foreign_net": -5234
    },
    "tx_futures": { ... },
    "margin": { ... }
  },
  "history": {
    "mxf": [ ... ],
    "tx": [ ... ]
  }
}
```

---

## 📊 資料庫結構

### 新增的 `mxf_futures_data` 表

| 欄位 | 類型 | 說明 |
|------|------|------|
| date | TEXT | 日期 (YYYYMMDD) |
| commodity_id | TEXT | 商品代碼 (MXF) |
| close_price | REAL | 收盤價 |
| total_oi | INTEGER | 全市場未平倉量 |
| dealers_long/short | INTEGER | 自營商多/空單 |
| trusts_long/short | INTEGER | 投信多/空單 |
| foreign_long/short | INTEGER | 外資多/空單 |
| retail_long/short | INTEGER | 散戶多/空單 |
| retail_ratio | REAL | **散戶多空比 (%)** ⭐ |

### 原有的 `futures_data` 表（保留）

TX 大台數據保留在此表，確保向下相容。

---

## 🔄 定時任務更新

如果您使用 launchd（macOS）：

```bash
# 編輯您的 plist 檔案
nano ~/Library/LaunchAgents/com.mystock.daily.plist
```

確認 `ProgramArguments` 指向新的 `run_daily.py`（或 `run_daily_v2.py`）

重新載入：
```bash
launchctl unload ~/Library/LaunchAgents/com.mystock.daily.plist
launchctl load ~/Library/LaunchAgents/com.mystock.daily.plist
```

---

## 🎨 前端整合建議

### 方案 A：獨立顯示（推薦）

```javascript
// 讀取 futures_data.json
const data = await fetch('/data/futures_data.json').then(r => r.json());

// MXF 微台指圖表（主要）
const mxfChart = {
  labels: data.history.mxf.map(d => d.date),
  datasets: [{
    label: '微台指散戶多空比 (%)',
    data: data.history.mxf.map(d => d.retail_ratio),
    borderColor: 'rgb(75, 192, 192)',
  }]
};

// TX 大台圖表（輔助參考）
const txChart = {
  labels: data.history.tx.map(d => d.date),
  datasets: [{
    label: 'TX 散戶多空比 (%)',
    data: data.history.tx.map(d => d.retail_ratio),
    borderColor: 'rgb(255, 99, 132)',
  }]
};
```

### 方案 B：雙軸比較圖

```javascript
// 在同一張圖上顯示 MXF 和 TX
const combinedChart = {
  labels: data.history.mxf.map(d => d.date),
  datasets: [
    {
      label: 'MXF 微台指 (散戶)',
      data: data.history.mxf.map(d => d.retail_ratio),
      borderColor: 'rgb(75, 192, 192)',
      yAxisID: 'y',
    },
    {
      label: 'TX 大台 (法人)',
      data: data.history.tx.map(d => d.retail_ratio),
      borderColor: 'rgb(255, 159, 64)',
      yAxisID: 'y',
    }
  ],
  options: {
    scales: {
      y: {
        type: 'linear',
        display: true,
        position: 'left',
        title: { text: '散戶多空比 (%)' }
      }
    }
  }
};
```

### 方案 C：背離提示

```javascript
// 計算背離
function detectDivergence(mxf, tx) {
  const mxfRatio = mxf[mxf.length - 1].retail_ratio;
  const txRatio = tx[tx.length - 1].retail_ratio;
  
  // MXF 偏多但 TX 偏空 → 短線過熱警告
  if (mxfRatio > 10 && txRatio < -5) {
    return {
      type: 'warning',
      message: '⚠️ 散戶追高但法人保守，注意短線過熱'
    };
  }
  
  // MXF 偏空但 TX 偏多 → 可能反彈機會
  if (mxfRatio < -15 && txRatio > 5) {
    return {
      type: 'opportunity',
      message: '💡 散戶恐慌但法人樂觀，可能超跌反彈'
    };
  }
  
  return null;
}
```

---

## 🐛 常見問題

### Q1: 升級後舊數據會消失嗎？
**不會。** `upgrade_database.py` 只新增表格，不刪除任何舊資料。

### Q2: 可以只用 MXF 不用 TX 嗎？
**可以。** 修改 `data_collector_v2.py` 的 `_collect_tx_futures()` 直接 return None 即可。

### Q3: 資料多久更新一次？
**每日收盤後。** 期交所數據通常在晚上 6-7 點公布，建議設定 20:30 自動執行。

### Q4: 如果爬蟲失敗怎麼辦？
1. 檢查網路連線
2. 執行 `python verify_scraper.py` 確認問題
3. 查看 debug 輸出找出錯誤

### Q5: 前端顯示的圖表跟第二張圖一樣嗎？
**概念相同。** 但您的圖表可以更豐富，例如：
- 新增收盤價走勢對照
- 標示極端值（>20% 或 <-20%）
- 顯示法人淨部位

---

## 📝 檔案清單

### 必須更新的檔案
- ✅ `scraper_taifex.py` - 新版爬蟲（支援 MXF）
- ✅ `data_collector.py` - 主收集器（雙資料源）
- ✅ `run_daily.py` - 定時腳本
- ✅ `retail_ratio_collector.py` - 歷史收集器

### 執行一次的檔案
- ✅ `upgrade_database.py` - 資料庫升級
- ✅ `verify_scraper.py` - 驗證數據正確性

### 額外工具（可選）
- `collect_mxf_history.py` - 批量收集歷史數據
- `compare_mxf_tx.py` - 背離分析工具

---

## 🎯 下一步

1. ✅ 完成檔案更新
2. ✅ 升級資料庫
3. ✅ 測試數據收集
4. ⏭️ **更新前端代碼**
5. ⏭️ 調整圖表顯示
6. ⏭️ 部署到生產環境

---

## 📞 需要協助？

如果遇到問題：
1. 執行 `python verify_scraper.py` 確認數據
2. 檢查 `logs/` 目錄的錯誤訊息
3. 提供錯誤訊息讓我協助除錯

---

**整合完成後，您將同時擁有：**
- 📈 TX 大台 → 法人態度指標
- 📊 MXF 微台 → 散戶情緒指標  
- 🔍 背離分析 → 反轉訊號捕捉

這將大幅提升您的交易決策品質！🚀
