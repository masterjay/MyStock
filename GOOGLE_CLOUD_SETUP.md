# 台股監控系統 - Google Cloud 部署指南

## 🌩️ 為什麼選 Google Cloud?

- ✅ **免費額度**: 每月 e2-micro VM 免費 (永久)
- ✅ **24/7 運行**: 不需要你的 Mac 開機
- ✅ **公開網址**: 外出也能查看
- ✅ **穩定可靠**: Google 的基礎設施

---

## 📋 前置作業

### 1. 註冊 Google Cloud

1. 前往 https://cloud.google.com/
2. 點擊「開始免費使用」
3. 使用 Google 帳號登入
4. 綁定信用卡 (不會扣款,只是驗證)
5. 獲得 $300 免費額度 (90天)

### 2. 建立專案

1. 進入 [Console](https://console.cloud.google.com/)
2. 點擊「選擇專案」→「新增專案」
3. 專案名稱: `taiwan-stock-monitor`
4. 點擊「建立」

---

## 🚀 部署步驟

### 步驟 1: 建立 VM 實例

1. **進入 Compute Engine**
   - 左側選單 → Compute Engine → VM 執行個體
   - 點擊「建立執行個體」

2. **設定 VM**
   ```
   名稱: stock-monitor-vm
   區域: asia-east1 (台灣)
   機器類型: e2-micro (免費方案)
   開機磁碟: Ubuntu 22.04 LTS (10GB)
   防火牆: 
     ✓ 允許 HTTP 流量
     ✓ 允許 HTTPS 流量
   ```

3. **點擊「建立」**

### 步驟 2: 連線到 VM

1. 在 VM 列表中,點擊「SSH」按鈕
2. 會開啟一個終端視窗

### 步驟 3: 安裝環境

在 SSH 終端中執行:

```bash
# 更新系統
sudo apt-get update
sudo apt-get upgrade -y

# 安裝 Python 3.9+
sudo apt-get install -y python3 python3-pip python3-venv

# 安裝 nginx (網頁伺服器)
sudo apt-get install -y nginx

# 安裝 git
sudo apt-get install -y git
```

### 步驟 4: 上傳專案

**方法 A: 從你的 Mac 上傳**

在你的 Mac 終端執行:
```bash
# 1. 壓縮專案
cd ~/taiwan-stock-monitor-complete
tar -czf stock-monitor.tar.gz .

# 2. 使用 gcloud 上傳 (需先安裝 gcloud CLI)
gcloud compute scp stock-monitor.tar.gz stock-monitor-vm:~ --zone=asia-east1-b
```

**方法 B: 直接在 VM 上下載** (如果你有 GitHub)

```bash
# 在 VM 的 SSH 終端中
git clone https://github.com/你的帳號/taiwan-stock-monitor.git
cd taiwan-stock-monitor
```

**方法 C: 手動上傳** (最簡單)

1. 在 VM 實例頁面,點擊「上傳檔案」
2. 選擇 `taiwan-stock-monitor.zip`
3. 在 SSH 終端中:
```bash
unzip taiwan-stock-monitor.zip
cd taiwan-stock-monitor-complete
```

### 步驟 5: 安裝 Python 套件

```bash
cd ~/taiwan-stock-monitor-complete/backend

# 建立虛擬環境
python3 -m venv venv

# 啟動虛擬環境
source venv/bin/activate

# 安裝套件
pip install -r requirements.txt

# 測試執行
python3 run_daily.py
```

### 步驟 6: 設定定時任務

```bash
# 編輯 crontab
crontab -e

# 選擇編輯器 (選 nano 比較簡單)

# 加入這一行 (每天 20:30 執行)
30 20 * * * cd /home/你的使用者名稱/taiwan-stock-monitor-complete/backend && /home/你的使用者名稱/taiwan-stock-monitor-complete/backend/venv/bin/python3 run_daily.py >> logs/cron.log 2>&1

# 儲存離開 (Ctrl+X, Y, Enter)
```

### 步驟 7: 設定 Nginx (網頁伺服器)

```bash
# 建立 nginx 設定檔
sudo nano /etc/nginx/sites-available/stock-monitor
```

貼上以下內容:
```nginx
server {
    listen 80;
    server_name _;

    root /home/你的使用者名稱/taiwan-stock-monitor-complete/frontend;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    # API endpoint (如果需要即時查詢)
    location /api/ {
        proxy_pass http://localhost:8000/;
    }
}
```

啟用設定:
```bash
# 建立符號連結
sudo ln -s /etc/nginx/sites-available/stock-monitor /etc/nginx/sites-enabled/

# 刪除預設設定
sudo rm /etc/nginx/sites-enabled/default

# 測試設定
sudo nginx -t

# 重新載入 nginx
sudo systemctl reload nginx
```

### 步驟 8: 設定防火牆

```bash
# 允許 HTTP
sudo ufw allow 80

# 允許 SSH
sudo ufw allow 22

# 啟用防火牆
sudo ufw enable
```

---

## 🌐 取得公開網址

### 方法 A: 使用 VM 的外部 IP (免費)

1. 在 Compute Engine 頁面,找到你的 VM
2. 複製「外部 IP」(例如: `34.80.123.45`)
3. 在瀏覽器開啟: `http://34.80.123.45`

**缺點**: IP 可能會變動

### 方法 B: 保留靜態 IP (免費)

1. 左側選單 → VPC 網路 → IP 位址
2. 點擊「保留外部靜態位址」
3. 名稱: `stock-monitor-ip`
4. 附加到: `stock-monitor-vm`
5. 點擊「保留」

現在這個 IP 就固定了!

### 方法 C: 使用自訂網域 (需購買網域)

如果你有網域 (如 `stock.example.com`):

1. 在網域 DNS 設定中,新增 A 記錄:
   ```
   A  stock  34.80.123.45
   ```

2. 修改 nginx 設定:
   ```bash
   sudo nano /etc/nginx/sites-available/stock-monitor
   ```
   
   將 `server_name _;` 改為:
   ```nginx
   server_name stock.example.com;
   ```

3. 安裝 SSL 憑證 (免費):
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d stock.example.com
   ```

---

## 🔍 驗證部署

### 1. 檢查網站

開啟瀏覽器,前往你的 IP:
```
http://你的外部IP
```

應該看到台股監控網站!

### 2. 檢查定時任務

```bash
# 查看 cron 日誌
tail -f ~/taiwan-stock-monitor-complete/backend/logs/cron.log

# 手動執行測試
cd ~/taiwan-stock-monitor-complete/backend
source venv/bin/activate
python3 run_daily.py
```

### 3. 檢查數據

```bash
# 查看最新數據
cat ~/taiwan-stock-monitor-complete/backend/data/market_data.json
```

---

## 💰 費用估算

### 免費方案 (永久)
- VM: e2-micro (免費)
- 網路傳輸: 1GB/月免費
- 儲存: 30GB 免費

**每月費用: $0** (在免費額度內)

### 如果超出免費額度
- VM: ~$7/月
- 網路: ~$1/月
- 總計: ~$8/月

**Tips**: 
- 選 e2-micro 就是免費的
- 台灣區域 (asia-east1) 速度最快
- 記得用免費的靜態 IP

---

## 📱 進階功能

### 1. 設定 HTTPS (免費 SSL)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx
```

### 2. 加入 LINE 通知

修改 `run_daily.py`,加入:
```python
import requests

def send_line_notify(message):
    token = '你的LINE Token'
    url = 'https://notify-api.line.me/api/notify'
    headers = {'Authorization': f'Bearer {token}'}
    data = {'message': message}
    requests.post(url, headers=headers, data=data)

# 在數據收集後
send_line_notify(f'✓ 數據已更新\n融資: {ratio}%\n外資淨部位: {net}')
```

### 3. 設定自動備份

```bash
# 每天備份到 Google Cloud Storage
0 2 * * * gsutil cp ~/taiwan-stock-monitor-complete/backend/market_data.db gs://你的bucket/backups/$(date +\%Y\%m\%d).db
```

---

## ⚠️ 注意事項

1. **安全性**:
   ```bash
   # 只允許特定 IP 連線 SSH (可選)
   sudo ufw allow from 你的家用IP to any port 22
   ```

2. **監控**:
   - Google Cloud Console 可以看 CPU/記憶體使用率
   - 設定警報通知

3. **維護**:
   ```bash
   # 每月更新系統
   sudo apt update && sudo apt upgrade -y
   ```

4. **關機會收費**:
   - VM 關機後 **IP 仍會收費**
   - 如果長期不用,記得刪除 VM

---

## 🎯 快速檢查清單

- [ ] Google Cloud 帳號已建立
- [ ] VM 已建立並運行
- [ ] Python 環境已安裝
- [ ] 專案已上傳
- [ ] 套件已安裝
- [ ] 定時任務已設定
- [ ] Nginx 已設定
- [ ] 網站可以訪問
- [ ] 數據正常更新

---

## 🆘 常見問題

### Q: 忘記外部 IP 怎麼辦?

```bash
# 在 VM SSH 中執行
curl ifconfig.me
```

### Q: 網站打不開?

```bash
# 檢查 nginx 狀態
sudo systemctl status nginx

# 檢查錯誤日誌
sudo tail -f /var/log/nginx/error.log
```

### Q: 定時任務沒執行?

```bash
# 檢查 cron 是否運行
sudo systemctl status cron

# 查看系統日誌
sudo tail -f /var/log/syslog | grep CRON
```

### Q: 如何停止 VM 省錢?

在 Console 中點擊 VM 旁的「停止」按鈕。
**注意**: 停止後無法訪問網站,但不會收費。

---

需要我幫你實際部署嗎? 我可以逐步指導! 🚀
