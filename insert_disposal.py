#!/usr/bin/env python3
"""
將處置股區塊插入 dashboard.html
執行: cd ~/MyStock && python3 insert_disposal.py
"""

import re

DASHBOARD = 'dashboard.html'

with open(DASHBOARD, 'r', encoding='utf-8') as f:
    html = f.read()

# ============================================================
# 1. CSS - 插入在 </style> 前（取最後一個 </style>）
# ============================================================
DISPOSAL_CSS = """
/* ==================== 處置股監控區塊 ==================== */
.disposal-section {
    margin: 0 0 30px 0;
    padding: 0;
}
.disposal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 14px;
    flex-wrap: wrap;
    gap: 8px;
}
.disposal-title-row {
    display: flex;
    align-items: center;
    gap: 8px;
}
.disposal-icon { font-size: 1.2em; }
.disposal-title {
    margin: 0;
    font-size: 1.1em;
    font-weight: 800;
    color: var(--text-primary);
    letter-spacing: 1px;
}
.disposal-badge {
    background: var(--accent-red);
    color: #fff;
    border-radius: 12px;
    padding: 2px 10px;
    font-size: 0.75em;
    font-weight: 600;
    min-width: 24px;
    text-align: center;
}
.disposal-badge.zero { background: var(--accent-green); }
.disposal-actions {
    display: flex;
    align-items: center;
    gap: 12px;
}
.disposal-updated {
    font-size: 0.7em;
    color: var(--text-secondary);
}
.disposal-link-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 5px 14px;
    border-radius: 6px;
    background: linear-gradient(135deg, var(--accent-red), #cc2952);
    color: #fff !important;
    text-decoration: none !important;
    font-size: 0.78em;
    font-weight: 600;
    transition: all 0.2s;
    border: 1px solid rgba(255,51,102,0.3);
}
.disposal-link-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 15px rgba(255,51,102,0.3);
}
/* 警示橫幅 */
.disposal-alerts { margin-bottom: 12px; }
.alert-banner {
    background: rgba(255,149,0,0.1);
    border: 1px solid rgba(255,149,0,0.4);
    border-radius: 8px;
    padding: 10px 16px;
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
}
.alert-icon { font-size: 1.1em; }
.alert-text {
    font-size: 0.82em;
    font-weight: 600;
    color: var(--accent-orange);
}
.alert-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}
.alert-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px;
    border-radius: 6px;
    background: rgba(255,149,0,0.08);
    border: 1px solid rgba(255,149,0,0.3);
    font-size: 0.8em;
}
.alert-chip .chip-id {
    font-weight: 700;
    color: var(--accent-orange);
}
.alert-chip .chip-name { color: var(--text-primary); }
.chip-status {
    font-size: 0.72em;
    padding: 1px 6px;
    border-radius: 4px;
    font-weight: 600;
}
.chip-status.disposal { background: var(--accent-red); color: #fff; }
.chip-status.notice { background: var(--accent-orange); color: #fff; }
/* 卡片 grid */
.disposal-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
    margin-bottom: 14px;
}
@media (max-width: 768px) {
    .disposal-grid { grid-template-columns: 1fr; }
}
.disposal-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 14px;
    min-height: 100px;
}
.disposal-card-release {
    border-left: 3px solid var(--accent-green);
}
.disposal-card-active {
    border-left: 3px solid var(--accent-red);
}
.card-label {
    font-size: 0.82em;
    font-weight: 700;
    margin-bottom: 10px;
    color: var(--text-secondary);
    letter-spacing: 0.5px;
}
.disposal-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-height: 220px;
    overflow-y: auto;
}
.disposal-list::-webkit-scrollbar { width: 4px; }
.disposal-list::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 2px; }
.disposal-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 5px 10px;
    border-radius: 5px;
    background: rgba(255,255,255,0.03);
    font-size: 0.8em;
    transition: background 0.15s;
}
.disposal-item:hover { background: rgba(255,255,255,0.07); }
.disposal-item .item-left {
    display: flex;
    align-items: center;
    gap: 6px;
}
.disposal-item .item-id {
    font-weight: 700;
    color: var(--accent-cyan);
    min-width: 42px;
}
.disposal-item .item-name { color: var(--text-secondary); }
.disposal-item .item-right {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.9em;
}
.item-freq {
    padding: 1px 6px;
    border-radius: 4px;
    font-weight: 600;
    font-size: 0.82em;
}
.freq-5 { background: rgba(255,51,102,0.2); color: var(--accent-red); border: 1px solid rgba(255,51,102,0.3); }
.freq-20 { background: rgba(255,149,0,0.2); color: var(--accent-orange); border: 1px solid rgba(255,149,0,0.3); }
.freq-45, .freq-60 { background: rgba(160,100,255,0.2); color: #c084fc; border: 1px solid rgba(160,100,255,0.3); }
.freq-other { background: rgba(125,139,167,0.2); color: var(--text-secondary); border: 1px solid var(--border-color); }
.item-days { font-weight: 600; color: var(--accent-green); }
.item-days.urgent { color: var(--accent-red); animation: disposal-pulse 1.5s infinite; }
@keyframes disposal-pulse { 0%,100%{opacity:1;} 50%{opacity:0.4;} }
.item-period { color: var(--text-secondary); font-size: 0.9em; }
.disposal-empty {
    text-align: center;
    padding: 16px;
    color: var(--text-secondary);
    font-size: 0.82em;
}
.loading-placeholder {
    text-align: center;
    padding: 16px;
    color: var(--text-secondary);
    font-size: 0.82em;
}
/* 快速連結 */
.disposal-quick-links {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}
.dqlink {
    padding: 4px 12px;
    border-radius: 5px;
    font-size: 0.72em;
    font-weight: 500;
    text-decoration: none !important;
    transition: all 0.2s;
    border: 1px solid;
}
.dqlink-risk { color: var(--accent-red); border-color: rgba(255,51,102,0.3); background: rgba(255,51,102,0.05); }
.dqlink-risk:hover { background: rgba(255,51,102,0.15); }
.dqlink-twse { color: var(--accent-cyan); border-color: rgba(0,217,255,0.3); background: rgba(0,217,255,0.05); }
.dqlink-twse:hover { background: rgba(0,217,255,0.15); }
.dqlink-tpex { color: #c084fc; border-color: rgba(160,100,255,0.3); background: rgba(160,100,255,0.05); }
.dqlink-tpex:hover { background: rgba(160,100,255,0.15); }
.dqlink-notice { color: var(--accent-orange); border-color: rgba(255,149,0,0.3); background: rgba(255,149,0,0.05); }
.dqlink-notice:hover { background: rgba(255,149,0,0.15); }
"""

# 找最後一個 </style> 插入 CSS
style_close_pos = html.rfind('</style>')
if style_close_pos == -1:
    print("❌ 找不到 </style>")
    exit(1)
html = html[:style_close_pos] + DISPOSAL_CSS + '\n' + html[style_close_pos:]
print("✅ CSS 已插入")


# ============================================================
# 2. HTML - 插入在 </section> (主流股雷達) 之後、<div id="mainContent"> 之前
# ============================================================
DISPOSAL_HTML = """
            <!-- 處置股監控 -->
            <div id="disposal-section" class="disposal-section">
              <div class="disposal-header">
                <div class="disposal-title-row">
                  <span class="disposal-icon">🚨</span>
                  <span class="disposal-title">處置股監控</span>
                  <span id="disposal-count" class="disposal-badge">--</span>
                </div>
                <div class="disposal-actions">
                  <span id="disposal-updated" class="disposal-updated"></span>
                  <a href="https://attstock.tw/risk" target="_blank" rel="noopener" class="disposal-link-btn">
                    處置大師 ↗
                  </a>
                </div>
              </div>
              <div id="disposal-alerts" class="disposal-alerts" style="display:none;">
                <div class="alert-banner">
                  <span class="alert-icon">⚠️</span>
                  <span class="alert-text">觀察名單中有股票被處置或列為注意股</span>
                </div>
                <div id="alert-list" class="alert-list"></div>
              </div>
              <div class="disposal-grid">
                <div class="disposal-card disposal-card-release">
                  <div class="card-label">📅 即將出關</div>
                  <div id="release-list" class="disposal-list">
                    <div class="loading-placeholder">載入中...</div>
                  </div>
                </div>
                <div class="disposal-card disposal-card-active">
                  <div class="card-label">🔒 處置中</div>
                  <div id="active-list" class="disposal-list">
                    <div class="loading-placeholder">載入中...</div>
                  </div>
                </div>
              </div>
              <div class="disposal-quick-links">
                <a href="https://attstock.tw/risk" target="_blank" class="dqlink dqlink-risk">風險股預測</a>
                <a href="https://www.twse.com.tw/zh/announcement/punish.html" target="_blank" class="dqlink dqlink-twse">證交所公告</a>
                <a href="https://www.tpex.org.tw/web/bulletin/disposal/disposal_result.php?l=zh-tw" target="_blank" class="dqlink dqlink-tpex">櫃買中心公告</a>
                <a href="https://www.twse.com.tw/zh/announcement/notice.html" target="_blank" class="dqlink dqlink-notice">注意股公告</a>
              </div>
            </div>
"""

# 錨點: </section> 後面接著 <div id="mainContent"
anchor = '</section>\n        <div id="mainContent"'
if anchor in html:
    html = html.replace(anchor, '</section>\n' + DISPOSAL_HTML + '\n        <div id="mainContent"', 1)
    print("✅ HTML 已插入（主流股雷達後、mainContent 前）")
else:
    # 嘗試寬鬆匹配
    anchor2 = '</section>\n'
    # 找第一個 </section> 後面有 mainContent 的
    pattern = r'(</section>\s*)<div id="mainContent"'
    match = re.search(pattern, html)
    if match:
        insert_pos = match.start() + len(match.group(1))
        html = html[:insert_pos] + DISPOSAL_HTML + '\n' + html[insert_pos:]
        print("✅ HTML 已插入（regex 匹配）")
    else:
        print("❌ 找不到 HTML 插入錨點，請手動插入")
        print("   建議位置: </section> (line ~3605) 之後")


# ============================================================
# 3. JS - 插入在 </script> 前（最後一個）
# ============================================================
DISPOSAL_JS = """
// ==================== 處置股監控 JS ====================
(function() {
  var DISPOSAL_URL = './data/disposal_stocks.json';

  function loadDisposalData() {
    fetch(DISPOSAL_URL + '?t=' + Date.now())
      .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function(data) { renderDisposal(data); })
      .catch(function(e) {
        console.warn('[處置股] 載入失敗:', e);
        var al = document.getElementById('active-list');
        var rl = document.getElementById('release-list');
        if (al) al.innerHTML = '<div class="disposal-empty">資料載入失敗</div>';
        if (rl) rl.innerHTML = '<div class="disposal-empty">--</div>';
      });
  }

  function renderDisposal(data) {
    var updEl = document.getElementById('disposal-updated');
    if (updEl && data.updated_at) updEl.textContent = '更新: ' + data.updated_at;

    var countEl = document.getElementById('disposal-count');
    var count = data.total_disposal_count || 0;
    if (countEl) {
      countEl.textContent = count;
      if (count === 0) countEl.classList.add('zero');
    }

    renderAlerts(data.watchlist_alerts || []);
    renderReleaseList(data.upcoming_release || []);
    renderActiveList(data.active_disposals || []);
  }

  function renderAlerts(alerts) {
    var container = document.getElementById('disposal-alerts');
    var list = document.getElementById('alert-list');
    if (!container || !list) return;
    if (!alerts.length) { container.style.display = 'none'; return; }
    container.style.display = 'block';
    list.innerHTML = alerts.map(function(a) {
      var statuses = (a.status || []).map(function(s) {
        var cls = s === '處置中' ? 'disposal' : 'notice';
        return '<span class="chip-status ' + cls + '">' + s + '</span>';
      }).join('');
      return '<div class="alert-chip">' +
        '<span class="chip-id">' + a.stock_id + '</span>' +
        '<span class="chip-name">' + a.stock_name + '</span>' +
        statuses + '</div>';
    }).join('');
  }

  function renderReleaseList(items) {
    var el = document.getElementById('release-list');
    if (!el) return;
    if (!items.length) { el.innerHTML = '<div class="disposal-empty">近期無出關股</div>'; return; }
    el.innerHTML = items.map(function(d) {
      var freqHtml = d.match_frequency ? '<span class="item-freq ' + getFreqClass(d.match_frequency) + '">' + d.match_frequency + '</span>' : '';
      var daysText = d.days_left === 0 ? '今日出關' : d.days_left === 1 ? '明日出關' : d.days_left + '日後';
      var urgent = d.days_left <= 1 ? ' urgent' : '';
      return '<div class="disposal-item">' +
        '<div class="item-left"><span class="item-id">' + d.stock_id + '</span><span class="item-name">' + d.stock_name + '</span></div>' +
        '<div class="item-right">' + freqHtml + '<span class="item-days' + urgent + '">' + daysText + '</span></div></div>';
    }).join('');
  }

  function renderActiveList(items) {
    var el = document.getElementById('active-list');
    if (!el) return;
    if (!items.length) { el.innerHTML = '<div class="disposal-empty">目前無處置股 ✅</div>'; return; }
    el.innerHTML = items.map(function(d) {
      var freqHtml = d.match_frequency ? '<span class="item-freq ' + getFreqClass(d.match_frequency) + '">' + d.match_frequency + '</span>' : '';
      var periodHtml = d.end_date_str ? '<span class="item-period">~' + d.end_date_str + '</span>' : '';
      return '<div class="disposal-item">' +
        '<div class="item-left"><span class="item-id">' + d.stock_id + '</span><span class="item-name">' + d.stock_name + '</span></div>' +
        '<div class="item-right">' + freqHtml + periodHtml + '</div></div>';
    }).join('');
  }

  function getFreqClass(freq) {
    if (!freq) return '';
    if (freq.indexOf('5') !== -1 && freq.indexOf('45') === -1) return 'freq-5';
    if (freq.indexOf('20') !== -1) return 'freq-20';
    if (freq.indexOf('45') !== -1 || freq.indexOf('60') !== -1) return 'freq-45';
    return 'freq-other';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadDisposalData);
  } else {
    loadDisposalData();
  }
})();
"""

# 找最後一個 </script> 插入 JS
script_close_pos = html.rfind('</script>')
if script_close_pos == -1:
    print("❌ 找不到 </script>")
    exit(1)
html = html[:script_close_pos] + DISPOSAL_JS + '\n' + html[script_close_pos:]
print("✅ JS 已插入")


# ============================================================
# 寫回
# ============================================================
with open(DASHBOARD, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"\n🎉 dashboard.html 已更新！請重整瀏覽器查看處置股區塊。")
