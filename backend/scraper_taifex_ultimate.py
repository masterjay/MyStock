"""
期交所微台指散戶多空比數據爬蟲 - 終極版
直接使用欄位索引，不轉換成數字陣列
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
        }
    
    def _to_int(self, text):
        """文字轉整數"""
        s = str(text).replace(',', '').replace('，', '').strip()
        if s in ('nan', '-', '', 'None'):
            return 0
        try:
            return int(float(s))
        except:
            return 0
    
    def get_retail_ratio(self, date=None, commodity_id='MXF', debug=False):
        """計算散戶多空比"""
        if date is None:
            date = datetime.now().strftime('%Y/%m/%d')
        
        product_name = self.product_map.get(commodity_id, '微型臺指')
        
        if debug:
            print(f"\n=== {product_name}({commodity_id}) 散戶多空比 ({date}) ===")
        
        positions = self.get_institutional_positions(date, commodity_id, debug)
        
        if not positions:
            return None
        
        inst_long = (positions['dealers']['long'] + 
                    positions['trusts']['long'] + 
                    positions['foreign']['long'])
        inst_short = (positions['dealers']['short'] + 
                     positions['trusts']['short'] + 
                     positions['foreign']['short'])
        
        inst_avg = (inst_long + inst_short) / 2
        estimated_total_oi = int(inst_avg / 0.25)
        
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
            print(f"自營商: 多={positions['dealers']['long']:,}, 空={positions['dealers']['short']:,}")
            print(f"投  信: 多={positions['trusts']['long']:,}, 空={positions['trusts']['short']:,}")
            print(f"外  資: 多={positions['foreign']['long']:,}, 空={positions['foreign']['short']:,}")
            print(f"法人合計: 多={inst_long:,}, 空={inst_short:,}")
            print(f"估算全市場 OI: {estimated_total_oi:,}")
            print(f"散戶做多: {retail_long:,}")
            print(f"散戶做空: {retail_short:,}")
            print(f"★ 散戶多空比: {retail_ratio:.2f}%")
            print(f"{'='*50}")
        
        return result
    
    def get_institutional_positions(self, date=None, commodity_id='MXF', debug=False):
        """獲取三大法人未平倉部位 - 直接用欄位索引"""
        if date is None:
            date = datetime.now().strftime('%Y/%m/%d')
        
        product_name = self.product_map.get(commodity_id, '微型臺指')
        url = "https://www.taifex.com.tw/cht/3/futContractsDate"
        params = {'queryStartDate': date, 'queryEndDate': date}
        
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
            
            for table in tables:
                rows = table.find_all('tr')
                
                # 找微型臺指
                mxf_idx = -1
                for idx, row in enumerate(rows):
                    if product_name in row.get_text():
                        mxf_idx = idx
                        break
                
                if mxf_idx == -1:
                    continue
                
                # 處理 3 行
                for offset in range(3):
                    row_idx = mxf_idx + offset
                    if row_idx >= len(rows):
                        break
                    
                    row = rows[row_idx]
                    cells = row.find_all(['td', 'th'])
                    
                    if offset == 0:
                        # 自營商: 15欄
                        identity = 'dealers'
                        if len(cells) >= 12:
                            oi_long = self._to_int(cells[9].get_text())
                            oi_short = self._to_int(cells[11].get_text())
                        else:
                            continue
                    else:
                        # 投信/外資: 13欄
                        if len(cells) < 10:
                            continue
                        
                        # 直接用欄位 [7] 和 [9]
                        oi_long = self._to_int(cells[7].get_text())
                        oi_short = self._to_int(cells[9].get_text())
                        
                        row_text = row.get_text()
                        if '投信' in row_text:
                            identity = 'trusts'
                        elif '外資' in row_text or '外陸資' in row_text:
                            identity = 'foreign'
                        else:
                            continue
                    
                    oi_net = oi_long - oi_short
                    
                    result[identity]['long'] = oi_long
                    result[identity]['short'] = oi_short
                    result[identity]['net'] = oi_net
                    
                    if debug:
                        print(f"  {identity}: 多={oi_long:,}, 空={oi_short:,}")
                
                if result['dealers']['long'] > 0:
                    break
            
            return result if sum(v['long'] + v['short'] for v in result.values()) > 0 else None
            
        except Exception as e:
            print(f"錯誤: {e}")
            if debug:
                import traceback
                traceback.print_exc()
            return None

if __name__ == '__main__':
    scraper = TAIFEXScraper()
    result = scraper.get_retail_ratio('2026/02/07', 'MXF', debug=True)

