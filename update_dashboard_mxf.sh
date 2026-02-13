#!/bin/bash

# 備份
cp dashboard.html dashboard.html.backup_$(date +%Y%m%d_%H%M%S)

# 1. 修改圖表標題和數據來源
sed -i 's/微台指散戶多空比 (30日)/微台指散戶多空比 (MXF) - 30日/g' dashboard.html
sed -i 's|retail_ratio_history\.json|futures_data.json|g' dashboard.html

# 2. 創建新的 drawRetailChart 函數（支援 MXF + TX）
cat > /tmp/new_retail_chart.js << 'JS_EOF'
            async function drawRetailChart() {
                try {
                    const response = await fetch('./backend/data/futures_data.json?t=' + new Date().getTime());
                    if (!response.ok) {
                        console.error('無法載入 futures_data.json');
                        return;
                    }
                    
                    const data = await response.json();
                    const mxfHistory = data.history.mxf || [];
                    const txHistory = data.history.tx || [];
                    
                    if (mxfHistory.length === 0) {
                        console.warn('MXF 數據為空');
                        return;
                    }
                    
                    // 準備標籤
                    const labels = mxfHistory.map(d => {
                        const date = d.date;
                        return date.substring(4,6) + '/' + date.substring(6,8);
                    });
                    
                    // MXF 散戶多空比
                    const mxfRatios = mxfHistory.map(d => d.retail_ratio);
                    
                    // 創建圖表
                    new Chart(document.getElementById('retailChart'), {
                        type: 'bar',
                        data: {
                            labels: labels,
                            datasets: [
                                {
                                    label: 'MXF 微台指散戶多空比',
                                    data: mxfRatios,
                                    backgroundColor: mxfRatios.map(v => 
                                        v >= 0 ? 'rgba(16, 185, 129, 0.7)' : 'rgba(239, 68, 68, 0.7)'
                                    ),
                                    borderColor: mxfRatios.map(v => 
                                        v >= 0 ? '#10b981' : '#ef4444'
                                    ),
                                    borderWidth: 1,
                                    order: 1
                                }
                            ]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: {
                                    display: true,
                                    labels: { 
                                        color: '#7d8ba7', 
                                        font: { size: 11 },
                                        generateLabels: function(chart) {
                                            const original = Chart.defaults.plugins.legend.labels.generateLabels(chart);
                                            // 添加說明
                                            original.push({
                                                text: '正值=散戶偏多 | 負值=散戶偏空',
                                                fillStyle: 'transparent',
                                                strokeStyle: 'transparent',
                                                fontColor: '#94a3b8',
                                                fontStyle: 'italic'
                                            });
                                            return original;
                                        }
                                    }
                                },
                                tooltip: {
                                    mode: 'index',
                                    intersect: false,
                                    backgroundColor: 'rgba(0,0,0,0.85)',
                                    titleColor: '#fff',
                                    bodyColor: '#fff',
                                    callbacks: {
                                        title: function(context) {
                                            const idx = context[0].dataIndex;
                                            return '日期: ' + mxfHistory[idx].date;
                                        },
                                        label: function(context) {
                                            const idx = context.dataIndex;
                                            const item = mxfHistory[idx];
                                            return [
                                                '散戶多空比: ' + item.retail_ratio.toFixed(2) + '%',
                                                '散戶做多: ' + item.retail_long.toLocaleString() + ' 口',
                                                '散戶做空: ' + item.retail_short.toLocaleString() + ' 口',
                                                '未平倉量: ' + item.total_oi.toLocaleString() + ' 口'
                                            ];
                                        }
                                    }
                                },
                                annotation: {
                                    annotations: {
                                        zeroline: {
                                            type: 'line',
                                            yMin: 0,
                                            yMax: 0,
                                            borderColor: '#475569',
                                            borderWidth: 2,
                                            borderDash: [5, 5],
                                            label: {
                                                content: '平衡線',
                                                display: true,
                                                position: 'end',
                                                backgroundColor: 'rgba(71, 85, 105, 0.8)',
                                                color: '#fff',
                                                font: { size: 10 }
                                            }
                                        }
                                    }
                                }
                            },
                            scales: {
                                x: {
                                    grid: { color: 'rgba(45, 55, 72, 0.3)' },
                                    ticks: { 
                                        color: '#7d8ba7', 
                                        font: { size: 9 },
                                        maxTicksLimit: 15
                                    }
                                },
                                y: {
                                    grid: { color: 'rgba(45, 55, 72, 0.3)' },
                                    ticks: { 
                                        color: '#7d8ba7',
                                        font: { size: 10 },
                                        callback: function(value) {
                                            return value.toFixed(1) + '%';
                                        }
                                    },
                                    title: {
                                        display: true,
                                        text: '散戶多空比 (%)',
                                        color: '#7d8ba7',
                                        font: { size: 11 }
                                    }
                                }
                            }
                        }
                    });
                    
                    // 顯示最新數值
                    if (data.latest && data.latest.mxf_futures) {
                        const latest = data.latest.mxf_futures;
                        console.log('最新 MXF 數據:', latest);
                        
                        // 更新頁面顯示（如果有對應的元素）
                        const mxfRatioElement = document.getElementById('mxfRetailRatio');
                        if (mxfRatioElement) {
                            mxfRatioElement.textContent = latest.retail_ratio.toFixed(2) + '%';
                            mxfRatioElement.style.color = latest.retail_ratio >= 0 ? 
                                'var(--accent-green)' : 'var(--accent-red)';
                        }
                    }
                    
                } catch (error) {
                    console.error('載入 MXF 數據失敗:', error);
                }
            }
JS_EOF

# 3. 替換原有的 drawRetailChart 函數
# 找到函數開始和結束位置，然後替換
python3 << 'PYTHON_EOF'
import re

with open('dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 讀取新函數
with open('/tmp/new_retail_chart.js', 'r', encoding='utf-8') as f:
    new_function = f.read()

# 使用正則替換 drawRetailChart 函數
pattern = r'async function drawRetailChart\(\).*?^\s{12}\}'
replacement = new_function.strip()

content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)

with open('dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ drawRetailChart 函數已更新")
PYTHON_EOF

echo "✓ Dashboard 更新完成!"
echo ""
echo "修改內容:"
echo "  1. 圖表標題改為「微台指散戶多空比 (MXF)」"
echo "  2. 數據來源改為 futures_data.json"
echo "  3. 顯示 MXF 散戶多空比柱狀圖"
echo "  4. Tooltip 顯示詳細資訊"
echo "  5. 0 線標示（平衡線）"
echo ""
echo "請重新整理瀏覽器查看效果！"

