"""
期交所微台指散戶多空比數據爬蟲 - 最終修正版
直接用 BeautifulSoup 手動解析
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re

class TAIFEXScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        self.product_map = {
            'MXF': '微型臺指',
            'MTX': '小型臺指',
            'TX':  '臺股期貨',
        }
    
    def get_retail_ratio(self, date=None, commodity_id='MXF', debug=False):
        """計算散戶多空比"""
        if date is None:
            date = datetime.now().strftime('%Y/%m/%d')
        
        product_name = self.product_map.get(commodity_id, '微型臺指')
        
        if debug:
            print(f"\n=== {product_name}({commodity_id}) 散戶多空比 ({date}) ===")
        
        # 取得三大法人部位
        positions = self.get_institutional_positions(date, commodity_id, debug)
        
        if not positions:
            return None
        
        # 估算全市場 OI (法人約佔 25%)
        inst_total = (positions['dealers']['long'] + positions['dealers']['short'] +
                     positions['trusts']['long'] + positions['trusts']['short'] +
                     positions['foreign']['long'] + positions['foreign']['short'])
        
        estimated_total_oi = int(inst_total / 0.25)
        
        # 計算散戶部位
        inst_long = positions['dealers']['long'] + positions['trusts']['long'] + positions['foreign']['long']
        inst_short = positions['dealers']['short'] + positions['trusts']['short'] + positions['foreign']['short']
        
        retail_long = estimated_total_oi - inst_long
        retail_short = estimated_total_oi - inst_short
        retail_net = retail_long - retail_short
        retail_ratio = (retail_net / estimated_total_oi * 100) if estimated_total_oi > 0 else 0
        
        result = {
            'date': date,
            'commodity_id': commodity_id,
            'product_name': product_name,
            'close_price': 0,
            'total_oi': estimated_total_oi,
            'dealers': positions['dealers'],
            'trusts': positions['trusts'],
            'foreign': positions['foreign'],
            'institutional_net': inst_long - inst_short,
            'retail_long': retail_long,
            'retail_short': retail_short,
            'retail_net': retail_net,
            'retail_ratio': round(retail_ratio, 2),
            'timestamp': datetime.now().isoformat(),
        }
        
        if debug:
            print(f"\n{'='*50}")
            print(f"法人總口數: {inst_total:,}")
            print(f"估算全市場 OI: {estimated_total_oi:,}")
            print(f"散戶做多: {retail_long:,}")
            print(f"散戶做空: {retail_short:,}")
            print(f"★ 散戶多空比: {retail_ratio:.2f}%")
            print(f"{'='*50}")
        
        return result
    
    def get_institutional_positions(self, date=None, commodity_id='MXF', debug=False):
        """獲取三大法人未平倉部位"""
        if date is None:
            date = datetime.now().strftime('%Y/%m/%d')
        
        product_name = self.product_map.get(commodity_id, '微型臺指')
        url = "https://www.taifex.com.tw/cht/3/futContractsDate"
        params = {
            'queryStartDate': date,
            'queryEndDate': date,
        }
        
        try:
            resp = requests.get(url, params=params, headers=self.headers, timeout=30)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            tables = soup.find_all('table')
            
            if debug:
                print(f"\n[三大法人部位] 找到 {len(tables)} 個表格")
            
            result = {
                'dealers': {'long': 0, 'short': 0, 'net': 0},
                'trusts':  {'long': 0, 'short': 0, 'net': 0},
                'foreign': {'long': 0, 'short': 0, 'net': 0},
            }
            
            identity_map = {
                '自營商': 'dealers',
                '投信': 'trusts',
                '外資及陸資': 'foreign',
                '外資': 'foreign',
            }
            
            # 解析表格
            for table in tables:
                rows = table.find_all('tr')
                
                for row in rows:
                    text = row.get_text()
                    
                    if product_name not in text:
                        continue
                    
                    # 判斷身份
                    matched_identity = None
                    for key, value in identity_map.items():
                        if key in text:
                            matched_identity = value
                            break
                    
                    if not matched_identity:
                        continue
                    
                    # 提取數字
                    cells = row.find_all(['td', 'th'])
                    numbers = []
                    for cell in cells:
                        cell_text = cell.get_text(strip=True).replace(',', '').replace('，', '')
                        if cell_text and cell_text not in ['-', '']:
                            try:
                                numbers.append(int(float(cell_text)))
                            except:
                                pass
                    
                    # 解析未平倉數據
                    # numbers[7] = 未平倉多方口數
                    # numbers[9] = 未平倉空方口數
                    if len(numbers) >= 10:
                        oi_long = numbers[7]
                        oi_short = numbers[9]
                        oi_net = oi_long - oi_short
                        
                        result[matched_identity]['long'] = oi_long
                        result[matched_identity]['short'] = oi_short
                        result[matched_identity]['net'] = oi_net
                        
                        if debug:
                            print(f"  {matched_identity}: 多={oi_long:,}, 空={oi_short:,}, 淨={oi_net:,}")
            
            # 檢查是否有數據
            total = sum(v['long'] + v['short'] for v in result.values())
            if total == 0:
                return None
            
            return result
            
        except Exception as e:
            print(f"抓取三大法人部位失敗: {e}")
            if debug:
                import traceback
                traceback.print_exc()
            return None

if __name__ == '__main__':
    scraper = TAIFEXScraper()
    
    # 測試多個日期
    test_dates = ['2026/02/07', '2026/02/06', '2026/02/05']
    
    for date in test_dates:
        print(f"\n{'='*60}")
        result = scraper.get_retail_ratio(date, 'MXF', debug=True)
        
        if result:
            print(f"\n✅ {date} 成功!")
            break
        else:
            print(f"\n✗ {date} 失敗")

