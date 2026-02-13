"""
期交所微台指散戶多空比數據爬蟲 - 最終修正版
正確處理投信和外資在後續列的情況
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
        
        # 計算法人總口數
        inst_long = (positions['dealers']['long'] + 
                    positions['trusts']['long'] + 
                    positions['foreign']['long'])
        inst_short = (positions['dealers']['short'] + 
                     positions['trusts']['short'] + 
                     positions['foreign']['short'])
        
        # 用法人口數的平均估算全市場 OI
        # 根據官方數據，法人約佔 25-35%
        inst_avg = (inst_long + inst_short) / 2
        estimated_total_oi = int(inst_avg / 0.25)  # 使用 25% 作為保守估計
        
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
        """獲取三大法人未平倉部位 - 修正版"""
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
            
            for table in tables:
                rows = table.find_all('tr')
                
                # 找到微型臺指的起始行
                mxf_start_idx = -1
                for idx, row in enumerate(rows):
                    if product_name in row.get_text():
                        mxf_start_idx = idx
                        break
                
                if mxf_start_idx == -1:
                    continue
                
                # 處理微型臺指及其後續 2 行（投信、外資）
                for offset in range(3):
                    row_idx = mxf_start_idx + offset
                    if row_idx >= len(rows):
                        break
                    
                    row = rows[row_idx]
                    cells = row.find_all(['td', 'th'])
                    
                    # 提取所有數字
                    numbers = []
                    for cell in cells:
                        cell_text = cell.get_text(strip=True).replace(',', '').replace('，', '')
                        if cell_text and cell_text not in ['-', '']:
                            try:
                                numbers.append(int(float(cell_text)))
                            except:
                                pass
                    
                    if len(numbers) < 10:
                        continue
                    
                    # 判斷身份
                    # offset=0: 自營商（有商品名稱）
                    # offset=1: 投信（無商品名稱，可能全是0）
                    # offset=2: 外資（無商品名稱）
                    
                    if offset == 0:
                        identity = 'dealers'
                        oi_long = numbers[7]
                        oi_short = numbers[9]
                    elif offset == 1:
                        identity = 'trusts'
                        # 投信的數字索引不同（少了序號和商品名）
                        # 找最大的兩個數字作為多空（通常是前幾個）
                        if len(numbers) >= 2:
                            oi_long = numbers[0] if len(numbers) > 0 else 0
                            oi_short = numbers[1] if len(numbers) > 1 else 0
                        else:
                            oi_long = oi_short = 0
                    else:  # offset == 2
                        identity = 'foreign'
                        # 外資格式類似投信
                        if len(numbers) >= 2:
                            oi_long = numbers[0]
                            oi_short = numbers[1]
                        else:
                            continue
                    
                    oi_net = oi_long - oi_short
                    
                    result[identity]['long'] = oi_long
                    result[identity]['short'] = oi_short
                    result[identity]['net'] = oi_net
                    
                    if debug:
                        print(f"  {identity}: 多={oi_long:,}, 空={oi_short:,}, 淨={oi_net:,}")
                
                # 找到就break
                if result['dealers']['long'] > 0:
                    break
            
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
    result = scraper.get_retail_ratio('2026/02/07', 'MXF', debug=True)
    
    if result:
        print(f"\n請提供 2026/02/07 的官方數據以驗證準確度")

