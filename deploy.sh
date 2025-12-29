#!/bin/bash
# Google Cloud 一鍵部署腳本
# 在 VM SSH 終端中執行

set -e

echo "=================================================="
echo "台股監控系統 - Google Cloud 自動部署"
echo "=================================================="

# 取得目前使用者
USER=$(whoami)
HOME_DIR="/home/$USER"

echo ""
echo "[1/7] 更新系統..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq

echo ""
echo "[2/7] 安裝必要套件..."
sudo apt-get install -y -qq python3 python3-pip python3-venv nginx unzip

echo ""
echo "[3/7] 解壓縮專案..."
if [ -f "$HOME_DIR/taiwan-stock-monitor.zip" ]; then
    cd $HOME_DIR
    unzip -q taiwan-stock-monitor.zip
    cd taiwan-stock-monitor-complete
    echo "✓ 專案已解壓縮"
else
    echo "✗ 找不到 taiwan-stock-monitor.zip"
    echo "請先上傳 zip 檔案到 VM"
    exit 1
fi

echo ""
echo "[4/7] 建立 Python 環境..."
cd $HOME_DIR/taiwan-stock-monitor-complete/backend
python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt
echo "✓ Python 套件已安裝"

echo ""
echo "[5/7] 建立 logs 目錄..."
mkdir -p logs

echo ""
echo "[6/7] 設定 Nginx..."
sudo tee /etc/nginx/sites-available/stock-monitor > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    root $HOME_DIR/taiwan-stock-monitor-complete/frontend;
    index index.html;

    location / {
        try_files \$uri \$uri/ =404;
    }

    location /data/ {
        alias $HOME_DIR/taiwan-stock-monitor-complete/backend/data/;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/stock-monitor /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
echo "✓ Nginx 已設定"

echo ""
echo "[7/7] 設定定時任務..."
(crontab -l 2>/dev/null | grep -v "taiwan-stock-monitor"; echo "30 20 * * * cd $HOME_DIR/taiwan-stock-monitor-complete/backend && $HOME_DIR/taiwan-stock-monitor-complete/backend/venv/bin/python3 run_daily.py >> logs/cron.log 2>&1") | crontab -
echo "✓ 定時任務已設定 (每天 20:30)"

echo ""
echo "=================================================="
echo "✓ 部署完成!"
echo "=================================================="
echo ""
echo "網站網址: http://$(curl -s ifconfig.me)"
echo "資料收集: 每天 20:30 自動執行"
echo ""
echo "測試執行:"
echo "  cd $HOME_DIR/taiwan-stock-monitor-complete/backend"
echo "  source venv/bin/activate"
echo "  python3 run_daily.py"
echo ""
echo "查看日誌:"
echo "  tail -f $HOME_DIR/taiwan-stock-monitor-complete/backend/logs/cron.log"
echo ""
