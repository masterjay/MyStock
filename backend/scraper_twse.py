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
        url = f"{self.base_url}/marginTrade/MI_MARGN"
        params = {
            'date': date,
            'selectType': 'MS',  # 整體市場
            'response': 'json'
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            
            if data['stat'] == 'OK':
                # 解析數據
                fields = data['fields']
                data_list = data['data']
                
                # 找到加權指數的融資數據
                margin_info = None
                for item in data_list:
                    if '融資' in item[0]:  # 第一欄是項目名稱
                        margin_info = dict(zip(fields, item))
                        break
                
                if margin_info:
                    return {
                        'date': date,
                        'margin_balance': margin_info.get('融資餘額(仟元)', '0').replace(',', ''),
                        'margin_purchase': margin_info.get('融資買進(仟元)', '0').replace(',', ''),
                        'margin_sale': margin_info.get('融資賣出(仟元)', '0').replace(',', ''),
                        'margin_redemption': margin_info.get('融資償還(仟元)', '0').replace(',', ''),
                        'timestamp': datetime.now().isoformat()
                    }
            
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
        
        url = f"{self.base_url}/afterTrading/MI_INDEX"
        params = {
            'date': date,
            'response': 'json'
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            
            if data['stat'] == 'OK':
                # 取得加權指數資料
                index_data = data['data1'][0]  # 第一筆是加權指數
                
                return {
                    'date': date,
                    'index_value': index_data[1].replace(',', ''),
                    'market_value': index_data[8].replace(',', ''),  # 市值(億)
                    'timestamp': datetime.now().isoformat()
                }
            
            return None
            
        except Exception as e:
            print(f"Error fetching market value: {e}")
            return None
    
    def calculate_margin_ratio(self, margin_data, market_data):
        """
        計算融資使用率
        """
        try:
            margin_balance = float(margin_data['margin_balance']) / 1000  # 轉成億
            market_value = float(market_data['market_value'])
            
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
