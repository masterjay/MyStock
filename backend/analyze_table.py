"""
簡單的期交所HTML表格分析工具
先把整個表格的原始資料都印出來
"""
import requests
from bs4 import BeautifulSoup

url = "https://www.taifex.com.tw/cht/3/futContractsDate"
params = {
    'queryStartDate': '2025/12/20',
    'queryEndDate': '2025/12/20',
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

print("正在抓取期交所資料...")
response = requests.get(url, params=params, headers=headers, timeout=30)

print(f"狀態碼: {response.status_code}\n")

soup = BeautifulSoup(response.text, 'lxml')

# 找所有表格
tables = soup.find_all('table')
print(f"找到 {len(tables)} 個表格\n")

# 分析第一個表格
if tables:
    table = tables[0]
    rows = table.find_all('tr')
    
    print(f"表格有 {len(rows)} 列\n")
    print("=" * 100)
    
    # 印出所有列的完整內容
    for i, row in enumerate(rows):
        cols = row.find_all(['td', 'th'])
        if len(cols) == 0:
            continue
        
        print(f"\n列 {i} ({len(cols)} 欄):")
        print("-" * 100)
        
        # 顯示每一欄的內容
        for j, col in enumerate(cols):
            text = col.get_text(strip=True)
            if text:  # 只顯示有內容的欄位
                print(f"  [{j:2d}] {text}")
        
        # 只顯示前 20 列,避免太長
        if i >= 20:
            print("\n... (後續省略)")
            break

print("\n" + "=" * 100)
print("\n請找出臺股期貨的三大法人在哪幾列,以及數據在哪些欄位")
