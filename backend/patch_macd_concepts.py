#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MACD Scanner 概念股整合補丁
============================
這個腳本用來修改現有的 macd_signal_scanner.py，
在掃描結果輸出前加上概念股標籤。

使用方式:
  python3 patch_macd_concepts.py

它會在 macd_signal_scanner.py 的 JSON 輸出段落前面
插入概念股標籤 enrichment 邏輯。

---
如果你不想自動 patch，也可以手動在 macd_signal_scanner.py 
的 json.dump 之前加入以下幾行:

```python
# === 概念股標籤 ===
try:
    from concept_stock_collector import enrich_signals_with_concepts
    signals = enrich_signals_with_concepts(signals)
    concept_tagged = sum(1 for s in signals if s.get('concepts'))
    print(f"  → {concept_tagged} 檔有概念股標籤")
except ImportError:
    print("  ℹ concept_stock_collector 不存在，跳過概念標籤")
except Exception as e:
    print(f"  ⚠ 概念標籤失敗: {e}")
```

同時在 output dict 中加入 concepts_meta:

```python
# 在 output = { ... } 中加入:
try:
    from concept_stock_collector import get_concept_labels
    import json as _json
    concept_file = DATA_DIR / 'concept_stocks.json'
    if concept_file.exists():
        with open(concept_file, 'r', encoding='utf-8') as _f:
            _cdata = _json.load(_f)
        output['concepts_meta'] = _cdata.get('concepts', {})
except:
    pass
```
"""

import re
import shutil
from pathlib import Path
from datetime import datetime

SCANNER_FILE = Path(__file__).parent / 'macd_signal_scanner.py'
BACKUP_SUFFIX = datetime.now().strftime('.backup_%Y%m%d_%H%M%S')


def patch_scanner():
    """
    自動在 macd_signal_scanner.py 中插入概念股整合程式碼。
    """
    if not SCANNER_FILE.exists():
        print(f"✗ 找不到 {SCANNER_FILE}")
        return False
    
    content = SCANNER_FILE.read_text(encoding='utf-8')
    
    # 檢查是否已經 patch 過
    if 'enrich_signals_with_concepts' in content:
        print("ℹ macd_signal_scanner.py 已包含概念股整合，跳過")
        return True
    
    # 備份
    backup_path = SCANNER_FILE.with_suffix(BACKUP_SUFFIX)
    shutil.copy2(SCANNER_FILE, backup_path)
    print(f"✓ 已備份: {backup_path}")
    
    # === Patch 1: 在 json.dump 之前加入 enrichment ===
    # 找到 json.dump(output, ...) 那一行的前方
    # 通常在 output_path = DATA_DIR / 'macd_signal_stocks.json' 附近
    
    patch_enrichment = '''
    # === 概念股標籤 ===
    try:
        from concept_stock_collector import enrich_signals_with_concepts
        signals = enrich_signals_with_concepts(signals)
        concept_tagged = sum(1 for s in signals if s.get('concepts'))
        print(f"  → {concept_tagged} 檔有概念股標籤")
    except ImportError:
        print("  ℹ concept_stock_collector 不存在，跳過概念標籤")
    except Exception as e:
        print(f"  ⚠ 概念標籤失敗: {e}")

'''
    
    # 找到 output_path 那行，在它前面插入
    marker = "output_path = DATA_DIR / 'macd_signal_stocks.json'"
    if marker in content:
        content = content.replace(marker, patch_enrichment + '    ' + marker)
        print("✓ Patch 1: 已加入概念股 enrichment")
    else:
        print("⚠ Patch 1: 找不到 output_path 標記，請手動加入")
    
    # === Patch 2: 在 output dict 中加入 concepts_meta ===
    patch_meta = """
    # === 概念股 meta ===
    try:
        concept_file = DATA_DIR / 'concept_stocks.json'
        if concept_file.exists():
            with open(concept_file, 'r', encoding='utf-8') as _f:
                _cdata = json.load(_f)
            output['concepts_meta'] = {
                cid: {'label': cd['label'], 'color': cd['color']}
                for cid, cd in _cdata.get('concepts', {}).items()
            }
    except Exception:
        pass

"""
    
    # 找到 'signals': signals 那行後面插入
    signals_marker = "'signals': signals,"
    if signals_marker in content:
        content = content.replace(
            signals_marker,
            signals_marker + "\n" + patch_meta
        )
        print("✓ Patch 2: 已加入 concepts_meta 到 output")
    else:
        print("⚠ Patch 2: 找不到 signals 標記，請手動加入")
    
    # 寫回
    SCANNER_FILE.write_text(content, encoding='utf-8')
    print(f"✓ 已更新: {SCANNER_FILE}")
    return True


if __name__ == '__main__':
    patch_scanner()
