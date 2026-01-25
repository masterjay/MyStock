"""
快速測試哪些日期有交易數據
"""
import requests
from datetime import datetime, timedelta

def test_date(date_str):
    """測試指定日期是否有數據"""
    url = f"https://www.twse.com.tw/rwd/zh/marginTrade/MI_MARGN"
    params = {
        'date': date_str,
        'selectType': 'MS',
        'response': 'json'
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('stat') == 'OK':
                return True
    except:
        pass
    
    return False

print("正在測試最近的交易日...")
print("="*50)

today = datetime(2025, 12, 26)
found_count = 0

for i in range(60):
    test_date = today - timedelta(days=i)
    
    # 跳過週末
    if test_date.weekday() >= 5:
        continue
    
    date_str = test_date.strftime('%Y%m%d')
    has_data = test_date(date_str)
    
    status = "✓ 有數據" if has_data else "✗ 無數據"
    print(f"{date_str} ({test_date.strftime('%m/%d %a')}) - {status}")
    
    if has_data:
        found_count += 1
        if found_count >= 5:  # 找到5個有數據的日期就停止
            print("\n找到最近的交易日了!")
            break

print("="*50)
print("測試完成!")
