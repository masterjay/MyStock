"""
期交所台指期多空比數據爬蟲
資料來源: 期貨交易所
"""
import requests
import json
from datetime import datetime, timedelta

class TAIFEXScraper:
    def __init__(self):
        self.base_url = "https://www.taifex.com.tw/cht/3"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def get_futures_oi(self, date=None):
        """
        獲取台指期未平倉量
        date: 格式 'YYYY/MM/DD'
        """
        if date is None:
            date = datetime.now().strftime('%Y/%m/%d')
        
        # 期交所 API - 各種期貨未平倉量
        url = "https://www.taifex.com.tw/cht/3/futContractsDateDown"
        params = {
            'down_type': '1',
            'queryStartDate': date,
            'queryEndDate': date,
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            
            # 找到台指期(TX)的數據
            tx_data = None
            for item in data.get('RptBody', []):
                if item.get('ContractCode') == 'TX':  # TX = 台指期
                    tx_data = item
                    break
            
            if tx_data:
                return {
                    'date': date,
                    'contract': 'TX',
                    'open_interest': tx_data.get('OpenInterest', '0').replace(',', ''),
                    'trading_volume': tx_data.get('TradingVolume', '0').replace(',', ''),
                    'settlement_price': tx_data.get('SettlementPrice', '0'),
                    'timestamp': datetime.now().isoformat()
                }
            
            return None
            
        except Exception as e:
            print(f"Error fetching futures OI: {e}")
            return None
    
    def get_institutional_positions(self, date=None):
        """
        獲取三大法人期貨留倉部位
        """
        if date is None:
            date = datetime.now().strftime('%Y/%m/%d')
        
        url = "https://www.taifex.com.tw/cht/3/futContractsDate"
        params = {
            'queryStartDate': date,
            'queryEndDate': date,
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            
            positions = {
                'date': date,
                'foreign': {'long': 0, 'short': 0, 'net': 0},
                'trust': {'long': 0, 'short': 0, 'net': 0},
                'dealer': {'long': 0, 'short': 0, 'net': 0},
                'timestamp': datetime.now().isoformat()
            }
            
            # 解析三大法人數據
            for item in data.get('RptBody', []):
                if item.get('ContractCode') == 'TX':
                    trader_type = item.get('TraderType', '')
                    
                    long_pos = int(item.get('LongOpenInterest', '0').replace(',', ''))
                    short_pos = int(item.get('ShortOpenInterest', '0').replace(',', ''))
                    net_pos = long_pos - short_pos
                    
                    if '外資' in trader_type:
                        positions['foreign'] = {
                            'long': long_pos,
                            'short': short_pos,
                            'net': net_pos
                        }
                    elif '投信' in trader_type:
                        positions['trust'] = {
                            'long': long_pos,
                            'short': short_pos,
                            'net': net_pos
                        }
                    elif '自營商' in trader_type:
                        positions['dealer'] = {
                            'long': long_pos,
                            'short': short_pos,
                            'net': net_pos
                        }
            
            return positions
            
        except Exception as e:
            print(f"Error fetching institutional positions: {e}")
            return None
    
    def calculate_long_short_ratio(self, institutional_data):
        """
        計算多空比
        """
        try:
            total_long = (institutional_data['foreign']['long'] + 
                         institutional_data['trust']['long'] + 
                         institutional_data['dealer']['long'])
            
            total_short = (institutional_data['foreign']['short'] + 
                          institutional_data['trust']['short'] + 
                          institutional_data['dealer']['short'])
            
            if total_short == 0:
                ratio = 0
            else:
                ratio = total_long / total_short
            
            return {
                'date': institutional_data['date'],
                'total_long': total_long,
                'total_short': total_short,
                'long_short_ratio': round(ratio, 2),
                'net_position': total_long - total_short,
                'foreign_net': institutional_data['foreign']['net'],
                'trust_net': institutional_data['trust']['net'],
                'dealer_net': institutional_data['dealer']['net'],
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Error calculating ratio: {e}")
            return None

if __name__ == "__main__":
    scraper = TAIFEXScraper()
    
    # 測試抓取
    print("正在抓取台指期未平倉...")
    oi = scraper.get_futures_oi()
    if oi:
        print(json.dumps(oi, indent=2, ensure_ascii=False))
    
    print("\n正在抓取三大法人部位...")
    positions = scraper.get_institutional_positions()
    if positions:
        print(json.dumps(positions, indent=2, ensure_ascii=False))
        
        print("\n計算多空比...")
        ratio = scraper.calculate_long_short_ratio(positions)
        print(json.dumps(ratio, indent=2, ensure_ascii=False))
