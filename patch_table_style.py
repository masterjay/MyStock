#!/usr/bin/env python3
"""
處置股改為表格式排列
"""

with open('dashboard.html', 'r', encoding='utf-8') as f:
    h = f.read()

# 1. 替換 JS renderActiveList - 加序號、改結構
old_active = """    el.innerHTML = items.map(function(d) {
      var freqHtml = d.match_frequency ? '<span class="item-freq ' + getFreqClass(d.match_frequency) + '">' + d.match_frequency + '</span>' : '';
      var periodHtml = d.end_date_str ? '<span class="item-period">~' + d.end_date_str + '</span>' : '';
      return '<div class="disposal-item">' +
        '<div class="item-left"><a class="item-id" href="https://tw.stock.yahoo.com/quote/' + d.stock_id + '" target="_blank" rel="noopener">' + d.stock_id + '</a><span class="item-name">' + d.stock_name + '</span></div>' +
        '<div class="item-right">' + freqHtml + periodHtml + '</div></div>';
    }).join('');"""

new_active = """    el.innerHTML = items.map(function(d, i) {
      var freqHtml = d.match_frequency ? '<span class="item-freq ' + getFreqClass(d.match_frequency) + '">' + d.match_frequency + '</span>' : '';
      var periodHtml = d.end_date_str ? '<span class="item-period">~' + d.end_date_str + '</span>' : '';
      return '<div class="disposal-row">' +
        '<span class="row-num">' + (i+1) + '</span>' +
        '<a class="row-id" href="https://tw.stock.yahoo.com/quote/' + d.stock_id + '" target="_blank" rel="noopener">' + d.stock_id + '</a>' +
        '<span class="row-name">' + d.stock_name + '</span>' +
        '<div class="row-tags">' + freqHtml + periodHtml + '</div>' +
        '</div>';
    }).join('');"""

# 2. 替換 JS renderReleaseList
old_release = """    el.innerHTML = items.map(function(d) {
      var freqHtml = d.match_frequency ? '<span class="item-freq ' + getFreqClass(d.match_frequency) + '">' + d.match_frequency + '</span>' : '';
      var daysText = d.days_left === 0 ? '今日出關' : d.days_left === 1 ? '明日出關' : d.days_left + '日後';
      var urgent = d.days_left <= 1 ? ' urgent' : '';
      return '<div class="disposal-item">' +
        '<div class="item-left"><a class="item-id" href="https://tw.stock.yahoo.com/quote/' + d.stock_id + '" target="_blank" rel="noopener">' + d.stock_id + '</a><span class="item-name">' + d.stock_name + '</span></div>' +
        '<div class="item-right">' + freqHtml + '<span class="item-days' + urgent + '">' + daysText + '</span></div></div>';
    }).join('');"""

new_release = """    el.innerHTML = items.map(function(d, i) {
      var freqHtml = d.match_frequency ? '<span class="item-freq ' + getFreqClass(d.match_frequency) + '">' + d.match_frequency + '</span>' : '';
      var daysText = d.days_left === 0 ? '今日出關' : d.days_left === 1 ? '明日出關' : d.days_left + '日後';
      var urgent = d.days_left <= 1 ? ' urgent' : '';
      return '<div class="disposal-row">' +
        '<span class="row-num">' + (i+1) + '</span>' +
        '<a class="row-id" href="https://tw.stock.yahoo.com/quote/' + d.stock_id + '" target="_blank" rel="noopener">' + d.stock_id + '</a>' +
        '<span class="row-name">' + d.stock_name + '</span>' +
        '<div class="row-tags">' + freqHtml + '<span class="item-days' + urgent + '">' + daysText + '</span></div>' +
        '</div>';
    }).join('');"""

c1 = h.count(old_active)
h = h.replace(old_active, new_active)
c2 = h.count(old_release)
h = h.replace(old_release, new_release)

# 3. 加新的表格行 CSS
new_css = """
/* 處置股表格行樣式 */
.disposal-row {
    display: flex;
    align-items: center;
    padding: 8px 10px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    font-size: 0.82em;
    transition: background 0.15s;
    gap: 0;
}
.disposal-row:last-child { border-bottom: none; }
.disposal-row:hover { background: rgba(255,255,255,0.05); }
.row-num {
    width: 28px;
    text-align: center;
    color: var(--text-secondary);
    font-size: 0.85em;
    flex-shrink: 0;
}
.row-id {
    width: 60px;
    text-align: center;
    font-weight: 700;
    color: var(--accent-cyan);
    text-decoration: none;
    flex-shrink: 0;
}
.row-id:hover { opacity: 0.7; text-decoration: underline; }
.row-name {
    flex: 1;
    color: var(--text-primary);
    padding-left: 10px;
}
.row-tags {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
    margin-left: auto;
}
"""

anchor = '/* ==================== 處置股監控區塊 ===================='
if anchor in h:
    h = h.replace(anchor, new_css + anchor)

with open('dashboard.html', 'w', encoding='utf-8') as f:
    f.write(h)

print(f"✅ active list 替換: {c1} 處")
print(f"✅ release list 替換: {c2} 處")
print("🎉 完成！處置股改為表格式排列")
