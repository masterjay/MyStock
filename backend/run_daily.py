#!/usr/bin/env python3
"""
每日自動執行腳本 v3.0
完整更新所有數據
"""
import sys
import os
from datetime import datetime
from pathlib import Path

# 載入 .env 環境變數
try:
    with open(Path(__file__).parent / ".env") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
except FileNotFoundError:
    pass

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
    print("[1/9] 收集主要數據 (TX + MXF)...")
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
    print("\n[2/9] 收集三大法人買賣金額...")
    try:
        import institutional_money_collector
        institutional_money_collector.main()
        print("  ✓ 完成")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")
    
    # 3. 漲停跌停股
    print("\n[3/9] 收集漲停跌停股...")
    try:
        import limit_updown_collector
        limit_updown_collector.main()
        print("  ✓ 完成")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")
    
    # 4. 外資買賣超排行
    print("\n[4/9] 收集外資買賣超 Top 50...")
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
    print("\n[5/9] 收集產業外資流向...")
    try:
        from industry_foreign_flow_collector import collect_industry_foreign_flow
        collect_industry_foreign_flow()
        print("  ✓ 完成")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")
    
    # 6. 產業熱力圖
    print("\n[6/9] 更新產業熱力圖...")
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
    print("\n[7/9] 收集 MXF 散戶多空比歷史...")
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
    print("\n[8/9] MACD 訊號掃描...")
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

    print("\n[9/10] 收集市場廣度數據...")
    try:
        result = subprocess.run(["python3", "market_breadth_collector.py"],
                              capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print("  ✓ 完成")
        else:
            print(f"  ✗ 失敗: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")

    print("\n[10/10] 產生 market_data.json...")
    try:
        result = subprocess.run(["python3", "market_data_exporter.py"],
                              capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print("  ✓ 完成")
        else:
            print(f"  ✗ 失敗: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")
        print(f"  ✗ 錯誤: {e}")

    # 10. VIX 恐慌指數
    print("\n[10/11] 抓取 VIX 恐慌指數...")
    try:
        result = subprocess.run(['python3', 'fetch_vix.py'],
                              capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print(result.stdout.strip())
            print("  ✓ 完成")
        else:
            print(f"  ✗ 失敗: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")

    # 11. 主流股雷達
    print("\n[11/11] 主流股雷達篩選...")
    try:
        result = subprocess.run(['python3', 'top_volume_screener.py'],
                                capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            print("  ✓ 完成")
        else:
            print(f"  ✗ 失敗: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")

    # 12. Notion 自選股同步
    print("\n[12/12] 同步 Notion 主題自選股...")
    try:
        result = subprocess.run(['python3', 'notion_watchlist.py'],
                              capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print(result.stdout.strip())
            print("  ✓ 完成")
        else:
            print(f"  ✗ 失敗: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")

    # 12. Notion 自選股同步
    print("\n[12/12] 同步 Notion 主題自選股...")
    try:
        result = subprocess.run(['python3', 'notion_watchlist.py'],
                              capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print(result.stdout.strip())
            print("  ✓ 完成")
        else:
            print(f"  ✗ 失敗: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")

    # 13. 處置股監控
    print("\n[13/15] 處置股資料抓取...")
    try:
        result = subprocess.run(["python3", "disposal_stocks.py"],
                              capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print(result.stdout.strip())
            print("  ✓ 完成")
        else:
            print(f"  ✗ 失敗: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")

    # 14. 周轉率數據收集
    print("\n[14/15] 周轉率數據收集...")
    try:
        result = subprocess.run(['python3', 'turnover_collector.py'],
                              capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            print(result.stdout.strip())
            print("  ✓ 完成")
        else:
            print(f"  ✗ 失敗: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")

    # 15. 周轉率分析
    print("\n[15/16] 周轉率過熱分析...")
    try:
        result = subprocess.run(['python3', 'turnover_analyzer.py'],
                              capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print(result.stdout.strip())
            print("  ✓ 完成")
        else:
            print(f"  ✗ 失敗: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")

    # 16. 內部人持股異動 (每月16日後執行)
    if datetime.now().day >= 16:
        print("\n[16/16] 內部人持股異動...")
        try:
            result = subprocess.run(['python3', 'insider_trading_collector.py'],
                                  capture_output=True, text=True, timeout=1800)
            if result.returncode == 0:
                print(result.stdout.strip()[-200:])
                print("  ✓ 完成")
            else:
                print(f"  ✗ 失敗: {result.stderr[:200]}")
        except Exception as e:
            print(f"  ✗ 錯誤: {e}")
    else:
        print("\n[16/16] 內部人持股異動: 每月16日後執行，跳過")

except Exception as e:
    print(f"\n✗ 執行錯誤: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n[補充] 00981A 持股爬蟲...")
import subprocess
subprocess.run(['python3', '/home/s0971417/MyStock/fetch_00981a_holdings.py'], check=False)

print(f"\n{'='*60}")
print(f"✓ 所有數據更新完成!")
print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}\n")
