"""
主數據收集器 - 整合所有數據源並存儲
"""
import json
import sqlite3
from datetime import datetime, timedelta
import schedule
import time
from pathlib import Path

from scraper_twse import TWSEScraper
from scraper_taifex import TAIFEXScraper

class DataCollector:
    def __init__(self, db_path='market_data.db'):
        self.db_path = db_path
        self.twse_scraper = TWSEScraper()
        self.taifex_scraper = TAIFEXScraper()
        self.init_database()
    
    def init_database(self):
        """初始化數據庫"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 融資數據表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS margin_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                margin_balance REAL,
                market_value REAL,
                margin_ratio REAL,
                margin_purchase REAL,
                margin_sale REAL,
                timestamp TEXT,
                UNIQUE(date)
            )
        ''')
        
        # 期貨多空數據表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS futures_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                open_interest INTEGER,
                total_long INTEGER,
                total_short INTEGER,
                long_short_ratio REAL,
                foreign_net INTEGER,
                trust_net INTEGER,
                dealer_net INTEGER,
                timestamp TEXT,
                UNIQUE(date)
            )
        ''')
        
        conn.commit()
        conn.close()
        print("Database initialized successfully")
    
    def collect_daily_data(self, target_date=None):
        """收集指定日期的數據"""
        if target_date is None:
            target_date = self.get_last_trading_day()
        
        date_str = target_date.strftime('%Y%m%d')
        date_slash = target_date.strftime('%Y/%m/%d')
        
        print(f"\n{'='*50}")
        print(f"開始收集 {date_str} ({target_date.strftime('%Y-%m-%d %A')}) 的數據")
        print(f"{'='*50}")
        
        # 1. 收集融資數據
        print("\n[1/4] 抓取融資餘額...")
        margin_data = self.twse_scraper.get_margin_data(date_str)
        time.sleep(3)
        
        print("[2/4] 抓取市值資料...")
        market_data = self.twse_scraper.get_market_value(date_str)
        time.sleep(3)
        
        margin_result = None
        if margin_data and market_data:
            margin_result = self.twse_scraper.calculate_margin_ratio(margin_data, market_data)
            if margin_result:
                self.save_margin_data(margin_result, margin_data)
                print(f"✓ 融資使用率: {margin_result['margin_ratio']}%")
        
        # 2. 收集期貨數據
        print("\n[3/4] 抓取台指期未平倉...")
        oi_data = self.taifex_scraper.get_futures_oi(date_slash)
        time.sleep(3)
        
        print("[4/4] 抓取三大法人部位...")
        positions_data = self.taifex_scraper.get_institutional_positions(date_slash)
        
        futures_result = None
        if positions_data:
            futures_result = self.taifex_scraper.calculate_long_short_ratio(positions_data)
            if futures_result and oi_data:
                futures_result['open_interest'] = int(oi_data['open_interest'])
                self.save_futures_data(futures_result)
                print(f"✓ 多空比: {futures_result['long_short_ratio']}")
                print(f"✓ 外資淨部位: {futures_result['foreign_net']:,} 口")
        
        print(f"\n{'='*50}")
        print(f"數據收集完成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*50}\n")
        
        return {
            'margin': margin_result,
            'futures': futures_result
        }
    
    def collect_historical_data(self, days=30):
        """收集過去 N 天的歷史數據"""
        print(f"\n{'='*60}")
        print(f"開始收集過去 {days} 天的歷史數據")
        print(f"{'='*60}\n")
        
        success_count = 0
        fail_count = 0
        
        today = datetime.now()
        
        for i in range(days):
            target_date = today - timedelta(days=i)
            
            # 跳過週末
            if not self.is_trading_day(target_date):
                print(f"跳過 {target_date.strftime('%Y-%m-%d %A')} (週末)")
                continue
            
            # 檢查是否已經有這天的數據
            date_str = target_date.strftime('%Y%m%d')
            if self.has_data(date_str):
                print(f"已有 {date_str} 的數據，跳過")
                continue
            
            try:
                result = self.collect_daily_data(target_date)
                if result['margin'] or result['futures']:
                    success_count += 1
                    print(f"✓ {date_str} 數據收集成功")
                else:
                    fail_count += 1
                    print(f"✗ {date_str} 數據收集失敗")
                
                # 避免請求太頻繁
                time.sleep(5)
                
            except Exception as e:
                fail_count += 1
                print(f"✗ {date_str} 發生錯誤: {e}")
        
        print(f"\n{'='*60}")
        print(f"歷史數據收集完成")
        print(f"成功: {success_count} 天 | 失敗: {fail_count} 天")
        print(f"{'='*60}\n")
    
    def has_data(self, date_str):
        """檢查是否已有該日期的數據(融資或期貨)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM margin_data WHERE date = ?', (date_str,))
        margin_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM futures_data WHERE date = ?', (date_str,))
        futures_count = cursor.fetchone()[0]
        
        conn.close()
        
        # 只要有一個有數據就跳過(避免重複抓取)
        return margin_count > 0 or futures_count > 0
    
    def is_trading_day(self, date):
        """簡單判斷是否為交易日 (排除週六日)"""
        return date.weekday() < 5  # 0-4 是週一到週五
    
    def get_last_trading_day(self, from_date=None):
        """取得最近的交易日"""
        if from_date is None:
            from_date = datetime.now()
        
        current = from_date
        # 最多往回找 10 天
        for i in range(10):
            if self.is_trading_day(current):
                return current
            current = current - timedelta(days=1)
        
        return from_date  # 如果找不到就回傳原日期
    
    def save_margin_data(self, ratio_data, raw_data):
        """保存融資數據"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO margin_data 
                (date, margin_balance, market_value, margin_ratio, 
                 margin_purchase, margin_sale, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                ratio_data['date'],
                ratio_data['margin_balance_billion'],
                ratio_data['market_value_billion'],
                ratio_data['margin_ratio'],
                float(raw_data['margin_purchase']) / 1000,
                float(raw_data['margin_sale']) / 1000,
                ratio_data['timestamp']
            ))
            conn.commit()
            print("✓ 融資數據已保存")
        except Exception as e:
            print(f"✗ 保存融資數據失敗: {e}")
        finally:
            conn.close()
    
    def save_futures_data(self, data):
        """保存期貨數據"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO futures_data 
                (date, open_interest, total_long, total_short, long_short_ratio,
                 foreign_net, trust_net, dealer_net, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['date'].replace('/', ''),
                data['open_interest'],
                data['total_long'],
                data['total_short'],
                data['long_short_ratio'],
                data['foreign_net'],
                data['trust_net'],
                data['dealer_net'],
                data['timestamp']
            ))
            conn.commit()
            print("✓ 期貨數據已保存")
        except Exception as e:
            print(f"✗ 保存期貨數據失敗: {e}")
        finally:
            conn.close()
    
    def get_latest_data(self):
        """獲取最新數據"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 獲取最新融資數據
        cursor.execute('''
            SELECT * FROM margin_data 
            ORDER BY date DESC LIMIT 1
        ''')
        margin = cursor.fetchone()
        
        # 獲取最新期貨數據
        cursor.execute('''
            SELECT * FROM futures_data 
            ORDER BY date DESC LIMIT 1
        ''')
        futures = cursor.fetchone()
        
        conn.close()
        
        return {
            'margin': margin,
            'futures': futures
        }
    
    def get_historical_data(self, days=30):
        """獲取歷史數據"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 獲取歷史融資數據
        cursor.execute('''
            SELECT date, margin_ratio, margin_balance 
            FROM margin_data 
            ORDER BY date DESC LIMIT ?
        ''', (days,))
        margin_history = cursor.fetchall()
        
        # 獲取歷史期貨數據
        cursor.execute('''
            SELECT date, long_short_ratio, foreign_net 
            FROM futures_data 
            ORDER BY date DESC LIMIT ?
        ''', (days,))
        futures_history = cursor.fetchall()
        
        conn.close()
        
        return {
            'margin': margin_history,
            'futures': futures_history
        }
    
    def export_to_json(self, output_dir='data'):
        """導出數據為 JSON 供前端使用"""
        Path(output_dir).mkdir(exist_ok=True)
        
        # 最新數據
        latest = self.get_latest_data()
        
        # 歷史數據
        history = self.get_historical_data(60)  # 60天
        
        export_data = {
            'latest': {
                'margin': {
                    'date': latest['margin'][1] if latest['margin'] else None,
                    'ratio': latest['margin'][4] if latest['margin'] else None,  # margin_ratio 在第4欄
                    'balance': latest['margin'][2] if latest['margin'] else None,
                },
                'futures': {
                    'date': latest['futures'][1] if latest['futures'] else None,
                    'ratio': latest['futures'][5] if latest['futures'] else None,
                    'foreign_net': latest['futures'][6] if latest['futures'] else None,
                }
            },
            'history': {
                'margin': [
                    {'date': row[0], 'ratio': row[1], 'balance': row[2]}
                    for row in history['margin']
                ],
                'futures': [
                    {'date': row[0], 'ratio': row[1], 'foreign_net': row[2]}
                    for row in history['futures']
                ]
            },
            'updated_at': datetime.now().isoformat()
        }
        
        with open(f'{output_dir}/market_data.json', 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        print(f"✓ 數據已導出至 {output_dir}/market_data.json")
        return export_data

def run_scheduler():
    """定時執行任務"""
    collector = DataCollector()
    
    # 每天晚上8:30執行 (確保融資數據已公布)
    schedule.every().day.at("20:30").do(collector.collect_daily_data)
    schedule.every().day.at("20:30").do(collector.export_to_json)
    
    print("排程已啟動，等待執行...")
    print("下次執行時間: 每日 20:30 (融資數據公布後)")
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    collector = DataCollector()
    
    print("\n台股監控系統 - 數據收集工具")
    print("="*60)
    print("選擇執行模式:")
    print("1. 收集最近交易日的數據 (預設)")
    print("2. 收集過去 30 天的歷史數據")
    print("3. 收集過去 60 天的歷史數據")
    print("4. 啟動定時任務 (每天 20:30 自動執行)")
    print("="*60)
    
    choice = input("請選擇 (直接 Enter 使用選項 1): ").strip()
    
    if choice == "2":
        collector.collect_historical_data(30)
    elif choice == "3":
        collector.collect_historical_data(60)
    elif choice == "4":
        run_scheduler()
    else:
        # 預設: 收集最近交易日
        result = collector.collect_daily_data()
    
    # 導出 JSON
    print("\n正在導出數據...")
    collector.export_to_json()
    
    # 顯示最新數據
    print("\n最新數據摘要:")
    print("-" * 50)
    latest = collector.get_latest_data()
    if latest['margin']:
        print(f"融資使用率: {latest['margin'][3]}%")
    if latest['futures']:
        print(f"期貨多空比: {latest['futures'][5]}")
        print(f"外資淨部位: {latest['futures'][6]:,} 口")
    
    print("\n✓ 完成! 可以開啟網站查看數據")

