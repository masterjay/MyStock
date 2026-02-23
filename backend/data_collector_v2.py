"""
主數據收集器 v2.0 - 整合所有數據源並存儲
新增: 同時收集 TX (大台) 和 MXF (微台) 期貨數據
"""
import json
import sqlite3
from datetime import datetime, timedelta
import schedule
import time
from pathlib import Path

from scraper_twse import TWSEScraper
from scraper_taifex import TAIFEXScraper  # 使用新版
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
        """初始化數據庫 - 更新版支援雙期貨資料源"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 融資數據表 (保持不變)
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
        
        # === 舊的期貨表 (TX 大台) - 保留向下相容 ===
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
                pcr_volume REAL,
                timestamp TEXT,
                UNIQUE(date)
            )
        ''')
        
        # === 新的微台指表 (MXF) ===
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mxf_futures_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                commodity_id TEXT DEFAULT 'MXF',
                close_price REAL,
                total_oi INTEGER,
                
                -- 法人部位
                dealers_long INTEGER,
                dealers_short INTEGER,
                dealers_net INTEGER,
                trusts_long INTEGER,
                trusts_short INTEGER,
                trusts_net INTEGER,
                foreign_long INTEGER,
                foreign_short INTEGER,
                foreign_net INTEGER,
                institutional_net INTEGER,
                
                -- 散戶部位
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
        print("✓ Database initialized (支援 TX + MXF 雙資料源)")
    
    def collect_daily_data(self, target_date=None):
        """收集指定日期的數據 - 同時收集 TX 和 MXF"""
        if target_date is None:
            target_date = self.get_last_trading_day()
        
        date_str = target_date.strftime('%Y%m%d')
        date_slash = target_date.strftime('%Y/%m/%d')
        
        print(f"\n{'='*60}")
        print(f"開始收集 {date_str} ({target_date.strftime('%Y-%m-%d %A')}) 的數據")
        print(f"{'='*60}")
        
        # 1. 收集融資數據
        print("\n[1/6] 抓取融資餘額...")
        margin_data = self.twse_scraper.get_margin_data(date_str)
        time.sleep(2)
        
        print("[2/6] 抓取市值資料...")
        market_data = self.twse_scraper.get_market_value(date_str)
        time.sleep(2)
        
        margin_result = None
        if margin_data and market_data:
            margin_result = self.twse_scraper.calculate_margin_ratio(margin_data, market_data)
            if margin_result:
                self.save_margin_data(margin_result, margin_data)
                print(f"✓ 融資使用率: {margin_result['margin_ratio']}%")
        
        # 2. 收集 TX 大台期貨 (保留舊邏輯)
        print("\n[3/6] 抓取 TX 台指期 (大台)...")
        tx_result = self._collect_tx_futures(date_slash)
        
        # 3. 收集 MXF 微台指期貨 (新增)
        print("\n[4/6] 抓取 MXF 微台指 (散戶指標)...")
        mxf_result = self._collect_mxf_futures(date_slash)
        
        # 4. 抓取選擇權 PCR
        print("\n[5/6] 抓取選擇權 PCR...")
        options_data = self.options_scraper.get_put_call_ratio(target_date)
        pcr_volume = None
        if options_data:
            pcr_volume = options_data['pcr_volume']
            print(f'✓ PCR: {pcr_volume:.2f}')
        else:
            print('✗ 無法取得 PCR 數據')
        
        # 5. 其他數據收集
        print("\n[6/6] 收集其他市場數據...")
        self._collect_additional_data()
        
        print(f"\n{'='*60}")
        print(f"數據收集完成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
        
        return {
            'margin': margin_result,
            'tx_futures': tx_result,
            'mxf_futures': mxf_result,
            'pcr': pcr_volume
        }
    
    def _collect_tx_futures(self, date_slash):
        """收集 TX 大台期貨數據 (舊邏輯保留)"""
        try:
            # 使用舊的方法 (您原本的 scraper_taifex.py 邏輯)
            # 這裡簡化處理，實際上您需要保留原本的 TX 爬蟲邏輯
            print("  ⚠ TX 大台數據收集需要您原本的爬蟲邏輯")
            print("  ⚠ 暫時跳過，稍後整合")
            return None
        except Exception as e:
            print(f"  ✗ TX 收集失敗: {e}")
            return None
    
    def _collect_mxf_futures(self, date_slash):
        """收集 MXF 微台指數據 (新增)"""
        try:
            result = self.taifex_scraper.get_retail_ratio(
                date=date_slash, 
                commodity_id='MXF', 
                debug=True
            )
            
            if result:
                self.save_mxf_data(result)
                print(f"  ✓ 微台指散戶多空比: {result['retail_ratio']:.2f}%")
                print(f"  ✓ 收盤價: {result['close_price']:,}")
                print(f"  ✓ 未平倉量: {result['total_oi']:,}")
                return result
            else:
                print("  ✗ 無法取得微台指數據")
                return None
        except Exception as e:
            print(f"  ✗ MXF 收集失敗: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def save_mxf_data(self, data):
        """儲存微台指數據到資料庫"""
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
            print(f"  ✓ 微台指數據已存入資料庫")
        except Exception as e:
            print(f"  ✗ 儲存微台指數據失敗: {e}")
            import traceback
            traceback.print_exc()
        finally:
            conn.close()
    
    def _collect_additional_data(self):
        """收集其他額外數據"""
        tasks = [
            ("周轉率", collect_turnover_data, analyze_and_export),
            ("商品期貨", collect_all_commodities, None),
            ("外資買賣超", collect_foreign_top_stocks, None),
            ("產業外資流向", collect_industry_foreign_flow, None),
        ]
        
        for name, func1, func2 in tasks:
            try:
                print(f"  • {name}...", end=" ")
                func1()
                if func2:
                    func2()
                print("✓")
            except Exception as e:
                print(f"✗ ({e})")
    
    def save_margin_data(self, margin_result, margin_data):
        """保存融資數據 (保持不變)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO margin_data 
            (date, margin_balance, market_value, margin_ratio, 
             margin_purchase, margin_sale, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            margin_result['date'],
            margin_result['margin_balance_billion'],
            margin_result['margin_limit_billion'],
            margin_result['margin_ratio'],
            margin_data.get('margin_purchase', 0),
            margin_data.get('margin_sale', 0),
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def get_last_trading_day(self):
        """取得最近的交易日"""
        today = datetime.now()
        
        # 如果是週末，回推到週五
        if today.weekday() == 5:  # 星期六
            return today - timedelta(days=1)
        elif today.weekday() == 6:  # 星期日
            return today - timedelta(days=2)
        
        # 如果是平日但時間早於收盤，使用前一個交易日
        if today.hour < 14:
            if today.weekday() == 0:  # 星期一
                return today - timedelta(days=3)
            else:
                return today - timedelta(days=1)
        
        return today
    
    def is_trading_day(self, date):
        """檢查是否為交易日"""
        # 簡單版本: 排除週末
        return date.weekday() < 5
    
    def has_data(self, date_str):
        """檢查資料庫中是否已有該日期的數據"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM mxf_futures_data WHERE date = ?', (date_str,))
        count = cursor.fetchone()[0]
        
        conn.close()
        return count > 0
    
    def get_latest_data(self):
        """獲取最新數據"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM margin_data ORDER BY date DESC LIMIT 1')
        margin = cursor.fetchone()
        
        cursor.execute('SELECT * FROM futures_data ORDER BY date DESC LIMIT 1')
        tx_futures = cursor.fetchone()
        
        cursor.execute('SELECT * FROM mxf_futures_data ORDER BY date DESC LIMIT 1')
        mxf_futures = cursor.fetchone()
        
        conn.close()
        
        return {
            'margin': margin,
            'tx_futures': tx_futures,
            'mxf_futures': mxf_futures
        }
    
    def export_to_json(self, output_dir='data'):
        """導出數據為 JSON 供前端使用 - 更新版包含 MXF"""
        Path(output_dir).mkdir(exist_ok=True)
        
        latest = self.get_latest_data()
        
        # 獲取 MXF 歷史數據 (30天)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT date, retail_ratio, retail_long, retail_short, 
                   close_price, total_oi, foreign_net
            FROM mxf_futures_data 
            ORDER BY date DESC LIMIT 30
        ''', )
        mxf_history = cursor.fetchall()
        
        # 獲取 TX 歷史數據 (30天) - 如果有的話
        cursor.execute('''
            SELECT date, retail_ratio, foreign_net
            FROM futures_data 
            ORDER BY date DESC LIMIT 30
        ''')
        tx_history = cursor.fetchall()
        
        conn.close()
        
        # 構建輸出
        export_data = {
            'latest': {
                'mxf_futures': self._format_mxf_latest(latest['mxf_futures']) if latest['mxf_futures'] else None,
                'tx_futures': self._format_tx_latest(latest['tx_futures']) if latest['tx_futures'] else None,
                'margin': self._format_margin_latest(latest['margin']) if latest['margin'] else None,
            },
            'history': {
                'mxf': [
                    {
                        'date': row[0],
                        'retail_ratio': row[1],
                        'retail_long': row[2],
                        'retail_short': row[3],
                        'close_price': row[4],
                        'total_oi': row[5],
                        'foreign_net': row[6]
                    }
                    for row in reversed(mxf_history)  # 從舊到新
                ],
                'tx': [
                    {
                        'date': row[0],
                        'retail_ratio': row[1],
                        'foreign_net': row[2]
                    }
                    for row in reversed(tx_history)
                ]
            },
            'updated_at': datetime.now().isoformat()
        }
        
        # 輸出 JSON
        with open(f'{output_dir}/futures_data.json', 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        print(f"✓ 期貨數據已導出至 {output_dir}/futures_data.json")
        
        if latest['mxf_futures']:
            mxf = self._format_mxf_latest(latest['mxf_futures'])
            print(f"  微台指 ({mxf['date']}): 散戶多空比 {mxf['retail_ratio']:.2f}%")
        
        return export_data
    
    def _format_mxf_latest(self, row):
        """格式化微台指最新數據"""
        if not row:
            return None
        return {
            'date': row[1],
            'close_price': row[3],
            'total_oi': row[4],
            'retail_long': row[15],
            'retail_short': row[16],
            'retail_net': row[17],
            'retail_ratio': row[18],
            'foreign_net': row[13],
        }
    
    def _format_tx_latest(self, row):
        """格式化 TX 最新數據"""
        if not row:
            return None
        return {
            'date': row[1],
            'retail_ratio': row[12] if len(row) > 12 else None,
            'foreign_net': row[6] if len(row) > 6 else None,
        }
    
    def _format_margin_latest(self, row):
        """格式化融資最新數據"""
        if not row:
            return None
        return {
            'date': row[1],
            'ratio': row[4],
            'balance': row[2],
        }

if __name__ == "__main__":
    collector = DataCollector()
    
    print("\n台股監控系統 v2.0 - 數據收集工具 (支援 TX + MXF)")
    print("="*60)
    
    # 測試收集
    result = collector.collect_daily_data()
    
    # 導出 JSON
    print("\n正在導出數據...")
    collector.export_to_json()
    
    print("\n✓ 完成!")
