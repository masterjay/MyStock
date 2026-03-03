#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_dashboard_concepts.py - 自動 patch dashboard.html 加入概念股篩選"""

import shutil
from pathlib import Path
from datetime import datetime

# dashboard.html 在 ~/MyStock/ 目錄
DASHBOARD = Path(__file__).parent.parent / 'dashboard.html'
if not DASHBOARD.exists():
    DASHBOARD = Path(__file__).parent / 'dashboard.html'

def patch():
    if not DASHBOARD.exists():
        print(f"✗ 找不到 {DASHBOARD}")
        return

    backup = DASHBOARD.with_name(DASHBOARD.name + '.backup_concept_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    shutil.copy2(DASHBOARD, backup)
    print(f"✓ 已備份: {backup.name}")

    content = DASHBOARD.read_text(encoding='utf-8')
    changes = 0

    # === 1. CSS ===
    concept_css = """
/* === 概念股標籤篩選 === */
.concept-filter-bar { display:flex; flex-wrap:wrap; gap:6px; padding:8px 0; margin-bottom:8px; border-bottom:1px solid rgba(255,255,255,0.06); }
.concept-filter-btn { display:inline-flex; align-items:center; gap:4px; padding:4px 10px; border-radius:14px; border:1px solid rgba(255,255,255,0.15); background:rgba(255,255,255,0.04); color:#9CA3AF; font-size:12px; cursor:pointer; transition:all 0.2s; white-space:nowrap; }
.concept-filter-btn:hover { background:rgba(255,255,255,0.08); color:#D1D5DB; }
.concept-filter-btn.active { border-color:var(--concept-color,#6B7280); background:color-mix(in srgb,var(--concept-color,#6B7280) 20%,transparent); color:#F3F4F6; }
.concept-filter-btn .dot { width:6px; height:6px; border-radius:50%; background:var(--concept-color,#6B7280); }
.concept-filter-btn .count { font-size:10px; opacity:0.7; margin-left:2px; }
.signal-concepts { display:flex; flex-wrap:wrap; gap:3px; margin-top:4px; }
.concept-tag { display:inline-block; padding:1px 6px; border-radius:8px; font-size:10px; line-height:16px; background:color-mix(in srgb,var(--tag-color,#6B7280) 15%,transparent); color:var(--tag-color,#9CA3AF); border:1px solid color-mix(in srgb,var(--tag-color,#6B7280) 30%,transparent); white-space:nowrap; }
.macd-signal-card.concept-hidden { display:none !important; }
"""
    idx = content.rfind('</style>')
    if idx > 0 and 'concept-filter-bar' not in content:
        content = content[:idx] + concept_css + content[idx:]
        changes += 1
        print("✓ 1/6 CSS 已插入")

    # === 2. HTML ===
    old_tabs = '<div class="macd-date-tabs" id="macd-date-tabs"></div>'
    new_tabs = old_tabs + '\n            <div id="concept-filter-bar" class="concept-filter-bar" style="display:none;"></div>'
    if old_tabs in content and 'concept-filter-bar' not in content:
        content = content.replace(old_tabs, new_tabs, 1)
        changes += 1
        print("✓ 2/6 concept-filter-bar HTML 已插入")

    # === 3. initConceptFilter 呼叫 ===
    old_init = '        initMacdControls();'
    new_init = old_init + '\n        initConceptFilter(_macdAllDays[_macdCurrentDate]);'
    if old_init in content and 'initConceptFilter' not in content:
        content = content.replace(old_init, new_init, 1)
        changes += 1
        print("✓ 3/6 initConceptFilter 呼叫已加入")

    # === 4. 日期切換 ===
    old_switch = "            updateMacdMeta();\n            renderMacdSignals();\n        });\n    });\n}"
    new_switch = "            updateMacdMeta();\n            renderMacdSignals();\n            initConceptFilter(_macdAllDays[_macdCurrentDate]);\n        });\n    });\n}"
    if old_switch in content and content.count('initConceptFilter') < 3:
        content = content.replace(old_switch, new_switch, 1)
        changes += 1
        print("✓ 4/6 日期切換概念篩選已加入")

    # === 5. 卡片 ===
    old_card = "return '<div class=\"macd-signal-card\" data-url=\"' + yahooUrl + '\">' +"
    new_card = """var conceptHtml = (s.concepts||[]).map(function(c){ return '<span class="concept-tag" style="--tag-color:'+c.color+'">'+c.label+'</span>'; }).join('');
        var conceptIds = (s.concepts||[]).map(function(c){ return c.id; }).join(',');
        return '<div class="macd-signal-card" data-url="' + yahooUrl + '" data-concepts="' + conceptIds + '">' +"""
    if old_card in content and 'conceptIds' not in content:
        content = content.replace(old_card, new_card, 1)
        changes += 1
        print("✓ 5/6 卡片 data-concepts 已加入")

        old_badges = "'<span class=\"macd-badge macd-badge-source\">' + (s.source || '') + '</span>' +\n                    '</div>' +\n                '</div>' +"
        new_badges = "'<span class=\"macd-badge macd-badge-source\">' + (s.source || '') + '</span>' +\n                    '</div>' +\n                    (conceptHtml ? '<div class=\"signal-concepts\">' + conceptHtml + '</div>' : '') +\n                '</div>' +"
        if old_badges in content:
            content = content.replace(old_badges, new_badges, 1)
            print("  + 概念標籤 HTML 已加入卡片")

    # === 6. JS 函式 ===
    concept_js = """
// === 概念股篩選 ===
var _activeConceptFilter = null;
var _conceptsMeta = {};
function initConceptFilter(macdData) {
    var bar = document.getElementById('concept-filter-bar');
    if (!bar) return;
    _conceptsMeta = macdData.concepts_meta || {};
    var signals = macdData.signals || [];
    var counts = {};
    var any = false;
    signals.forEach(function(s) {
        (s.concepts||[]).forEach(function(c) {
            counts[c.id] = (counts[c.id]||0) + 1;
            any = true;
            if (!_conceptsMeta[c.id]) _conceptsMeta[c.id] = {label:c.label, color:c.color};
        });
    });
    if (!any) { bar.style.display='none'; return; }
    bar.style.display = 'flex';
    var h = '<button class="concept-filter-btn active" data-concept="all" style="--concept-color:#6B7280"><span class="dot"></span>\\u5168\\u90E8 <span class="count">'+signals.length+'</span></button>';
    Object.keys(counts).sort(function(a,b){return counts[b]-counts[a];}).forEach(function(cid) {
        var m = _conceptsMeta[cid]||{};
        h += '<button class="concept-filter-btn" data-concept="'+cid+'" style="--concept-color:'+(m.color||'#6B7280')+'"><span class="dot"></span>'+(m.label||cid)+' <span class="count">'+counts[cid]+'</span></button>';
    });
    bar.innerHTML = h;
    _activeConceptFilter = null;
    bar.querySelectorAll('.concept-filter-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            bar.querySelectorAll('.concept-filter-btn').forEach(function(b){b.classList.remove('active');});
            this.classList.add('active');
            _activeConceptFilter = this.getAttribute('data-concept')==='all' ? null : this.getAttribute('data-concept');
            document.querySelectorAll('.macd-signal-card').forEach(function(card) {
                if (!_activeConceptFilter) { card.classList.remove('concept-hidden'); return; }
                var cc = card.getAttribute('data-concepts')||'';
                if (cc.indexOf(_activeConceptFilter)>=0) card.classList.remove('concept-hidden');
                else card.classList.add('concept-hidden');
            });
        });
    });
}

"""
    if 'function initConceptFilter' not in content:
        marker = 'function initMacdModal()'
        if marker in content:
            content = content.replace(marker, concept_js + marker)
            changes += 1
            print("✓ 6/6 概念篩選 JS 函式已插入")

    DASHBOARD.write_text(content, encoding='utf-8')
    print(f"\n共完成 {changes} 處修改")
    print(f"檔案: {DASHBOARD}")

if __name__ == '__main__':
    patch()
