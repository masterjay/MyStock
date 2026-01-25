#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
美股 Fear & Greed Index 抓取程式
數據來源: CNN Money
"""

import requests
from datetime import datetime

class USFearGreedScraper:
    """美股恐慌貪婪指數抓取器"""
    
    def __init__(self):
        self.api_url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    
    def fetch_current_index(self):
        """
        抓取當前的 Fear & Greed Index
        
        Returns:
            dict: {
                'score': int,           # 0-100
                'rating': str,          # 'Extreme Fear', 'Fear', 'Neutral', 'Greed', 'Extreme Greed'
                'previous_close': float,
                'previous_week': float,
                'previous_month': float,
                'timestamp': str
            }
        """
        try:
            # 加入瀏覽器 Headers 避免被 CNN API 拒絕
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://www.cnn.com/',
                'Origin': 'https://www.cnn.com'
            }
            
            response = requests.get(self.api_url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # 提取最新數據
            fear_greed = data['fear_and_greed']
            
            result = {
                'score': fear_greed['score'],
                'rating': fear_greed['rating'],
                'previous_close': fear_greed.get('previous_close', 0),
                'previous_week': fear_greed.get('previous_1_week', 0),
                'previous_month': fear_greed.get('previous_1_month', 0),
                'timestamp': fear_greed.get('timestamp', datetime.now().isoformat())
            }
            
            print(f"✓ 美股 Fear & Greed Index: {result['score']} ({result['rating']})")
            return result
            
        except Exception as e:
            print(f"✗ 抓取美股指數失敗: {e}")
            return None
    
    def get_rating_text(self, score):
        """根據分數返回評級"""
        if score <= 24:
            return 'Extreme Fear'
        elif score <= 44:
            return 'Fear'
        elif score <= 55:
            return 'Neutral'
        elif score <= 75:
            return 'Greed'
        else:
            return 'Extreme Greed'
    
    def get_rating_color(self, score):
        """根據分數返回顏色代碼"""
        if score <= 24:
            return '#FF4136'  # 紅色 - Extreme Fear
        elif score <= 44:
            return '#FF851B'  # 橙色 - Fear
        elif score <= 55:
            return '#FFDC00'  # 黃色 - Neutral
        elif score <= 75:
            return '#2ECC40'  # 綠色 - Greed
        else:
            return '#01FF70'  # 亮綠色 - Extreme Greed


if __name__ == '__main__':
    # 測試
    scraper = USFearGreedScraper()
    data = scraper.fetch_current_index()
    
    if data:
        print(f"\n當前指數: {data['score']}")
        print(f"評級: {data['rating']}")
        print(f"前一日: {data['previous_close']}")
        print(f"一週前: {data['previous_week']}")
        print(f"一月前: {data['previous_month']}")
