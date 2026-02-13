"""
台股股票主檔收集器 v2
使用證交所 API 獲取更乾淨的資料
"""
import requests
import json
from datetime import datetime
import sqlite3

class StockMasterCollector:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def collect_listed_stocks(self):
        """收集上市股票"""
        print("收集上市股票...")
        
        # 證交所 API - 取得所有上市公司基本資料
        url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        
        try:
            resp = requests.get(url, headers=self.headers, timeout=30)
            data = resp.json()
            
            stocks = []
            for item in data:
                code = item.get('Code', '')
                name = item.get('Name', '')
                
                # 只要 4 碼數字的股票
                if len(code) == 4 and code.isdigit():
                    stocks.append({
                        'stock_id': code,
                        'stock_name': name,
                        'market': '上市'
                    })
            
            print(f"  ✓ 上市: {len(stocks)} 檔")
            return stocks
            
        except Exception as e:
            print(f"  ✗ 錯誤: {e}")
            return []
    
    def collect_otc_stocks(self):
        """收集上櫃股票"""
        print("收集上櫃股票...")
        
        # 櫃買中心 API
        url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"
        
        try:
            resp = requests.get(url, headers=self.headers, timeout=30)
            data = resp.json()
            
            stocks = []
            for item in data:
                code = item.get('SecuritiesCompanyCode', '')
                name = item.get('CompanyName', '')
                
                if len(code) == 4 and code.isdigit():
                    stocks.append({
                        'stock_id': code,
                        'stock_name': name,
                        'market': '上櫃'
                    })
            
            print(f"  ✓ 上櫃: {len(stocks)} 檔")
            return stocks
            
        except Exception as e:
            print(f"  ✗ 錯誤: {e}")
            return []
    
    def add_industry_mapping(self, stocks):
        """添加產業分類 - 使用內建對照表"""
        print("添加產業分類...")
        
        # 產業分類對照表（主要產業）
        industry_map = self._get_industry_map()
        
        for stock in stocks:
            code = stock['stock_id']
            # 預設為「其他」
            stock['industry'] = industry_map.get(code, '其他')
        
        # 統計
        industries = {}
        for stock in stocks:
            ind = stock['industry']
            industries[ind] = industries.get(ind, 0) + 1
        
        print(f"  ✓ 產業分類: {len(industries)} 個")
        return stocks
    
    def _get_industry_map(self):
        """產業分類對照表（簡化版）"""
        # 這裡可以從其他來源補充，或手動維護重要股票
        return {
            # 金融保險
            '2801': '銀行', '2809': '銀行', '2812': '銀行', '2834': '銀行',
            '2836': '銀行', '2838': '銀行', '2845': '銀行', '2847': '銀行',
            '2849': '銀行', '2850': '銀行', '2851': '銀行', '2852': '銀行',
            '2855': '銀行', '2867': '銀行', '2880': '銀行', '2881': '銀行',
            '2882': '銀行', '2883': '銀行', '2884': '銀行', '2885': '銀行',
            '2886': '銀行', '2887': '銀行', '2888': '銀行', '2889': '銀行',
            '2890': '銀行', '2891': '銀行', '2892': '銀行', '2897': '銀行',
            
            '2823': '保險', '2832': '保險', '2833': '保險', '2867': '保險',
            
            # 半導體
            '2330': '半導體', '2303': '半導體', '2454': '半導體', '2379': '半導體',
            '3034': '半導體', '3711': '半導體', '6669': '半導體', '6239': '半導體',
            '3443': '半導體', '2408': '半導體', '8046': '半導體',
            
            # 電子通路與零組件
            '2317': '電子通路', '3702': '電子通路', '2399': '電子零組件',
            
            # 光電
            '2409': '光電', '2448': '光電', '3481': '光電',
        }
    
    def save_to_database(self, stocks):
        """儲存到資料庫"""
        if not stocks:
            return
        
        conn = sqlite3.connect('data/market_data.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_master (
                stock_id TEXT PRIMARY KEY,
                stock_name TEXT NOT NULL,
                industry TEXT,
                market TEXT,
                updated_at TEXT
            )
        ''')
        
        cursor.execute('DELETE FROM stock_master')
        
        updated_at = datetime.now().isoformat()
        for stock in stocks:
            cursor.execute('''
                INSERT INTO stock_master (stock_id, stock_name, industry, market, updated_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                stock['stock_id'],
                stock['stock_name'],
                stock['industry'],
                stock['market'],
                updated_at
            ))
        
        conn.commit()
        conn.close()
        
        print(f"\n✓ 已儲存 {len(stocks)} 檔股票到資料庫")
    
    def export_to_json(self, stocks):
        """匯出為 JSON"""
        if not stocks:
            return
        
        stock_dict = {}
        industries = {}
        
        for stock in stocks:
            stock_dict[stock['stock_id']] = {
                'name': stock['stock_name'],
                'industry': stock['industry'],
                'market': stock['market']
            }
            
            ind = stock['industry']
            if ind not in industries:
                industries[ind] = []
            industries[ind].append(stock['stock_id'])
        
        output = {
            'updated_at': datetime.now().isoformat(),
            'total_stocks': len(stocks),
            'total_industries': len(industries),
            'stocks': stock_dict,
            'industries': industries
        }
        
        with open('data/stock_master.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        print(f"✓ 已匯出至 data/stock_master.json")

if __name__ == '__main__':
    print("\n=== 台股股票主檔收集器 v2 ===\n")
    
    collector = StockMasterCollector()
    
    # 收集上市+上櫃
    stocks = []
    stocks.extend(collector.collect_listed_stocks())
    stocks.extend(collector.collect_otc_stocks())
    
    print(f"\n總計: {len(stocks)} 檔股票")
    
    # 添加產業分類
    stocks = collector.add_industry_mapping(stocks)
    
    # 儲存
    collector.save_to_database(stocks)
    collector.export_to_json(stocks)
    
    print("\n" + "="*60)
    print("✓ 完成!")
    print("="*60)
    print("\n下一步: 修改 industry_foreign_flow_collector.py 使用此主檔")

