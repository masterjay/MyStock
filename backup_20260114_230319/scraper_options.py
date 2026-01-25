"""
台指選擇權 Put/Call Ratio 爬蟲
"""

from datetime import datetime

class OptionsScraper:
    def __init__(self):
        pass
    
    def get_put_call_ratio(self, target_date=None):
        """取得台指選擇權 Put/Call Ratio"""
        if target_date is None:
            target_date = datetime.now()
        
        print(f"[PCR] 查詢日期: {target_date.strftime('%Y-%m-%d')}")
        
        # 模擬數據 (實際應從期交所 API 抓取)
        result = {
            'date': target_date.strftime('%Y%m%d'),
            'put_volume': 150000,
            'call_volume': 120000,
            'pcr_volume': 1.25,
        }
        
        print(f"✓ PCR (Volume): {result['pcr_volume']:.2f}")
        return result
    
    def interpret_pcr(self, pcr_volume):
        """解讀 PCR"""
        if pcr_volume >= 1.5:
            return {'sentiment': '極度恐慌', 'signal': '超賣'}
        elif pcr_volume >= 1.2:
            return {'sentiment': '恐慌', 'signal': '偏空'}
        elif pcr_volume >= 0.8:
            return {'sentiment': '中性', 'signal': '中性'}
        elif pcr_volume >= 0.6:
            return {'sentiment': '貪婪', 'signal': '偏多'}
        else:
            return {'sentiment': '極度貪婪', 'signal': '超買'}

if __name__ == '__main__':
    scraper = OptionsScraper()
    result = scraper.get_put_call_ratio()
    print(f"日期: {result['date']}")
    print(f"PCR: {result['pcr_volume']}")
    interpretation = scraper.interpret_pcr(result['pcr_volume'])
    print(f"情緒: {interpretation['sentiment']}")
