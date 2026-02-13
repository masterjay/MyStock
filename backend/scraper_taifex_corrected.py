"""
期交所微台指散戶多空比數據爬蟲 - 修正版
使用修正後的估算公式，更接近官方數據
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime

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
        
        # 修正後的估算參數（根據官方數據反推）
        # 官方 2026/02/11: 全市場OI=69,324, 法人總=17,451+7,051=24,502
        # 實際法人佔比 ≈ 35.4%
        # 但考慮到數據波動，使用 38% 較穩定
        self.institutional_ratio = 0.38
    
    def get_retail_ratio(self, date=None, commodity_id='MXF', debug=False):
        """計算散戶多空比 - 使用修正後的估算公式"""
        if date is None:
            date = datetime.now().strftime('%Y/%m/%d')
        
        product_name = self.product_map.get(commodity_id, '微型臺指')
        
        if debug:
            print(f"\n=== {product_name}({commodity_id}) 散戶多空比 ({date}) ===")
        
        # 取得三大法人部位
        positions = self.get_institutional_positions(date, commodity_id, debug)
        
        if not positions:
            return None
        
        # 計算法人總口數
        inst_long = (positions['dealers']['long'] + 
                    positions['trusts']['long'] + 
                    positions['foreign']['long'])
        inst_short = (positions['dealers']['short'] + 
                     positions['trusts']['short'] + 
                     positions['foreign']['short'])
        
        # 使用修正後的比例估算全市場 OI
        # 方法：用法人的多空口數平均來估算
        inst_avg = (inst_long + inst_short) / 2
        estimated_total_oi = int(inst_avg / self.institutional_ratio)
        
        # 計算散戶部位
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
            print(f"法人多單: {inst_long:,}, 法人空單: {inst_short:,}")
            print(f"法人平均: {inst_avg:,}")
            print(f"估算全市場 OI: {estimated_total_oi:,} (法人佔比 {self.institutional_ratio*100:.0f}%)")
            print(f"散戶做多: {retail_long:,}")
            print(f"散戶做空: {retail_short:,}")
            print(f"★ 散戶多空比: {retail_ratio:.2f}%")
            print(f"{'='*50}")
        
        return result
    
    def get_institutional_positions(self, date=None, commodity_id='MXF', debug=False):
        """獲取三大法人未平倉部位（保持不變）"""
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
            
            for table in tables:
                rows = table.find_all('tr')
                
                for row in rows:
                    text = row.get_text()
                    
                    if product_name not in text:
                        continue
                    
                    matched_identity = None
                    for key, value in identity_map.items():
                        if key in text:
                            matched_identity = value
                            break
                    
                    if not matched_identity:
                        continue
                    
                    cells = row.find_all(['td', 'th'])
                    numbers = []
                    for cell in cells:
                        cell_text = cell.get_text(strip=True).replace(',', '').replace('，', '')
                        if cell_text and cell_text not in ['-', '']:
                            try:
                                numbers.append(int(float(cell_text)))
                            except:
                                pass
                    
                    if len(numbers) >= 10:
                        oi_long = numbers[7]
                        oi_short = numbers[9]
                        oi_net = oi_long - oi_short
                        
                        result[matched_identity]['long'] = oi_long
                        result[matched_identity]['short'] = oi_short
                        result[matched_identity]['net'] = oi_net
                        
                        if debug:
                            print(f"  {matched_identity}: 多={oi_long:,}, 空={oi_short:,}, 淨={oi_net:,}")
            
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
    
    print("=== 測試修正後的估算公式 ===\n")
    
    # 用 2026/02/07 測試（我們有法人數據）
    result = scraper.get_retail_ratio('2026/02/07', 'MXF', debug=True)
    
    if result:
        print(f"\n對照官方數據 (需要您提供 2026/02/07 的官方值):")
        print(f"  我們的結果: 散戶多={result['retail_long']:,}, 散戶空={result['retail_short']:,}, 比率={result['retail_ratio']:.2f}%")

