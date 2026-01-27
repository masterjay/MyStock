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
from scraper_options import OptionsScraper
from scraper_us_sentiment import USFearGreedScraper
from sentiment_tw import TWSentimentCalculator
from calculator_retail import RetailInvestorCalculator

from market_breadth_collector import get_market_momentum, get_market_breadth
from turnover_collector import collect_turnover_data
from turnover_analyzer import analyze_and_export
from commodities_collector import collect_all_commodities
from foreign_top_stocks_collector import collect_foreign_top_stocks
from industry_foreign_flow_collector import collect_industry_foreign_flow
from industry_heatmap_collector import collect_industry_heatmap

class DataCollector:
    def __init__(self, db_path='data/market_data.db'):
        self.db_path = db_path
        self.twse_scraper = TWSEScraper()
        self.taifex_scraper = TAIFEXScraper()
        self.us_scraper = USFearGreedScraper()
        self.tw_calculator = TWSentimentCalculator()
        self.retail_calculator = RetailInvestorCalculator()
        self.options_scraper = OptionsScraper()
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
                retail_long INTEGER,
                retail_short INTEGER,
                retail_net INTEGER,
                retail_ratio REAL,
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
                
                # 計算散戶多空比
                if 'total_long' in positions_data and 'total_short' in positions_data:
                    retail_data = self.retail_calculator.calculate_retail_positions({
                        'total_long': positions_data['total_long'],
                        'total_short': positions_data['total_short'],
                        'foreign_long': positions_data['foreign']['long'],
                        'foreign_short': positions_data['foreign']['short'],
                        'trust_long': positions_data['trusts']['long'],
                        'trust_short': positions_data['trusts']['short'],
                        'dealer_long': positions_data['dealers']['long'],
                        'dealer_short': positions_data['dealers']['short']
                    })
                    
                    # 加入散戶數據
                    futures_result['retail_long'] = retail_data['retail_long']
                    futures_result['retail_short'] = retail_data['retail_short']
                    futures_result['retail_net'] = retail_data['retail_net']
                    futures_result['retail_ratio'] = retail_data['retail_ratio']
                    
                    print(f"✓ 散戶多空比: {retail_data['retail_ratio']}")
                

                # [5/5] 抓取選擇權 PCR
                print('[5/5] 抓取選擇權 PCR...')
                options_data = self.options_scraper.get_put_call_ratio(target_date)
                if options_data:
                    pcr_volume = options_data['pcr_volume']
                    futures_result['pcr_volume'] = pcr_volume
                    print(f'✓ PCR: {pcr_volume:.2f}')
                else:
                    futures_result['pcr_volume'] = None
                    print('✗ 無法取得 PCR 數據')

                self.save_futures_data(futures_result)
                print(f"✓ 多空比: {futures_result['long_short_ratio']}")
                print(f"✓ 外資淨部位: {futures_result['foreign_net']:,} 口")
        
        print(f"\n{'='*50}")
        print(f"數據收集完成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*50}\n")
        
        # 收集周轉率數據
        print("\n[6/7] 收集周轉率數據...")
        try:
            collect_turnover_data()
            analyze_and_export()
            print("✓ 周轉率數據收集完成")
        except Exception as e:
            print(f"✗ 周轉率收集失敗: {e}")
        
        # 收集商品期貨數據
        print("\n[7/7] 收集商品期貨數據...")
        try:
            collect_all_commodities()
            print("✓ 商品期貨數據收集完成")
        except Exception as e:
            print(f"✗ 商品期貨收集失敗: {e}")
        
        
        # 收集外資買賣超排行
        print("\n[8/8] 收集外資買賣超排行...")
        try:
            collect_foreign_top_stocks()
            print("✓ 外資買賣超排行收集完成")
        except Exception as e:
            print(f"✗ 外資買賣超收集失敗: {e}")
        
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
                ratio_data.get('margin_limit_billion', ratio_data.get('market_value_billion', 6000)),  # 相容新舊欄位名
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
        """保存期貨數據(含散戶)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO futures_data 
                (date, open_interest, total_long, total_short, long_short_ratio,
                 foreign_net, trust_net, dealer_net, 
                 retail_long, retail_short, retail_net, retail_ratio, pcr_volume, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['date'].replace('/', ''),
                data['open_interest'],
                data['total_long'],
                data['total_short'],
                data['long_short_ratio'],
                data['foreign_net'],
                data['trust_net'],
                data['dealer_net'],
                data.get('retail_long', 0),
                data.get('retail_short', 0),
                data.get('retail_net', 0),
                data.get('retail_ratio', 0),
                data.get('pcr_volume', None),
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
        
        # 計算台股情緒指數 (v2.0 CNN-style)
        tw_sentiment = None
        
        # 取得價格類指標
        momentum_data = None
        breadth_data = None
        
        try:
            # 取得市場廣度數據
            breadth_raw = get_market_breadth()
            if breadth_raw:
                breadth_data = {
                    'up_count': breadth_raw['up_count'],
                    'down_count': breadth_raw['down_count'],
                    'up_ratio': breadth_raw['up_ratio']
                }
                # 用漲停/跌停當價格強度指標
                strength_data = {
                    'new_highs': breadth_raw.get('up_limit', 0),
                    'new_lows': breadth_raw.get('down_limit', 0)
                }
            
            # 取得動能數據 (從 market_breadth 表取歷史)
            momentum_raw = get_market_momentum()
            if momentum_raw:
                import sqlite3
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT taiex_close FROM market_breadth WHERE taiex_close IS NOT NULL ORDER BY date DESC LIMIT 60")
                closes = [row[0] for row in cursor.fetchall()]
                conn.close()
                
                if len(closes) >= 5:
                    ma20 = sum(closes[:min(20, len(closes))]) / min(20, len(closes))
                    ma60 = sum(closes) / len(closes)
                    momentum_data = {
                        'close': momentum_raw['close'],
                        'ma20': ma20,
                        'ma60': ma60,
                        'change': momentum_raw.get('change', 0)
                    }
                else:
                    # 數據不足時用漲跌幅估算
                    change = momentum_raw.get('change', 0)
                    close = momentum_raw['close']
                    # 假設昨收 = 今收 - 漲跌
                    yesterday = close - change
                    momentum_data = {
                        'close': close,
                        'ma20': yesterday,  # 暫用昨收代替
                        'ma60': yesterday,
                        'change': change
                    }
        except Exception as e:
            print(f"  ⚠ 價格指標取得失敗: {e}")
        
        if latest['margin'] and latest['futures']:
            margin_ratio = latest['margin'][4]  # margin_ratio
            futures_ratio = latest['futures'][5]  # long_short_ratio
            foreign_net = latest['futures'][6]  # foreign_net
            pcr_volume = latest['futures'][14] if len(latest['futures']) > 14 else None  # pcr_volume
            
            tw_sentiment = self.tw_calculator.calculate_sentiment(
                margin_ratio=margin_ratio, 
                futures_ratio=futures_ratio, 
                foreign_net=foreign_net,
                pcr_volume=pcr_volume,
                momentum_data=momentum_data,
                breadth_data=breadth_data,
                strength_data=strength_data
            )
        
        # 抓取美股情緒指數
        us_sentiment = self.us_scraper.fetch_current_index()
        
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
                    'trust_net': latest['futures'][7] if latest['futures'] and len(latest['futures']) > 7 else None,
                    'dealer_net': latest['futures'][8] if latest['futures'] and len(latest['futures']) > 8 else None,
                    'retail_long': latest['futures'][10] if latest['futures'] and len(latest['futures']) > 10 else None,
                    'retail_short': latest['futures'][11] if latest['futures'] and len(latest['futures']) > 11 else None,
                    'retail_net': latest['futures'][12] if latest['futures'] and len(latest['futures']) > 12 else None,
                    'retail_ratio': latest['futures'][13] if latest['futures'] and len(latest['futures']) > 13 else None,
                    'pcr_volume': latest['futures'][14] if latest['futures'] and len(latest['futures']) > 14 else None,
                }
            },
            'sentiment': {
                'taiwan': tw_sentiment,
                'us': us_sentiment
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
        if tw_sentiment:
            print(f"  台股情緒: {tw_sentiment['score']} - {tw_sentiment['rating']}")
        if us_sentiment:
            print(f"  美股情緒: {us_sentiment['score']} - {us_sentiment['rating']}")
        
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

