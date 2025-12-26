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
    
    def collect_daily_data(self):
        """收集當日所有數據"""
        date_str = datetime.now().strftime('%Y%m%d')
        print(f"\n{'='*50}")
        print(f"開始收集 {date_str} 的數據")
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
        date_slash = datetime.now().strftime('%Y/%m/%d')
        
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
                    'ratio': latest['margin'][3] if latest['margin'] else None,
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
    
    # 每天下午3點後執行
    schedule.every().day.at("15:30").do(collector.collect_daily_data)
    schedule.every().day.at("15:30").do(collector.export_to_json)
    
    print("排程已啟動，等待執行...")
    print("下次執行時間: 每日 15:30")
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    collector = DataCollector()
    
    # 立即執行一次
    print("開始收集數據...")
    result = collector.collect_daily_data()
    
    # 導出 JSON
    collector.export_to_json()
    
    # 顯示最新數據
    print("\n最新數據摘要:")
    print("-" * 50)
    if result['margin']:
        print(f"融資使用率: {result['margin']['margin_ratio']}%")
    if result['futures']:
        print(f"期貨多空比: {result['futures']['long_short_ratio']}")
        print(f"外資淨部位: {result['futures']['foreign_net']:,} 口")
    
    # 詢問是否啟動定時任務
    print("\n是否要啟動定時任務? (y/n)")
    # run_scheduler()  # 取消註解以啟動
