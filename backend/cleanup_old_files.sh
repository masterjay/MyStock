#!/bin/bash

echo "=== 清理舊檔案 ==="
echo ""

# 備份檔案
echo "刪除備份檔案..."
rm -f *.backup* *.old *_backup_*

# 測試/臨時檔案
echo "刪除臨時檔案..."
rm -f fix_*.py
rm -f test_*.py  
rm -f debug_*.py
rm -f regenerate_*.py
rm -f import_*.py
rm -f enrich_*.py
rm -f create_*.py

# 舊版本檔案
echo "刪除舊版本檔案..."
rm -f scraper_taifex_ultimate.py
rm -f stock_master_collector.py
rm -f industry_foreign_flow_v*.py
rm -f foreign_with_price.py
rm -f *_v2.py *_v3.py
rm -f *_final.py
rm -f *_correct.py
rm -f *_simple.py

echo ""
echo "✓ 清理完成"
echo ""
echo "剩餘的 Python 檔案:"
ls -1 *.py | sort

