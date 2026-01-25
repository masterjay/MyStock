"""
測試證交所融資數據 API
"""
import requests
from datetime import datetime, timedelta

dates = [
    "20251226",  # 今天
    "20251225",  # 昨天
    "20251224",  # 前天
    "20251223",  # 三天前
    "20251220",  # 上週五
    "20251218",  # 上週三
]

print("測試多個日期的融資數據")
print("=" * 60)

for date in dates:
    url = "https://www.twse.com.tw/exchangeReport/MI_MARGN"
    params = {
        'response': 'json',
        'date': date,
        'selectType': 'MS'
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('stat') == 'OK' and data.get('tables'):
                # 嘗試找融資金額
                has_data = False
                for table in data.get('tables', []):
                    if table and 'data' in table:
                        for row in table.get('data', []):
                            if len(row) > 0 and '融資金額' in row[0]:
                                margin_balance = row[5] if len(row) > 5 else '?'
                                print(f"✓ {date}: 融資餘額 = {margin_balance} 仟元")
                                has_data = True
                                break
                    if has_data:
                        break
                
                if not has_data:
                    print(f"✗ {date}: {data.get('stat', 'Unknown')}")
            else:
                print(f"✗ {date}: {data.get('stat', 'Unknown')}")
        else:
            print(f"✗ {date}: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"✗ {date}: 錯誤 - {e}")

print("=" * 60)

