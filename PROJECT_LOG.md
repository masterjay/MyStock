# TWSE/MyStock 專案日誌

> 每次部署、功能新增、bug 修復、架構變更都記在這裡。**最新的在最上面**。
>
> 與其他兩份文件的分工：
> - `INFRASTRUCTURE.md` = 現況快照（系統現在長什麼樣）
> - `STYLE_GUIDE.md` = 設計規範（UI 應該長什麼樣）
> - `PROJECT_LOG.md` = **時間軸**（什麼時候、為什麼這樣改的）
>
> 細節（commit-level「做了什麼」）靠 git log 自助；本日誌只記 git diff 看不出來的東西：
> 架構決策、踩雷教訓、量化基準、實戰守則、待辦事項。

---

## 撰寫規範

### 條目格式

每個工作階段（通常是一個 commit 或一次部署）一個條目，**最新的放最上面**：

```markdown
## YYYY-MM-DD — 一句話總結

### 🆕 新增 / ✨ 改進 / 🐛 修復 / 🔧 重構 / 🚀 部署 / ⚠️ 事故 / 📝 文件
- 做了什麼（檔案：`path/to/file.py`）
- 為什麼這樣做（如果不直觀）

### 📊 量化數據（如有）
- 回測勝率、預期值、賺賠比等

### 📌 決策 / 守則（如有）
- 為什麼選 A 不選 B
- 凍結點宣告（避免日後過度優化）

### ⚠️ 影響 / 踩雷
- 影響到哪些既有功能 / API / 資料檔
- 是否需要重啟服務 / reload nginx / 重跑 pipeline

### ⏳ 未完成（如有）
- [ ] 待辦事項
```

### 分類 emoji（固定使用，方便日後 grep）

| Emoji | 類別 | 範例 |
|-------|------|------|
| 🆕 | 新增功能 | 新增「新高雷達」 |
| ✨ | 改進既有功能 | 主流股雷達加上 EMA20 條件 |
| 🐛 | Bug 修復 | 修正主題雷達 acceleration 算錯 |
| 🔧 | 重構 / 內部調整 | 把 watchlist 拆成兩個 API |
| 🚀 | 部署 / 基礎建設 | nginx 新增 location 區塊 |
| ⚠️ | 事故 / 近 miss | 差點覆蓋 watchlist.json |
| 📊 | 量化基準 / 回測數據 | V2_F 勝率 62% |
| 📌 | 決策 / 實戰守則 | 凍結優化、持有 20 天紀律 |
| 📝 | 文件更新 | 新增 STYLE_GUIDE.md |
| 🗑️ | 移除 / 廢棄 | 拿掉舊版 turnover 區塊 |
| ⏳ | 未完成 / TODO | crontab 排程待貼 |

### 寫日誌的時機

- **每次 git commit 之後**：把 commit 訊息擴寫成日誌條目（commit-level 細節靠 git log 自助，這裡只記決策與基準）
- **每次 nginx / Flask 服務改動後**：即使沒 commit 也要記
- **每次踩雷之後**：把錯誤跟解法記下來，比補 INFRASTRUCTURE.md「排錯指南」更快
- **每次完成回測或實戰驗證後**：把量化基準寫進來，未來改策略時可對照
- **跨日的工作不要混在一個條目**：寧可一天一條，也不要把一週的事擠在一起

---


## 2026-05-03 — ETF 池長期高點 enrich (Phase A)

### 🆕 新增
- `etf_pool_helper.py`: 從 SQLite 讀 6 檔 ETF 持股，提供機構共識分級
- `enrich_etf_pool.py`: 對 ETF + watchlist 併集股池計算長期高點 + 機構共識
- `data/etf_holdings_blacklist.json`: 非台股代號黑名單機制
- `data/etf_pool_long_term.json`: enrich 結果輸出（自動產生）

### 📌 動機
- 既有 enrich_long_term_high.py 只涵蓋當日新高雷達 ~20 檔，候選池太小
- 想擴大到「機構長期持有」的 ETF 持股核心股，配合策略 #3 形態學突破
- 機構鐵桿股（被多檔 ETF 持有）+ 大週期突破 = 高品質候選

### 📌 決策
- **6 檔 ETF 來源**：00981A / 00992A / 00991A / 00980A / 0050 / 0052
  - 含主動式 ETF 4 檔（不同投信策略）+ 被動式 2 檔（大盤 + 科技）
  - 已有 `fetch_etf_holdings.py` 抓 MoneyDJ → 寫入 SQLite，沿用不重做
- **儲存格式：沿用既有 SQLite**（`market_data.db / etf_holdings_history` table）
  - 不像 K 線資料庫用 CSV，因為 ETF 持股需要跨 ETF/跨日期 JOIN 查詢
- **獨立輸出 etf_pool_long_term.json**：不污染 new_high_stocks.json
- **Tier 分級**：core(6 檔ETF) / strong(4-5) / normal(1-3) / none(0)
  - 依當日資料分佈自然分級，137 檔 ETF 持股呈乾淨金字塔
- **黑名單機制**（解決跨市場代號）：source 端靜默 skip
  - JSON 設定檔：未來遇新非台股代號加 JSON 即可，不用改 code
- **欄位前綴**：`lt_` (長期高點) + `inst_` (機構共識)，避免衝突
- **Tier 顯示用 `🏛️ ×N`**：比 `🏛️🏛️🏛️` 三層 emoji 更精簡

### 📊 部署驗證 (2026-05-03 用 4/30 盤後資料)
- 併集股池 160 檔（etf 137 + watchlist 30 + nh_watchlist 10，去重 + 黑名單）
- 成功 enrich 159 / 160（1 檔黑名單靜默 skip）
- Tier 分佈：core 8 / strong 25 / normal 104 / none 22
- **核心 8 檔（🏛️×6 全持）今日全無大週期突破**：台積電、金像電、台光電、聯發科、奇鋐、健策、日月光、緯穎都還在盤整
- **6 檔 10 年突破**：
  - 8046 南電（🏛️×4，盤整 4 天）— 強共識 + 突破，最值得追
  - 4958 臻鼎-KY（🏛️×1，盤整 4 天）
  - 6147 頎邦（🏛️×1，盤整 5 天）
  - 1597 直得（無 ETF，盤整 38 天）
  - 3605 宏致（無 ETF，盤整 37 天）
  - 6197 佳必琪（無 ETF，盤整 76 天）
- **觀察 1**：機構鐵桿核心 0 突破，真正爆發力在「ETF 沒持有的小型成長股」
- **觀察 2**：PCB 載板族群（南電、臻鼎、頎邦）3 檔同時 10y 突破，題材輪動訊號被 Phase A 確認
- **觀察 3**：金融/電信長期沉睡名單（盤整 ≥ 500 天）：合庫金 722 / 中華電 643 / 兆豐金 624 / 台灣大 527 / 第一金 504。一旦突破會是「長期沉睡股甦醒」訊號

### ⚠️ 事故 / 近 miss
- 首次跑出現 `[121/160] 6061 華星光 ✗ 無資料`
  - 查證：6061 是日本上市 Universal Engeisha Co., Ltd.，非台股 4979 華星光
  - 推測：MoneyDJ 某主動式 ETF 持股清單含跨市場標的
  - **教訓**：ETF 抓取要做代號白/黑名單過濾，不能假設都是台股
  - **解法**：建立 `data/etf_holdings_blacklist.json`，etf_pool_helper.py 在 source 端 skip
- Git commit 時 `data/etf_holdings_blacklist.json` 被 .gitignore 擋下（規則為 `backend/data/`）
  - 雖在 data/ 下，但黑名單是「**設定檔**」（手動維護）不是衍生資料，必須進 git
  - 解法：`git add -f` 強制加入
  - **教訓**：未來在 data/ 下加設定檔要記得 -f；長期可考慮在 .gitignore 加白名單規則

### 🚀 部署
- `run_daily.py` 流程順序調整：
  - **`fetch_etf_holdings.py` 從 [補充] 區段移到前段**（在 enrich 之前）
  - 完整流程：[ETF持股]→[新高雷達]→[長期高點]→[觀察清單]→[ETF池]→[主流股]
- 不需修改 nginx（純檔案 / 純後端，無新 API endpoint）
- 首次跑 5-7 分鐘（160 檔 lazy 補齊 10 年 K 線），之後增量更新 1-2 分鐘
- 本地 K 線資料庫從 38 檔 / 3.64 MB 擴張到 175 檔 / 16.55 MB

### ⏳ 未完成 (Phase B+ 待後續)
- [ ] dashboard 顯示 ETF 池長期高點區塊（用 🏛️×N 徽章）
- [ ] 機構動向訊號（剛進入/離開 ETF 持股）— 等資料累積 1-2 週
- [ ] 5/9 累積 5 天資料後，驗證盤整 0.85 閾值是否合適
- [ ] 盤中假突破偵測（5/3 台肥案例：盤中觸碰但收盤未站穩）
- [ ] AI 每日摘要 — 把「同題材聚集突破」訊號餵給 AI 做解讀（等資料累積後）

---

## 2026-05-03 — 新高雷達加入「長期高點 / 盤整 / 假突破」指標

### 🆕 新增
- `kline_history_manager.py`：本地 CSV 形式的 K 線資料庫管理（每檔一個 CSV，最多 10 年），支援 lazy 補齊
- `long_term_high_calc.py`：1/3/5/10 年高點 + 突破偵測 + 盤整天數 + 假突破警示計算
- `enrich_long_term_high.py`：把計算結果 enrich 進 `new_high_stocks.json`
- 新目錄 `data/kline_history/{code}.csv`：每檔一個 CSV，由 lazy 補齊機制管理
- Dashboard 新高雷達表格新增 2 欄：「大週期」徽章（10y/5y/3y/1y）+ 「盤整(天)」欄
- Dashboard 篩選列新增 4 個按鈕：🚀 3年新高 / 🚀 5年新高 / 🚀 10年新高 / ⚠️ 假突破
- 摘要 pill 新增 🚀10年、🚀5年、🚀3年、⚠️假突破 統計

### 📌 動機
- 老師教的「形態學突破」需要看大週期關鍵高點（Intel 案例 = 10 年箱型突破）
- 既有新高雷達最遠只看到 240 日（≈1 年），無法識別「3 年 / 5 年 / 10 年」尺度的長期突破
- 配合策略 #3「右側突破」做候選股自動篩選

### 📌 決策
- **儲存格式選 CSV 不選 SQLite**：100MB 規模對 GCP 磁碟無感，CSV debug 直觀（vim 直接看）
- **股池採 lazy 補齊**：只追蹤進入新高雷達的股票，不掃全市場（避免 Yahoo 全量擋 IP）
- **時間尺度 4 個（1/3/5/10 年）**：1 年保留以涵蓋台股實際情境（雙鴻、可成都不到 10 年），1 年只在 dashboard 顯示、不發 Discord
- **盤整區間 高點 ×0.85 ~ 1.0**：先試試這個值，之後依實際看到的形態微調
- **假突破窗口 5 日**：突破日後 5 個交易日內跌破突破日最低 = 假突破（較嚴）
- **完全 side-by-side 整合**：不動既有 `new_high_screener.py`，新欄位掛 `lt_` 前綴避免衝突
- **抓取端點對齊既有架構**：用 `query1.finance.yahoo.com/v8/finance/chart/` REST API（跟 `new_high_screener.py` 一致），不引入 `yfinance` 套件依賴

### 🚀 部署
- `run_daily.py` 一次加入 3 個 pipeline step（在主流股雷達之前）：
  1. `new_high_screener.py`（之前手動跑過、這次才進 cron）
  2. `enrich_long_term_high.py`（本次新增）
  3. `update_new_high_watchlist_status.py`（之前已存在但沒在 cron）
- 首次跑會抓每檔 10 年資料（200 檔 × 約 1-2 秒 ≈ 5-7 分鐘），之後每天只抓增量（更快）
- nginx 設定**不需修改**（純檔案 / 純後端，無新 API endpoint）

### 📊 部署驗證（2026-05-03 手動跑，使用 4/30 盤後資料）
- 篩選池 200 檔 → 創新高 20 檔 → enrich 成功 20/20
- 突破分佈：🚀 10y 2 檔（臻鼎-KY 4958、南電 8046）、🚀 3y 1 檔（嘉晶 3016）、🚀 5y/1y 各 0 檔
- 觀察：PCB 載板族群（臻鼎、南電）同時 10 年新高 → 題材輪動訊號
- 觀察：台肥 1722 盤整 297 天，盤中觸碰壓力但收盤未站穩（程式判定未突破，但人工看圖是「測試壓力線」）
  → 已記入 Phase 2 候選：盤中假突破偵測
- 本地 K 線資料庫：38 檔、3.64 MB

### ⚠️ 影響
- `data/` 多 `kline_history/` 目錄（首次部署後約 30-100 MB，全市場版本可達 200 MB）
- `data/new_high_stocks.json` schema 擴充 19 個 `lt_` 前綴欄位（舊欄位不變，向下相容）
- 首次跑 `enrich_long_term_high.py` 比較久（5-7 分鐘），之後正常 cron 流程不影響
- 失敗的股票（找不到 .TW/.TWO 的小型股）`lt_` 欄位為 null，dashboard 顯示 `·`，不影響其他功能

### ⚠️ 事故 / 近 miss
- 部署時發現 `run_daily.py` 從未呼叫 `new_high_screener.py`，但 `data/new_high_stocks.json` 卻存在
  → 推測是過去某次手動跑過留下的舊資料
  → **教訓**：新增 pipeline step 後要立即驗證 cron 真的會跑到（不能只看 `data/` 有檔案就以為自動化）
- 同時發現 `~/MyStock/new_high_screener.py` 與 `~/MyStock/backend/new_high_screener.py` 兩份內容相同的重複檔
  → diff 確認 0 差異，先擱置觀察，未來考慮 mv 為 .deprecated
- Git push 第一次失敗：本機推 dashboard.html 後 GCP 沒 pull，需 `git pull --rebase` 才能 push

### ⏳ 未完成（Phase 2，待累積 1 週資料後再做）
- [ ] Discord 通知 — 大週期突破訊號（3 年以上才推 + 假突破警示）
- [ ] 觀察 1 週後評估盤整 0.85 閾值是否合適
- [ ] 觀察清單裡的股票是否要也納入長期高點計算（目前只追蹤 new_high_stocks.json 內的）
- [ ] **盤中假突破偵測**：當日 high > 過去高點 但 close < 過去高點 + 放量 → 標記 ⚠️
- [ ] 整合 `stock_universe.py`：把 enrich 範圍擴大到合併股池（自選股 + 觀察清單 + 主流股）

## 2026-05-02 — V2_F 回檔買點系統上線

### 🆕 新增
- 策略 **V2_F**：綠柱縮小 + KD 低檔金叉的回檔買點偵測
- `pullback_signal_scanner.py`：每日 18:30 cron 掃描全市場
- Notion + Discord 通知整合（D1 才響、含去重邏輯）
- Dashboard 新增「📍 回檔買點雷達」區塊，與主流股雷達、新高雷達並列三雷達
- crontab 排程30 18 * * 1-5 cd /home/s0971417/MyStock/backend && /usr/bin/python3 pullback_signal_scanner.py >> pullback_cron.log 2>&1
  0 20 * * 0 cd /home/s0971417/MyStock/backend && /usr/bin/python3 pullback_signal_review.py --start $(date -d '7 days ago' +%Y-%m-%d) >> pullback_review_weekly.log>

### 📊 回測基準（2025-01 ~ 2026-04，跨 200+ 檔，共 95 筆訊號）
- 持有 20 天勝率 **62%**
- 預期值 **+6.03%**
- 賺賠比 **2.15:1**
- ⚠️ 月份波動大：甜蜜月勝率 80% / 痛月勝率 12%

### 📌 實戰守則（凍結，不再優化）
- 持有 20 天紀律，**不提前停利或停損**
- 單筆 ≤ 8% 部位（凱利 1/4）
- 同股 D2/D3+ 不加碼
- 接受痛月存在、**連虧 3-4 筆是常態**，不因此懷疑系統

### ⏳ 未完成
- [ ] 累積實盤紀錄
- [ ] 預計 **2026-08** 做 3 個月實盤檢視

---

## 2026-04-30 — 整理設計系統文件

### 📝 文件
- 新增 `STYLE_GUIDE.md`（664 行）：把 dashboard 既有的 GitHub Dark 風格整理成可複用規範
- 新增 `INFRASTRUCTURE.md`(550 行）：把 GCP / nginx / Flask 部署架構文件化

### 📌 動機
- 跨對話協作時，AI 助手常因不知道既有風格而產出 Material Design 風格的橘黃色區塊（v1 新高雷達 UI 出過這狀況）
- 部署相關的「為什麼不能改 GCP 防火牆」這種隱性知識需要明文寫下

### ⚠️ 影響
- 之後新增 dashboard 區塊一律走 STYLE_GUIDE.md 的「複製貼上骨架」（第 11 章）
- 之後新增 API 一律走 INFRASTRUCTURE.md 的 nginx 反代流程，不開新 GCP 防火牆 port

---

## 2026-04 — 新增「新高雷達」與「新高觀察清單」

### 🆕 新增
- `new_high_screener.py`：篩成交金額 Top 200，依 20/60/120/240 日 / 歷史新高分級，5 星強度評分 + 量比 ≥1.5×MA20 的爆量偵測
- `new_high_watchlist_api.py`（port 5002）：新高專用 watchlist CRUD API
- `update_new_high_watchlist_status.py`：每日更新觀察清單股票最新狀態
- 對應 dashboard 區塊：🚀 新高雷達 + ⭐ 新高觀察清單

### 🚀 部署
- nginx 新增 `location /api/new_high_watchlist` 區塊，反代到 `localhost:5002`
- ⚠️ 重要：這個 location 區塊**必須放在 `/api/` 之前**，否則會被舊的 `/api/` 抓走（nginx longest-match）

### ⚠️ 事故 / 近 miss
- 一開始想直接重用舊的 `/api/watchlist`（port 5001、寫入 `data/watchlist.json`）
- 發現會覆蓋既有的 30 檔分類 MACD watchlist
- **決策**：完全拆開——兩個檔（`watchlist.json` vs `new_high_watchlist.json`）+ 兩個 port（5001 vs 5002）+ 兩個 API 前綴
- **教訓**：之後新增 API 一律用唯一前綴，絕不重用舊路徑

### ⚠️ 影響
- `data/` 多了 `new_high_stocks.json`、`new_high_watchlist.json` 兩份檔案
- `run_daily.py` 新增一個 pipeline step

---

## 2026-04 — 新增「主流股雷達」

### 🆕 新增
- 6 條件篩選引擎，4 條以上達標 = 主流股：
  1. 5 日 Top 30 成交金額出現次數
  2. 站上 MA20 的天數
  3. 站上 EMA10 / EMA20
  4. 法人連續買超
  5. 基本面催化（手動標記）
  6. 類股龍頭（手動標記）
- 在 `run_daily.py` 加為**最後一個** pipeline step（依賴前面所有資料產出）

### ⚠️ 影響
- 條件 ① 需要累積 5 日的 `data/top30_history.json` 才會有意義 → 剛部署時會看到很多「條件不足」是正常的，要等 5 個交易日

---

## 2026-04 — 新增「題材輪動雷達」

### 🆕 新增
- `3v2_calc_theme_radar.py`：18 個 CMoney 題材（約 111 檔成分股）的加速度與廣度指標
  - 加速度 = 今日漲跌幅 − 近 5 日平均日漲跌幅
  - 廣度 = 題材內上漲股票占比
- 整合 `foreign_top_stocks.json`：題材內外資/投信買超檔數
- 週日 06:00 cron：`2b_fetch_cmoney_stocks.py` 重抓 CMoney 題材成分

### 📌 動機
- 美股風格的「11 大類股 quadrant 圖」不適合台灣（電子佔比太重，類股輪動訊號被稀釋）
- 改用 CMoney 題材分類，貼近台股實際的籌碼語言

### ⚠️ 影響
- `data/` 多 `theme_radar.json`
- 每週日早上會跑一次 CMoney 抓題材成分（其他天不重抓，避免被擋）

---

## 初始建置（時間早於本日誌）

> 以下為日誌建立前已經完成的功能，僅做摘要存查。

### 🚀 基礎建設
- GCP Compute Engine（Debian 11）+ nginx + Flask + Python 3.11
- 專案路徑 `~/MyStock/`，`~/MyStock/data` symlink 到 `~/MyStock/backend/data`
- `dashboard.html` 走 nginx static + 相對路徑 fetch

### 🆕 早期功能
- TWSE MI_INDEX20 抓取（成交金額 Top 20）
- Yahoo Finance K 線抓取
- MACD 訊號掃描 + 30 檔分類 watchlist（`watchlist_server.py`，port 5001）
- 法人買賣超統計（`foreign_top_stocks.json`）
- 周轉率 / 處置股區塊（dashboard 舊風格區塊，列為「待重構」）

---

*Last updated: 2026-05-03*
