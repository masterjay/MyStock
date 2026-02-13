"""
台股股票主檔收集器
從證交所抓取完整的股票清單、產業分類、公司名稱
"""
import requests
import pandas as pd
import json
from datetime import datetime
import sqlite3

class StockMasterCollector:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def collect_all_stocks(self):
        """從證交所抓取完整股票清單"""
        print("\n=== 收集台股股票主檔 ===\n")
        
        # 證交所國際板 API
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        
        try:
            resp = requests.get(url, headers=self.headers, timeout=30)
            resp.encoding = 'big5'
            
            # 解析 HTML 表格
            dfs = pd.read_html(resp.text)
            
            if not dfs:
                print("✗ 無法解析資料")
                return None
            
            # 第一個表格通常是上市股票
            df = dfs[0]
            
            # 清理資料
            df.columns = ['stock_info', 'isin', 'listed_date', 'market', 'industry', 'cfi']
            
            # 分離股票代碼和名稱
            df[['stock_id', 'stock_name']] = df['stock_info'].str.split('　', n=1, expand=True)
            
            # 過濾出股票（排除 ETF、ETN 等）
            stocks = df[
                df['stock_id'].str.match(r'^\d{4}$') &  # 4位數字
                ~df['stock_name'].str.contains('ＥＴＦ|ＥＴＮ|期', na=False) &
                df['industry'].notna()
            ].copy()
            
            # 清理產業分類
            stocks['industry'] = stocks['industry'].str.strip()
            
            # 選擇需要的欄位
            stocks = stocks[['stock_id', 'stock_name', 'industry', 'market']].copy()
            
            print(f"✓ 已收集 {len(stocks)} 檔上市股票\n")
            
            # 收集上櫃股票
            url_otc = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
            resp_otc = requests.get(url_otc, headers=self.headers, timeout=30)
            resp_otc.encoding = 'big5'
            
            dfs_otc = pd.read_html(resp_otc.text)
            
            if dfs_otc:
                df_otc = dfs_otc[0]
                df_otc.columns = ['stock_info', 'isin', 'listed_date', 'market', 'industry', 'cfi']
                df_otc[['stock_id', 'stock_name']] = df_otc['stock_info'].str.split('　', n=1, expand=True)
                
                stocks_otc = df_otc[
                    df_otc['stock_id'].str.match(r'^\d{4}$') &
                    ~df_otc['stock_name'].str.contains('ＥＴＦ|ＥＴＮ|期', na=False) &
                    df_otc['industry'].notna()
                ].copy()
                
                stocks_otc['industry'] = stocks_otc['industry'].str.strip()
                stocks_otc = stocks_otc[['stock_id', 'stock_name', 'industry', 'market']].copy()
                
                print(f"✓ 已收集 {len(stocks_otc)} 檔上櫃股票\n")
                
                # 合併
                stocks = pd.concat([stocks, stocks_otc], ignore_index=True)
            
            print(f"✓ 總計 {len(stocks)} 檔股票")
            print(f"✓ 產業分類數: {stocks['industry'].nunique()} 個\n")
            
            # 顯示產業統計
            print("產業分布 (Top 10):")
            industry_counts = stocks['industry'].value_counts().head(10)
            for industry, count in industry_counts.items():
                print(f"  {industry}: {count} 檔")
            
            return stocks
            
        except Exception as e:
            print(f"✗ 錯誤: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def save_to_database(self, stocks):
        """儲存到資料庫"""
        if stocks is None or len(stocks) == 0:
            return
        
        conn = sqlite3.connect('data/market_data.db')
        cursor = conn.cursor()
        
        # 建立股票主檔表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_master (
                stock_id TEXT PRIMARY KEY,
                stock_name TEXT NOT NULL,
                industry TEXT,
                market TEXT,
                updated_at TEXT
            )
        ''')
        
        # 清空舊資料
        cursor.execute('DELETE FROM stock_master')
        
        # 插入新資料
        updated_at = datetime.now().isoformat()
        for _, row in stocks.iterrows():
            cursor.execute('''
                INSERT INTO stock_master (stock_id, stock_name, industry, market, updated_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                row['stock_id'],
                row['stock_name'],
                row['industry'],
                row['market'],
                updated_at
            ))
        
        conn.commit()
        conn.close()
        
        print(f"\n✓ 已儲存 {len(stocks)} 檔股票到資料庫")
    
    def export_to_json(self, stocks):
        """匯出為 JSON"""
        if stocks is None or len(stocks) == 0:
            return
        
        # 轉換為字典格式
        stock_dict = {}
        for _, row in stocks.iterrows():
            stock_dict[row['stock_id']] = {
                'name': row['stock_name'],
                'industry': row['industry'],
                'market': row['market']
            }
        
        # 產業對照表
        industries = {}
        for industry in stocks['industry'].unique():
            industry_stocks = stocks[stocks['industry'] == industry]['stock_id'].tolist()
            industries[industry] = industry_stocks
        
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
    collector = StockMasterCollector()
    
    # 收集股票資料
    stocks = collector.collect_all_stocks()
    
    if stocks is not None:
        # 儲存到資料庫
        collector.save_to_database(stocks)
        
        # 匯出 JSON
        collector.export_to_json(stocks)
        
        print("\n" + "="*60)
        print("✓ 股票主檔建立完成!")
        print("="*60)

