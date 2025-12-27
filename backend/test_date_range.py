"""
測試期交所API的日期參數
使用實際爬蟲的解析邏輯
"""
import requests
from bs4 import BeautifulSoup

# 測試: 查詢12/16到12/20的數據
test_dates = [
    ("2025/12/16", "2025/12/20"),  # 一週範圍
    ("2025/12/18", "2025/12/20"),  # 三天範圍
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

print("測試期交所起迄日期查詢")
print("="*60)

for start_date, end_date in test_dates:
    print(f"\n查詢範圍: {start_date} ~ {end_date}")
    print("-"*60)
    
    url = "https://www.taifex.com.tw/cht/3/futContractsDate"
    params = {
        'queryStartDate': start_date,
        'queryEndDate': end_date,
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'lxml')
            table = soup.find('table', {'class': 'table_f'})
            
            if not table:
                # 嘗試找任何表格
                tables = soup.find_all('table')
                if tables:
                    table = tables[0]
            
            if table:
                rows = table.find_all('tr')
                print(f"找到表格,共 {len(rows)} 列")
                
                # 找臺股期貨的起始列 (跟實際爬蟲邏輯一樣)
                taiwan_futures_start = -1
                for i, row in enumerate(rows):
                    cols = row.find_all('td')
                    if len(cols) >= 3:
                        product = cols[1].get_text(strip=True)
                        if '臺股期貨' in product:
                            taiwan_futures_start = i
                            break
                
                if taiwan_futures_start >= 0:
                    print(f"臺股期貨從列 {taiwan_futures_start} 開始")
                    
                    # 解析三列 (自營商、投信、外資)
                    for offset in range(3):
                        row_idx = taiwan_futures_start + offset
                        if row_idx >= len(rows):
                            break
                        
                        cols = rows[row_idx].find_all('td')
                        
                        if offset == 0:
                            # 第一列: 自營商 (15欄)
                            if len(cols) >= 12:
                                trader = cols[2].get_text(strip=True)
                                long_oi = cols[9].get_text(strip=True).replace(',', '')
                                short_oi = cols[11].get_text(strip=True).replace(',', '')
                                print(f"  {trader}: 多={long_oi}, 空={short_oi}")
                        else:
                            # 第二、三列: 投信、外資 (13欄)
                            if len(cols) >= 10:
                                trader = cols[0].get_text(strip=True)
                                long_oi = cols[7].get_text(strip=True).replace(',', '')
                                short_oi = cols[9].get_text(strip=True).replace(',', '')
                                
                                if '外資' in trader:
                                    net = int(long_oi) - int(short_oi)
                                    print(f"  {trader}: 多={long_oi}, 空={short_oi}, 淨={net:,}")
                                else:
                                    print(f"  {trader}: 多={long_oi}, 空={short_oi}")
                else:
                    print("  ✗ 找不到臺股期貨")
            else:
                print("  ✗ 找不到表格")
        else:
            print(f"  ✗ HTTP {response.status_code}")
            
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")

print("\n" + "="*60)

