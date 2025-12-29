"""
台股融資融券數據爬蟲
資料來源: 證券交易所
"""
import requests
import json
from datetime import datetime, timedelta
import time

class TWSEScraper:
    def __init__(self):
        self.base_url = "https://www.twse.com.tw/rwd/zh"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def get_margin_data(self, date=None):
        """
        獲取融資融券餘額數據
        date: 格式 'YYYYMMDD'，預設為今天
        """
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        
        # 證交所 API - 信用交易統計
        url = f"https://www.twse.com.tw/exchangeReport/MI_MARGN"
        params = {
            'response': 'json',
            'date': date,
            'selectType': 'MS'
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get('stat') == 'OK' and data.get('tables'):
                # 從 tables 中找到信用交易統計表
                for table in data.get('tables', []):
                    if not table or 'data' not in table:
                        continue
                    
                    fields = table.get('fields', [])
                    data_rows = table.get('data', [])
                    
                    # 找融資金額那一列
                    for row in data_rows:
                        if len(row) > 0 and '融資金額' in row[0]:
                            # row = ["融資金額(仟元)", "買進", "賣出", "償還", "前日餘額", "今日餘額"]
                            return {
                                'date': date,
                                'margin_balance': row[5].replace(',', '') if len(row) > 5 else '0',  # 今日餘額
                                'margin_purchase': row[1].replace(',', '') if len(row) > 1 else '0',  # 買進
                                'margin_sale': row[2].replace(',', '') if len(row) > 2 else '0',  # 賣出
                                'margin_redemption': row[3].replace(',', '') if len(row) > 3 else '0',  # 償還
                                'timestamp': datetime.now().isoformat()
                            }
            
            print(f"API 回應: {data.get('stat', 'Unknown')}")
            return None
            
        except Exception as e:
            print(f"Error fetching margin data: {e}")
            return None
    
    def get_market_value(self, date=None):
        """
        獲取融資限額資料用於計算融資使用率
        
        註: 融資使用率 = 融資餘額 / 融資限額
        不是 融資餘額 / 市值
        
        台股融資限額約為 6,000億 (會隨著市場調整)
        """
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        
        url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
        params = {
            'response': 'json',
            'date': date
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get('stat') == 'OK':
                # 融資限額約為市值的 10% 左右
                # 台股市值約 60兆,融資限額約 6,000億
                # 這裡使用固定值,實際應從證交所取得最新限額
                
                return {
                    'date': date,
                    'margin_limit': '6000',  # 融資限額 6,000億 (實際值應從API取得)
                    'timestamp': datetime.now().isoformat()
                }
            
            print(f"API 回應: {data.get('stat', 'Unknown')}")
            return None
            
        except Exception as e:
            print(f"Error fetching margin limit: {e}")
            return None
    
    def calculate_margin_ratio(self, margin_data, market_data):
        """
        計算融資使用率
        
        融資使用率 = (融資餘額 / 融資限額) × 100%
        
        範例:
        - 融資餘額: 3,400億
        - 融資限額: 6,000億
        - 使用率: 56.67%
        """
        try:
            # margin_balance 可能已經是億或仟元,需要判斷
            margin_balance_str = str(margin_data.get('margin_balance', '0'))
            margin_balance = float(margin_balance_str) if margin_balance_str else 0
            
            # 如果是仟元,轉成億 (通常 > 1000000 表示是仟元)
            if margin_balance > 1000000:
                margin_balance = margin_balance / 100000  # 仟元轉億
            
            # 使用融資限額而非市值
            margin_limit = float(market_data.get('margin_limit', '6000'))
            
            if margin_limit == 0:
                return None
            
            ratio = (margin_balance / margin_limit) * 100
            
            return {
                'date': margin_data['date'],
                'margin_balance_billion': round(margin_balance, 2),
                'margin_limit_billion': round(margin_limit, 2),
                'margin_ratio': round(ratio, 2),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            print(f"Error calculating ratio: {e}")
            return None

if __name__ == "__main__":
    scraper = TWSEScraper()
    
    # 測試抓取今日數據
    print("正在抓取融資數據...")
    margin = scraper.get_margin_data()
    print(json.dumps(margin, indent=2, ensure_ascii=False))
    
    time.sleep(3)  # 避免請求太快
    
    print("\n正在抓取融資限額...")
    market = scraper.get_market_value()
    print(json.dumps(market, indent=2, ensure_ascii=False))
    
    if margin and market:
        print("\n計算融資使用率...")
        ratio = scraper.calculate_margin_ratio(margin, market)
        print(json.dumps(ratio, indent=2, ensure_ascii=False))
        
        print(f"\n融資餘額: {ratio['margin_balance_billion']}億")
        print(f"融資限額: {ratio['margin_limit_billion']}億")
        print(f"使用率: {ratio['margin_ratio']}%")
