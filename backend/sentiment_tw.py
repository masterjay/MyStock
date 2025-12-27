#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股情緒指數計算程式
基於融資使用率、期貨多空比等指標
"""

class TWSentimentCalculator:
    """台股情緒指數計算器"""
    
    def __init__(self):
        pass
    
    def calculate_sentiment(self, margin_ratio, futures_ratio, foreign_net=0):
        """
        計算台股情緒指數 (0-100)
        
        Args:
            margin_ratio: 融資使用率 (%)
            futures_ratio: 期貨多空比
            foreign_net: 外資淨部位 (口)
        
        Returns:
            dict: {
                'score': int (0-100),
                'rating': str,
                'components': dict
            }
        """
        # 各指標權重
        margin_weight = 0.4
        futures_weight = 0.4
        foreign_weight = 0.2
        
        # 1. 融資使用率分數 (0-100)
        # 低融資 (<40%) = 恐慌, 高融資 (>60%) = 貪婪
        margin_score = self._calculate_margin_score(margin_ratio)
        
        # 2. 期貨多空比分數 (0-100)
        # 低比值 (<0.8) = 恐慌, 高比值 (>1.2) = 貪婪
        futures_score = self._calculate_futures_score(futures_ratio)
        
        # 3. 外資淨部位分數 (0-100)
        # 大量做空 (< -20000) = 恐慌, 大量做多 (> +20000) = 貪婪
        foreign_score = self._calculate_foreign_score(foreign_net)
        
        # 計算總分
        total_score = (
            margin_score * margin_weight +
            futures_score * futures_weight +
            foreign_score * foreign_weight
        )
        
        total_score = max(0, min(100, int(total_score)))
        
        result = {
            'score': total_score,
            'rating': self._get_rating(total_score),
            'components': {
                'margin': {
                    'score': int(margin_score),
                    'weight': margin_weight
                },
                'futures': {
                    'score': int(futures_score),
                    'weight': futures_weight
                },
                'foreign': {
                    'score': int(foreign_score),
                    'weight': foreign_weight
                }
            }
        }
        
        return result
    
    def _calculate_margin_score(self, ratio):
        """計算融資使用率分數"""
        # 輸入的 ratio 已經是百分比小數形式 (例如 0.57 代表 0.57%)
        # 需要轉換成真正的百分比數值
        ratio_percent = ratio * 100

        # 融資使用率越高 = 越貪婪
        # 40% 以下 = 極度恐慌 (0-25)
        # 40-50% = 恐慌 (25-45)
        # 50-55% = 中性 (45-55)
        # 55-60% = 貪婪 (55-75)
        # 60% 以上 = 極度貪婪 (75-100)

        if ratio_percent < 40:
            return ratio_percent / 40 * 25
        elif ratio_percent < 50:
            return 25 + (ratio_percent - 40) / 10 * 20
        elif ratio_percent < 55:
            return 45 + (ratio_percent - 50) / 5 * 10
        elif ratio_percent < 60:
            return 55 + (ratio_percent - 55) / 5 * 20
        else:
            return 75 + min((ratio_percent - 60) / 10 * 25, 25)
    
    def _calculate_futures_score(self, ratio):
        """計算期貨多空比分數"""
        # 多空比越高 = 越貪婪
        # < 0.7 = 極度恐慌 (0-25)
        # 0.7-0.9 = 恐慌 (25-45)
        # 0.9-1.1 = 中性 (45-55)
        # 1.1-1.3 = 貪婪 (55-75)
        # > 1.3 = 極度貪婪 (75-100)
        
        if ratio < 0.7:
            return ratio / 0.7 * 25
        elif ratio < 0.9:
            return 25 + (ratio - 0.7) / 0.2 * 20
        elif ratio < 1.1:
            return 45 + (ratio - 0.9) / 0.2 * 10
        elif ratio < 1.3:
            return 55 + (ratio - 1.1) / 0.2 * 20
        else:
            return 75 + min((ratio - 1.3) / 0.3 * 25, 25)
    
    def _calculate_foreign_score(self, net_position):
        """計算外資淨部位分數"""
        # 淨部位越多 (做多) = 越貪婪
        # < -30000 = 極度恐慌 (0-25)
        # -30000 to -10000 = 恐慌 (25-45)
        # -10000 to +10000 = 中性 (45-55)
        # +10000 to +30000 = 貪婪 (55-75)
        # > +30000 = 極度貪婪 (75-100)
        
        if net_position < -30000:
            return max(0, 25 + net_position / 30000 * 25)
        elif net_position < -10000:
            return 25 + (net_position + 30000) / 20000 * 20
        elif net_position < 10000:
            return 45 + (net_position + 10000) / 20000 * 10
        elif net_position < 30000:
            return 55 + (net_position - 10000) / 20000 * 20
        else:
            return 75 + min((net_position - 30000) / 30000 * 25, 25)
    
    def _get_rating(self, score):
        """根據分數返回評級"""
        if score <= 24:
            return '極度恐慌'
        elif score <= 44:
            return '恐慌'
        elif score <= 55:
            return '中性'
        elif score <= 75:
            return '貪婪'
        else:
            return '極度貪婪'
    
    def get_rating_color(self, score):
        """根據分數返回顏色代碼"""
        if score <= 24:
            return '#FF4136'  # 紅色
        elif score <= 44:
            return '#FF851B'  # 橙色
        elif score <= 55:
            return '#FFDC00'  # 黃色
        elif score <= 75:
            return '#2ECC40'  # 綠色
        else:
            return '#01FF70'  # 亮綠色


if __name__ == '__main__':
    # 測試
    calculator = TWSentimentCalculator()
    
    # 測試案例
    test_cases = [
        {'margin': 0.57, 'futures': 0.98, 'foreign': -23476, 'desc': '當前數據'},
        {'margin': 0.40, 'futures': 0.75, 'foreign': -35000, 'desc': '極度恐慌'},
        {'margin': 0.60, 'futures': 1.25, 'foreign': 25000, 'desc': '極度貪婪'},
    ]
    
    for case in test_cases:
        result = calculator.calculate_sentiment(
            case['margin'], 
            case['futures'], 
            case['foreign']
        )
        print(f"\n{case['desc']}:")
        print(f"  分數: {result['score']}")
        print(f"  評級: {result['rating']}")
        print(f"  融資分數: {result['components']['margin']['score']}")
        print(f"  期貨分數: {result['components']['futures']['score']}")
        print(f"  外資分數: {result['components']['foreign']['score']}")
