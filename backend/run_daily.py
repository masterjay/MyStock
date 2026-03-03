#!/usr/bin/env python3
"""
每日自動執行腳本 v3.0
完整更新所有數據
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
print(f"台股監控 v3.0 - 每日自動執行")
print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}\n")

try:
    # 1. 主要數據收集器
    print("[1/8] 收集主要數據 (TX + MXF)...")
    try:
        from data_collector_v2 import DataCollector
        collector = DataCollector()
        result = collector.collect_daily_data()
        
        if result:
            print("  ✓ 主要數據收集成功")
            collector.export_to_json()
        else:
            print("  ✗ 主要數據收集失敗")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")
    
    # 2. 三大法人買賣金額
    print("\n[2/8] 收集三大法人買賣金額...")
    try:
        import institutional_money_collector
        institutional_money_collector.main()
        print("  ✓ 完成")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")
    
    # 3. 漲停跌停股
    print("\n[3/8] 收集漲停跌停股...")
    try:
        import limit_updown_collector
        limit_updown_collector.main()
        print("  ✓ 完成")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")
    
    # 4. 外資買賣超排行
    print("\n[4/8] 收集外資買賣超 Top 50...")
    try:
        import subprocess
        result = subprocess.run(['python3', 'foreign_with_price_v2.py'], 
                              capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print("  ✓ 完成")
        else:
            print(f"  ✗ 失敗: {result.stderr}")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")
    
    # 5. 產業外資流向
    print("\n[5/8] 收集產業外資流向...")
    try:
        from industry_foreign_flow_collector import collect_industry_foreign_flow
        collect_industry_foreign_flow()
        print("  ✓ 完成")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")
    
    # 6. 產業熱力圖
    print("\n[6/8] 更新產業熱力圖...")
    try:
        import subprocess
        result = subprocess.run(['python3', 'industry_heatmap_collector.py'], 
                              capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            # 後處理：合併外資數據
            result2 = subprocess.run(["python3", "fix_to_wan_zhang_with_change.py"], 
                                    capture_output=True, text=True, timeout=30)
            if result2.returncode == 0:
                print("  ✓ 完成 (含外資合併)")
            else:
                print(f"  △ 熱力圖OK但外資合併失敗: {result2.stderr}")
        else:
            print(f"  ✗ 失敗: {result.stderr}")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")

    # 7. MXF 散戶多空比歷史
    print("\n[7/8] 收集 MXF 散戶多空比歷史...")
    try:
        from retail_ratio_collector_v2 import collect_mxf_ratio_history
        collect_mxf_ratio_history()
        print("  ✓ 完成")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")

    # 概念股收集 (每週一更新)
    from datetime import datetime as _dt
    if _dt.now().weekday() == 0:
        print("\n[概念股] 每週更新概念股對照表...")
        try:
            result = subprocess.run(['python3', 'concept_stock_collector.py'],
                                  capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                print("  ✓ 完成")
            else:
                print(f"  ✗ 失敗: {result.stderr[:200]}")
        except Exception as e:
            print(f"  ✗ 錯誤: {e}")
    else:
        print("\n[概念股] 非週一，跳過")

    # 8. MACD 訊號掃描
    print("\n[8/8] MACD 訊號掃描...")
    try:
        import subprocess
        result = subprocess.run(['python3', 'macd_signal_scanner.py'],
                              capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            print("  ✓ 完成")
            try:
                import json
                with open('data/macd_signal_stocks.json', 'r') as f:
                    sig_data = json.load(f)
                print(f"  → 找到 {sig_data.get('signal_count', 0)} 檔訊號股")
            except:
                pass
        else:
            print(f"  ✗ 失敗: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")

except Exception as e:
    print(f"\n✗ 執行錯誤: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"\n{'='*60}")
print(f"✓ 所有數據更新完成!")
print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}\n")
