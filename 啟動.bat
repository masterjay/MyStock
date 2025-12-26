@echo off
chcp 65001 >nul
echo ====================================
echo 台股監控系統 - 一鍵啟動 (Windows)
echo ====================================
echo.

REM 檢查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 找不到 Python，請先安裝 Python 3.8+
    pause
    exit /b 1
)

echo ✓ Python 已安裝
echo.

REM 安裝依賴
echo 正在安裝依賴套件...
cd backend
pip install -r requirements.txt -q
if errorlevel 1 (
    echo ⚠ 依賴套件安裝可能有問題
) else (
    echo ✓ 依賴套件安裝完成
)
echo.

REM 執行數據收集
echo 正在收集市場數據...
echo 建議選擇選項 2 (收集過去 30 天的歷史數據)
echo.
python data_collector.py

REM 檢查結果
if exist "..\data\market_data.json" (
    echo.
    echo ✓ 數據收集完成!
    echo.
    echo 下一步: 用瀏覽器開啟 dashboard.html
    echo.
    
    set /p open="是否要立即開啟網站? (y/n): "
    if /i "%open%"=="y" (
        cd ..
        start dashboard.html
    )
) else (
    echo.
    echo ⚠ 數據收集可能失敗
    echo   請檢查是否為交易日或網路連線
    echo.
)

echo ====================================
echo 按任意鍵退出...
pause >nul
