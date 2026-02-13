#!/usr/bin/env python3
"""
快速驗證腳本 - 在你的伺服器上跑這個來確認數據正確性
用法: python3 verify_scraper.py

會用 2026/02/11 的已知數據來驗證爬蟲是否正確
"""
from scraper_taifex import TAIFEXScraper
import sys

# 官方已知數據 (來自你的截圖)
EXPECTED = {
    '2026/02/11': {
        'close_price': 33691,
        'retail_long': 29462,
        'retail_short': 39862,
        'retail_ratio': -22.17,
    },
    '2026/02/10': {
        'close_price': 33307,
        'retail_long': 31431,
        'retail_short': 45449,
        'retail_ratio': -27.43,
    },
    '2026/02/09': {
        'close_price': 32651,
        'retail_long': 36202,
        'retail_short': 41673,
        'retail_ratio': -10.99,
    },
}

def verify():
    scraper = TAIFEXScraper()
    all_pass = True
    
    for date, expected in EXPECTED.items():
        print(f"\n{'='*60}")
        print(f"驗證 {date}")
        print(f"{'='*60}")
        
        # 先分開測試兩個資料來源
        print("\n[1] 三大法人部位:")
        positions = scraper.get_institutional_positions(date, 'MXF', debug=True)
        
        print("\n[2] 全市場未平倉量:")
        oi_data = scraper.get_market_oi(date, 'MXF', debug=True)
        
        if not positions or not oi_data:
            print(f"\n❌ {date}: 資料抓取失敗")
            if not positions:
                print("   → 三大法人部位失敗")
            if not oi_data:
                print("   → 全市場OI失敗")
            all_pass = False
            continue
        
        # 計算散戶數據
        total_oi = oi_data['total_oi']
        inst = positions['net_institutional']
        retail_long = total_oi - inst['long']
        retail_short = total_oi - inst['short']
        retail_ratio = (retail_long - retail_short) / total_oi * 100 if total_oi > 0 else 0
        
        # 比對
        print(f"\n--- 比對結果 ---")
        checks = [
            ('散戶做多', retail_long, expected['retail_long']),
            ('散戶做空', retail_short, expected['retail_short']),
            ('散戶多空比(%)', round(retail_ratio, 2), expected['retail_ratio']),
        ]
        
        for label, actual, exp in checks:
            match = '✓' if abs(actual - exp) < 1 else '✗'
            if match == '✗':
                all_pass = False
            print(f"  {match} {label}: 實際={actual}, 預期={exp}, 差={actual - exp}")
        
        print(f"  全市場OI: {total_oi:,}")
        print(f"  法人多: {inst['long']:,}, 法人空: {inst['short']:,}")
    
    print(f"\n{'='*60}")
    if all_pass:
        print("✅ 所有驗證通過！爬蟲數據與官方一致")
    else:
        print("⚠️  有數據不一致，請檢查 debug 輸出")
        print("\n常見問題排查:")
        print("1. 三大法人部位: 確認過濾到的是「微型臺指」而非「臺股期貨」")
        print("2. 全市場OI: 確認只取「一般交易時段」，不含盤後")
        print("3. OI 是否加總了所有到期月份")
        print("\n如果解析失敗，請用 debug=True 跑一次 get_institutional_positions")
        print("並把 HTML 表格結構貼給我，我幫你調整解析邏輯")
    print(f"{'='*60}")
    
    return all_pass

if __name__ == '__main__':
    success = verify()
    sys.exit(0 if success else 1)
