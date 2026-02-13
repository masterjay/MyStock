"""
期交所微台指散戶多空比數據爬蟲
資料來源: 臺灣期貨交易所 (TAIFEX)

需要兩個資料來源:
1. 三大法人期貨部位 (futContractsDate) → 法人未平倉多空口數
2. 每日行情表 (futDailyMarketReport) → 全市場未平倉量 (OI)

散戶多空比公式 (與 WantGoo 玩股網一致):
  散戶做多 = 全市場OI - (自營多 + 投信多 + 外資多)  [未平倉]
  散戶做空 = 全市場OI - (自營空 + 投信空 + 外資空)  [未平倉]
  散戶多空比(%) = (散戶做多 - 散戶做空) / 全市場OI × 100
"""
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import io
import time
import re


class TAIFEXScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
        }
        self.product_map = {
            'MXF': '微型臺指',
            'MTX': '小型臺指',
            'TX':  '臺股期貨',
        }

    # =========================================================================
    # 1. 三大法人「未平倉」部位
    # =========================================================================
    def get_institutional_positions(self, date=None, commodity_id='MXF', debug=False):
        """
        獲取三大法人「未平倉餘額」(不是交易口數)
        
        期交所 futContractsDate 表格有 15 欄 (multi-level header):
        [0] 序號
        [1] 商品名稱  
        [2] 身份別
        --- 交易口數與契約金額 ---
        [3] 多方口數  [4] 多方金額  [5] 空方口數  [6] 空方金額  [7] 淨額口數  [8] 淨額金額
        --- 未平倉餘額 ---
        [9] 多方口數  [10] 多方金額  [11] 空方口數  [12] 空方金額  [13] 淨額口數  [14] 淨額金額
        """
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
            
            dfs = pd.read_html(io.StringIO(resp.text))
            
            if debug:
                print(f"找到 {len(dfs)} 個表格")
            
            # 找包含法人資料的表格
            target_df = None
            for df in dfs:
                df_str = df.to_string()
                if '自營商' in df_str and product_name in df_str:
                    target_df = df
                    break
            
            if target_df is None:
                print(f"找不到含有 '{product_name}' 的表格")
                return None
            
            if debug:
                print(f"表格 shape: {target_df.shape}, 欄數: {target_df.shape[1]}")
            
            return self._parse_positions_by_column(target_df, product_name, debug)
            
        except Exception as e:
            print(f"抓取三大法人部位失敗: {e}")
            if debug:
                import traceback
                traceback.print_exc()
            return None

    def _parse_positions_by_column(self, df, product_name, debug=False):
        """
        用欄位位置直接取「未平倉餘額」數據
        
        已確認欄位結構 (15欄):
        col[9]  = 未平倉-多方口數
        col[11] = 未平倉-空方口數
        col[13] = 未平倉-多空淨額口數
        """
        result = {
            'dealers': {'long': 0, 'short': 0, 'net': 0},
            'trusts':  {'long': 0, 'short': 0, 'net': 0},
            'foreign': {'long': 0, 'short': 0, 'net': 0},
            'net_institutional': {'long': 0, 'short': 0, 'net': 0},
        }
        
        identity_map = {
            '自營商': 'dealers',
            '投信': 'trusts',
            '外資及陸資': 'foreign',
            '外資': 'foreign',
        }
        
        found_product = False
        parsed_count = 0
        ncols = df.shape[1]
        
        for idx in range(len(df)):
            row = df.iloc[idx]
            row_values = [str(v) for v in row.values]
            row_str = ' '.join(row_values)
            
            # 找到目標商品
            if product_name in row_str:
                found_product = True
            
            if not found_product:
                continue
            
            # 辨別身份
            matched_identity = None
            for key_str, identity_key in identity_map.items():
                if key_str in row_str:
                    matched_identity = identity_key
                    break
            
            if matched_identity is None:
                if parsed_count > 0:
                    for pname in self.product_map.values():
                        if pname in row_str and pname != product_name:
                            found_product = False
                            break
                continue
            
            # === 直接用欄位位置取「未平倉餘額」===
            if ncols >= 14:
                try:
                    oi_long  = self._to_int(row.iloc[9])   # 未平倉-多方口數
                    oi_short = self._to_int(row.iloc[11])   # 未平倉-空方口數
                    oi_net   = oi_long - oi_short
                    
                    result[matched_identity]['long'] = oi_long
                    result[matched_identity]['short'] = oi_short
                    result[matched_identity]['net'] = oi_net
                    parsed_count += 1
                    
                    if debug:
                        print(f"  {matched_identity} 未平倉: 多={oi_long:,}, 空={oi_short:,}, 淨={oi_net:,}")
                    
                except (ValueError, IndexError) as e:
                    if debug:
                        print(f"  {matched_identity} 解析失敗: {e}")
                    continue
            
            if parsed_count >= 3:
                break
        
        if parsed_count == 0:
            print(f"找不到 '{product_name}' 的未平倉數據")
            return None
        
        # 合計
        for key in ['long', 'short', 'net']:
            result['net_institutional'][key] = (
                result['dealers'][key] +
                result['trusts'][key] +
                result['foreign'][key]
            )
        
        return result

    # =========================================================================
    # 2. 全市場未平倉量 (OI)
    # =========================================================================
    def get_market_oi(self, date=None, commodity_id='MXF', debug=False):
        """
        獲取全市場未平倉量 + 收盤價
        嘗試多種方式: POST / GET / Excel頁面
        """
        if date is None:
            date = datetime.now().strftime('%Y/%m/%d')

        # === 方法1: POST to futDailyMarketReport ===
        url = "https://www.taifex.com.tw/cht/3/futDailyMarketReport"
        payload = {
            'queryStartDate': date,
            'queryEndDate': date,
            'commodity_id': commodity_id,
            'MarketCode': '0',
        }

        try:
            resp = requests.post(url, data=payload, headers=self.headers, timeout=30)
            resp.raise_for_status()
            result = self._parse_market_report(resp.text, date, commodity_id, debug)
            if result:
                return result
            if debug:
                print("  POST futDailyMarketReport 無結果")
        except Exception as e:
            if debug:
                print(f"  POST 失敗: {e}")

        # === 方法2: GET to futDailyMarketReport ===
        try:
            resp = requests.get(url, params=payload, headers=self.headers, timeout=30)
            resp.raise_for_status()
            result = self._parse_market_report(resp.text, date, commodity_id, debug)
            if result:
                return result
            if debug:
                print("  GET futDailyMarketReport 無結果")
        except Exception as e:
            if debug:
                print(f"  GET 失敗: {e}")

        # === 方法3: POST to futDailyMarketExcel ===
        try:
            url2 = "https://www.taifex.com.tw/cht/3/futDailyMarketExcel"
            resp = requests.post(url2, data=payload, headers=self.headers, timeout=30)
            resp.raise_for_status()
            result = self._parse_market_report(resp.text, date, commodity_id, debug)
            if result:
                return result
            if debug:
                print("  POST futDailyMarketExcel 無結果")
        except Exception as e:
            if debug:
                print(f"  Excel POST 失敗: {e}")

        # === 方法4: GET to futDailyMarketExcel ===
        try:
            resp = requests.get(url2, params=payload, headers=self.headers, timeout=30)
            resp.raise_for_status()
            result = self._parse_market_report(resp.text, date, commodity_id, debug)
            if result:
                return result
        except Exception as e:
            if debug:
                print(f"  Excel GET 失敗: {e}")

        print(f"[{date}] 所有方式都無法取得 {commodity_id} 全市場OI")
        return None

    def _parse_market_report(self, html_text, date, commodity_id, debug=False):
        """
        解析期貨每日行情表 HTML
        
        行情表欄位 (約14欄):
        契約 | 到期月份(週別) | 開盤價 | 最高價 | 最低價 | 收盤價 | 漲跌價 | 漲跌% |
        成交量(盤後) | 成交量(一般) | 成交量(合計) | 結算價 | 未沖銷契約數 | 最後交易日
        """
        try:
            dfs = pd.read_html(io.StringIO(html_text))
        except ValueError:
            if debug:
                print("  read_html: 找不到表格")
            return None
        
        if debug:
            print(f"  行情表共 {len(dfs)} 個表格")
        
        if not dfs:
            return None
        
        # 找含有「未沖銷」或行情數據的表格
        target_df = None
        for df in dfs:
            df_str = df.to_string()
            if '未沖銷' in df_str:
                target_df = df
                break
        
        if target_df is None:
            # 找最大表格
            target_df = max(dfs, key=lambda d: d.shape[0])
            if target_df.shape[0] < 3:
                if debug:
                    print("  表格太小，可能不是行情表")
                return None
        
        if debug:
            print(f"  目標表格: {target_df.shape}")
            for i in range(min(4, len(target_df))):
                vals = [str(v)[:12] for v in target_df.iloc[i].values[:8]]
                print(f"    列{i}: {vals}")
        
        total_oi = 0
        close_price = 0
        
        for idx in range(len(target_df)):
            row = target_df.iloc[idx]
            row_str = ' '.join([str(v) for v in row.values])
            
            # 跳過標題列、合計列
            if '契約' in row_str and ('到期' in row_str or '月份' in row_str):
                continue
            if '合計' in row_str:
                continue
            
            numbers = []
            for v in row.values:
                s = str(v).replace(',', '').strip()
                if s in ('-', 'nan', '', 'None'):
                    continue
                try:
                    numbers.append(float(s))
                except ValueError:
                    continue
            
            if len(numbers) < 5:
                continue
            
            # 收盤價 (10000~60000 範圍)
            if close_price == 0:
                for n in numbers[:6]:
                    if 10000 < n < 60000:
                        close_price = n
                        break
            
            # 未沖銷契約數 = 最後一個正整數
            last_positive_int = 0
            for n in reversed(numbers):
                if n > 0 and n == int(n):
                    last_positive_int = int(n)
                    break
            
            if last_positive_int > 0:
                total_oi += last_positive_int
                if debug:
                    print(f"    → OI +{last_positive_int:,}")
        
        if total_oi > 0:
            return {
                'date': date,
                'commodity_id': commodity_id,
                'total_oi': total_oi,
                'close_price': close_price,
            }
        return None

    # =========================================================================
    # 3. 核心: 計算散戶多空比
    # =========================================================================
    def get_retail_ratio(self, date=None, commodity_id='MXF', debug=False):
        """
        計算散戶多空比
        """
        if date is None:
            date = datetime.now().strftime('%Y/%m/%d')
        
        product_name = self.product_map.get(commodity_id, '微型臺指')

        if debug:
            print(f"\n=== {product_name}({commodity_id}) 散戶多空比 ({date}) ===")

        # Step 1: 三大法人未平倉部位
        if debug:
            print(f"\n[Step 1] 三大法人未平倉部位")
        positions = self.get_institutional_positions(date, commodity_id, debug)
        if not positions:
            return None

        # Step 2: 全市場未平倉量
        if debug:
            print(f"\n[Step 2] 全市場未平倉量")
        oi_data = self.get_market_oi(date, commodity_id, debug)
        if not oi_data:
            return None

        total_oi = oi_data['total_oi']
        close_price = oi_data['close_price']
        inst = positions['net_institutional']

        # Step 3: 計算
        retail_long  = total_oi - inst['long']
        retail_short = total_oi - inst['short']
        retail_net   = retail_long - retail_short
        retail_ratio = (retail_net / total_oi * 100) if total_oi > 0 else 0

        result = {
            'date': date,
            'close_price': close_price,
            'total_oi': total_oi,
            'retail_long': retail_long,
            'retail_short': retail_short,
            'retail_net': retail_net,
            'retail_ratio': round(retail_ratio, 2),
            'institutional_net': inst['net'],
            'dealers': positions['dealers'],
            'trusts': positions['trusts'],
            'foreign': positions['foreign'],
            'commodity_id': commodity_id,
            'product_name': product_name,
            'timestamp': datetime.now().isoformat(),
        }

        if debug:
            print(f"\n{'='*50}")
            print(f"日期: {date}  收盤: {close_price}")
            print(f"全市場OI: {total_oi:,}")
            print(f"自營商: 多={positions['dealers']['long']:,}  空={positions['dealers']['short']:,}")
            print(f"投信  : 多={positions['trusts']['long']:,}  空={positions['trusts']['short']:,}")
            print(f"外資  : 多={positions['foreign']['long']:,}  空={positions['foreign']['short']:,}")
            print(f"法人合計: 多={inst['long']:,}  空={inst['short']:,}")
            print(f"散戶做多: {retail_long:,}")
            print(f"散戶做空: {retail_short:,}")
            print(f"★ 散戶多空比: {retail_ratio:.2f}%")
            print(f"{'='*50}")

        return result

    # =========================================================================
    # 4. 批量歷史
    # =========================================================================
    def get_retail_ratio_history(self, days=30, commodity_id='MXF', debug=False):
        results = []
        current_date = datetime.now()
        attempts = 0
        max_attempts = days * 2 + 10
        
        while len(results) < days and attempts < max_attempts:
            check_date = current_date - timedelta(days=attempts)
            attempts += 1
            if check_date.weekday() >= 5:
                continue
            date_str = check_date.strftime('%Y/%m/%d')
            data = self.get_retail_ratio(date_str, commodity_id, debug=False)
            if data and data['total_oi'] > 0:
                results.append(data)
                if debug:
                    print(f"[{date_str}] ✓ {data['retail_ratio']}%")
            time.sleep(0.3)
        
        results.sort(key=lambda x: x['date'])
        return results

    # =========================================================================
    # 5. 舊介面相容
    # =========================================================================
    def get_futures_oi(self, date=None, debug=False):
        return self.get_retail_ratio(date, 'MXF', debug)

    # =========================================================================
    # 工具
    # =========================================================================
    def _to_int(self, val):
        s = str(val).replace(',', '').replace('，', '').strip()
        if s in ('nan', '-', '', 'None'):
            return 0
        return int(float(s))


# =========================================================================
# 測試
# =========================================================================
if __name__ == '__main__':
    scraper = TAIFEXScraper()
    
    print("=" * 60)
    print("微台指散戶多空比爬蟲 v2 - 測試")
    print("=" * 60)
    
    test_dates = ['2026/02/11', '2026/02/10', '2026/02/09']
    
    for test_date in test_dates:
        result = scraper.get_retail_ratio(test_date, 'MXF', debug=True)
        
        if result:
            print(f"\n結果: 散戶多={result['retail_long']:,}, "
                  f"散戶空={result['retail_short']:,}, "
                  f"多空比={result['retail_ratio']}%")
    
    print(f"\n{'='*60}")
    print("預期 (官方截圖):")
    print("  02/11: 散戶多=29462, 散戶空=39862, 多空比=-22.17%")
    print("  02/10: 散戶多=31431, 散戶空=45449, 多空比=-27.43%")
    print("  02/09: 散戶多=36202, 散戶空=41673, 多空比=-10.99%")
    print(f"{'='*60}")
