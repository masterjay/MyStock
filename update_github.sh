#!/bin/bash
echo "=== 更新 GitHub Repository ==="

# 複製檔案到 git repo
echo "1. 複製檔案..."
cp -r ~/taiwan-stock-monitor-complete/* ~/MyStock-temp/
cp ~/taiwan-stock-monitor-complete/.gitignore ~/MyStock-temp/ 2>/dev/null || true

cd ~/MyStock-temp

# 檢查變更
echo ""
echo "2. 檢查變更..."
git status --short

# 添加並提交
echo ""
echo "3. 提交變更..."
git add .

# 輸入 commit message (如果沒提供則用預設)
COMMIT_MSG="${1:-Update dashboard}"
git commit -m "$COMMIT_MSG"

# 推送
echo ""
echo "4. 推送到 GitHub..."
git push origin main

echo ""
echo "✓ 完成! https://github.com/masterjay/MyStock"
