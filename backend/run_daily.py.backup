#!/usr/bin/env python3
"""
每日自動執行腳本 v2.0
支援 TX + MXF 雙期貨資料源
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
print(f"台股監控 v2.0 - 每日自動執行 (TX + MXF)")
print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}\n")

try:
    # 1. 導入資料收集器 v2
    from data_collector_v2 import DataCollector
    
    # 執行資料收集
    collector = DataCollector()
    
    print("開始收集當日數據 (TX + MXF)...")
    result = collector.collect_daily_data()
    
    if result:
        print("\n✓ 數據收集成功")
        print(f"  • TX 大台: {'✓' if result.get('tx_futures') else '✗'}")
        print(f"  • MXF 微台: {'✓' if result.get('mxf_futures') else '✗'}")
        print(f"  • 融資: {'✓' if result.get('margin') else '✗'}")
        
        # 導出 JSON
        print("\n導出數據到 JSON...")
        collector.export_to_json()
        print("✓ 完成!")
    else:
        print("✗ 數據收集失敗")
        sys.exit(1)
    
    # 2. 收集三大法人買賣金額
    print("\n[額外收集] 三大法人買賣金額統計...")
    try:
        import institutional_money_collector
        institutional_money_collector.main()
        print("✓ 三大法人買賣金額收集完成")
    except Exception as e:
        print(f"✗ 三大法人買賣金額收集失敗: {e}")
    
    # 3. 收集漲停跌停股
    print("\n[額外收集] 漲停跌停股...")
    try:
        import limit_updown_collector
        limit_updown_collector.main()
        print("✓ 漲停跌停股收集完成")
    except Exception as e:
        print(f"✗ 漲停跌停股收集失敗: {e}")
    
    # 4. 收集產業外資流向
    print("\n[額外收集] 產業外資流向...")
    try:
        from industry_foreign_flow_collector import collect_industry_foreign_flow
        collect_industry_foreign_flow()
        print("✓ 產業外資流向收集完成")
    except Exception as e:
        print(f"✗ 產業外資流向收集失敗: {e}")

    # 5. 收集散戶多空比歷史 (更新為讀取 MXF)
    print("\n[額外收集] 微台指散戶多空比歷史...")
    try:
        from retail_ratio_collector_v2 import collect_mxf_ratio_history
        collect_mxf_ratio_history()
        print("✓ 微台指散戶多空比歷史收集完成")
    except Exception as e:
        print(f"✗ 散戶多空比歷史收集失敗: {e}")
        
except Exception as e:
    print(f"✗ 執行錯誤: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"\n{'='*60}")
print(f"執行完成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}\n")
