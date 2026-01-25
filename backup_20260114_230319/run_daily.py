#!/usr/bin/env python3
"""
每日自動執行腳本
由 launchd 定時呼叫
"""
import sys
import os
from datetime import datetime
from pathlib import Path

# 確保在正確的目錄
script_dir = Path(__file__).parent
os.chdir(script_dir)

# 建立 logs 目錄
Path('logs').mkdir(exist_ok=True)

print(f"\n{'='*60}")
print(f"台股監控 - 每日自動執行")
print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}\n")

try:
    # 導入資料收集器
    from data_collector import DataCollector
    
    # 執行資料收集
    collector = DataCollector()
    
    print("開始收集當日數據...")
    result = collector.collect_daily_data()
    
    if result:
        print("✓ 數據收集成功")
        
        # 導出 JSON
        print("導出數據到 JSON...")
        collector.export_to_json()
        print("✓ 完成!")
    else:
        print("✗ 數據收集失敗")
        sys.exit(1)
        
except Exception as e:
    print(f"✗ 執行錯誤: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"\n{'='*60}")
print(f"執行完成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}\n")
