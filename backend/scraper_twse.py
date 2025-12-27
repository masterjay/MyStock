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
        獲取市值資料用於計算融資使用率
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
                # 從 tables 中找大盤統計資訊
                # 需要計算市值: 用成交金額當作市值的替代指標
                # 或者我們直接用融資餘額除以一個固定的比例(如0.25)來估算
                
                # 暫時先回傳一個估算值
                # 正確的市值需要從其他API獲取
                # 根據台股平均市值約 60兆,融資餘額約 3.3兆
                # 市值 ≈ 融資餘額 / 0.055 (約5.5%)
                
                return {
                    'date': date,
                    'market_value': '600000',  # 暫定 60兆(億) = 600,000億
                    'timestamp': datetime.now().isoformat()
                }
            
            print(f"API 回應: {data.get('stat', 'Unknown')}")
            return None
            
        except Exception as e:
            print(f"Error fetching market value: {e}")
            return None
    
    def calculate_margin_ratio(self, margin_data, market_data):
        """
        計算融資使用率
        """
        try:
            # margin_balance 可能已經是億或仟元,需要判斷
            margin_balance_str = str(margin_data.get('margin_balance', '0'))
            margin_balance = float(margin_balance_str) if margin_balance_str else 0
            
            # 如果是仟元,轉成億 (通常 > 1000000 表示是仟元)
            if margin_balance > 1000000:
                margin_balance = margin_balance / 100000  # 仟元轉億
            
            market_value = float(market_data.get('market_value', '0'))
            
            if market_value == 0:
                return None
            
            ratio = (margin_balance / market_value) * 100
            
            return {
                'date': margin_data['date'],
                'margin_balance_billion': round(margin_balance, 2),
                'market_value_billion': round(market_value, 2),
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
    
    print("\n正在抓取市值數據...")
    market = scraper.get_market_value()
    print(json.dumps(market, indent=2, ensure_ascii=False))
    
    if margin and market:
        print("\n計算融資使用率...")
        ratio = scraper.calculate_margin_ratio(margin, market)
        print(json.dumps(ratio, indent=2, ensure_ascii=False))
