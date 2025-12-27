"""
測試期交所是否支援歷史查詢
直接使用爬蟲模組
"""
import sys
sys.path.insert(0, '.')

from scraper_taifex import TAIFEXScraper

dates = [
    "2025/12/20",  # 上週五
    "2025/12/19",  # 上週四
    "2025/12/18",  # 上週三
    "2025/12/17",  # 上週二
    "2025/12/16",  # 上週一
    "2025/12/13",  # 更早
]

print("測試期交所歷史查詢支援")
print("="*60)

scraper = TAIFEXScraper()

for date in dates:
    print(f"\n查詢日期: {date}")
    print("-"*60)
    
    # 使用 debug 模式
    positions = scraper.get_institutional_positions(date, debug=False)
    
    if positions:
        print(f"自營商: 多={positions['dealers']['long']:,}, 空={positions['dealers']['short']:,}")
        print(f"投  信: 多={positions['trusts']['long']:,}, 空={positions['trusts']['short']:,}")
        print(f"外  資: 多={positions['foreign']['long']:,}, 空={positions['foreign']['short']:,}")
        
        # 計算外資淨部位
        foreign_net = positions['foreign']['long'] - positions['foreign']['short']
        print(f"→ 外資淨部位: {foreign_net:,}")
    else:
        print("✗ 無法取得數據")

print("\n" + "="*60)


