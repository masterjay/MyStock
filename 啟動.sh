#!/bin/bash

echo "===================================="
echo "台股監控系統 - 一鍵啟動 (Mac/Linux)"
echo "===================================="
echo ""

# 檢查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 找不到 Python3，請先安裝"
    exit 1
fi

echo "✓ Python3 已安裝"
echo ""

# 安裝依賴
echo "正在安裝依賴套件..."
cd backend
pip3 install -r requirements.txt -q 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✓ 依賴套件安裝完成"
else
    echo "⚠ 依賴套件安裝可能有問題，繼續執行..."
fi
echo ""

# 執行數據收集
echo "正在收集市場數據..."
echo "建議選擇選項 2 (收集過去 30 天的歷史數據)"
echo ""
python3 data_collector.py

# 檢查結果
if [ -f "../data/market_data.json" ]; then
    echo ""
    echo "✓ 數據收集完成!"
    echo ""
    echo "下一步: 用瀏覽器開啟 dashboard.html"
    echo ""
    
    read -p "是否要立即開啟網站? (y/n): " open
    if [[ $open == "y" || $open == "Y" ]]; then
        cd ..
        if [[ "$OSTYPE" == "darwin"* ]]; then
            open dashboard.html
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            xdg-open dashboard.html 2>/dev/null || echo "請手動開啟 dashboard.html"
        fi
    fi
else
    echo ""
    echo "⚠ 數據收集可能失敗"
    echo "  請檢查是否為交易日或網路連線"
    echo ""
fi

echo "===================================="
echo "完成!"
echo "===================================="
