"""
測試期交所是否支援歷史日期查詢
"""
import requests
from bs4 import BeautifulSoup

dates = [
    "2025/12/26",  # 今天
    "2025/12/24",  # 兩天前
    "2025/12/20",  # 上週五
    "2025/12/18",  # 上週三
]

print("測試期交所不同日期的查詢")
print("=" * 60)

for date in dates:
    url = "https://www.taifex.com.tw/cht/3/futContractsDate"
    params = {
        'queryStartDate': date,
        'queryEndDate': date,
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'lxml')
            table = soup.find('table', {'class': 'table_f'})
            
            if table:
                rows = table.find_all('tr')
                
                # 找臺股期貨的外資數據
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 10:
                        product = cols[1].get_text(strip=True) if len(cols) > 1 else ''
                        if '臺股期貨' in product:
                            trader = cols[2].get_text(strip=True) if len(cols) > 2 else ''
                            if '外資' in trader:
                                long_oi = cols[7].get_text(strip=True).replace(',', '')
                                short_oi = cols[9].get_text(strip=True).replace(',', '')
                                net = int(long_oi) - int(short_oi) if long_oi and short_oi else 0
                                print(f"{date}: 外資淨部位 = {net:,} 口")
                                break
                else:
                    print(f"{date}: 找不到外資數據")
            else:
                print(f"{date}: 找不到表格")
        else:
            print(f"{date}: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"{date}: 錯誤 - {e}")

print("=" * 60)
