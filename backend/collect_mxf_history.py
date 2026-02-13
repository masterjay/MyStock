#!/usr/bin/env python3
"""
批量收集微台指 (MXF) 歷史數據
用於首次整合時補齊過去 30-60 天的數據
"""
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# 確保在正確的目錄
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from scraper_taifex_v2 import TAIFEXScraper
import sqlite3

class MXFHistoryCollector:
    def __init__(self, db_path='data/market_data.db'):
        self.db_path = db_path
        self.scraper = TAIFEXScraper()
    
    def collect_history(self, days=30, delay=2):
        """
        收集過去 N 天的 MXF 數據
        
        Args:
            days: 要收集的天數
            delay: 每次請求間隔（秒），避免被封鎖
        """
        print(f"\n{'='*60}")
        print(f"微台指 (MXF) 歷史數據收集工具")
        print(f"目標: 收集過去 {days} 天的數據")
        print(f"{'='*60}\n")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 檢查 mxf_futures_data 表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='mxf_futures_data'
        """)
        
        if not cursor.fetchone():
            print("✗ mxf_futures_data 表不存在")
            print("  請先執行 upgrade_database.py")
            conn.close()
            return
        
        conn.close()
        
        success_count = 0
        fail_count = 0
        skip_count = 0
        
        current_date = datetime.now()
        
        for i in range(days * 2):  # 多跑一些天數以應對假日
            if success_count >= days:
                break
            
            check_date = current_date - timedelta(days=i)
            
            # 跳過週末
            if check_date.weekday() >= 5:
                continue
            
            date_str = check_date.strftime('%Y/%m/%d')
            date_db = check_date.strftime('%Y%m%d')
            
            # 檢查是否已有數據
            if self._has_data(date_db):
                print(f"[{date_str}] ⏭️  已有數據，跳過")
                skip_count += 1
                continue
            
            # 收集數據
            print(f"\n[{date_str}] 收集中...", end=" ")
            
            try:
                result = self.scraper.get_retail_ratio(
                    date=date_str,
                    commodity_id='MXF',
                    debug=False
                )
                
                if result and result['total_oi'] > 0:
                    self._save_data(result)
                    print(f"✓ (散戶比: {result['retail_ratio']:.2f}%)")
                    success_count += 1
                else:
                    print("✗ (無數據)")
                    fail_count += 1
                
                # 延遲避免被封
                time.sleep(delay)
                
            except Exception as e:
                print(f"✗ 錯誤: {e}")
                fail_count += 1
        
        print(f"\n{'='*60}")
        print("收集完成!")
        print(f"  成功: {success_count} 天")
        print(f"  失敗: {fail_count} 天")
        print(f"  跳過: {skip_count} 天")
        print(f"{'='*60}\n")
        
        if success_count > 0:
            print("下一步:")
            print("1. 執行 python retail_ratio_collector_v2.py 產生 JSON")
            print("2. 檢查 data/retail_ratio_history.json")
            print("3. 更新前端讀取新格式")
    
    def _has_data(self, date_db):
        """檢查資料庫是否已有該日期的數據"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT COUNT(*) FROM mxf_futures_data WHERE date = ?',
            (date_db,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        
        return count > 0
    
    def _save_data(self, data):
        """儲存數據到資料庫"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO mxf_futures_data (
                    date, commodity_id, close_price, total_oi,
                    dealers_long, dealers_short, dealers_net,
                    trusts_long, trusts_short, trusts_net,
                    foreign_long, foreign_short, foreign_net,
                    institutional_net,
                    retail_long, retail_short, retail_net, retail_ratio,
                    timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['date'].replace('/', ''),
                data.get('commodity_id', 'MXF'),
                data.get('close_price', 0),
                data['total_oi'],
                data['dealers']['long'],
                data['dealers']['short'],
                data['dealers']['net'],
                data['trusts']['long'],
                data['trusts']['short'],
                data['trusts']['net'],
                data['foreign']['long'],
                data['foreign']['short'],
                data['foreign']['net'],
                data['institutional_net'],
                data['retail_long'],
                data['retail_short'],
                data['retail_net'],
                data['retail_ratio'],
                data['timestamp']
            ))
            
            conn.commit()
        except Exception as e:
            print(f"\n  ✗ 儲存失敗: {e}")
        finally:
            conn.close()

if __name__ == '__main__':
    print("\n選擇收集範圍:")
    print("1. 過去 30 天 (推薦)")
    print("2. 過去 60 天")
    print("3. 自訂天數")
    
    choice = input("\n請選擇 (Enter = 1): ").strip()
    
    if choice == "2":
        days = 60
    elif choice == "3":
        days = int(input("請輸入天數: "))
    else:
        days = 30
    
    collector = MXFHistoryCollector()
    collector.collect_history(days=days, delay=2)
