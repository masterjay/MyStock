#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
散戶多空比計算模組
透過「總部位 - 三大法人部位」計算散戶部位
"""

class RetailInvestorCalculator:
    """散戶投資人數據計算器"""
    
    def __init__(self):
        pass
    
    def calculate_retail_positions(self, futures_data):
        """
        計算散戶多空部位
        
        Args:
            futures_data: dict包含:
                - total_long: 總多單
                - total_short: 總空單
                - foreign_long: 外資多單
                - foreign_short: 外資空單
                - trust_long: 投信多單
                - trust_short: 投信空單
                - dealer_long: 自營商多單
                - dealer_short: 自營商空單
        
        Returns:
            dict: {
                'retail_long': 散戶多單,
                'retail_short': 散戶空單,
                'retail_net': 散戶淨部位,
                'retail_ratio': 散戶多空比,
                'institutional_long': 三大法人合計多單,
                'institutional_short': 三大法人合計空單,
                'institutional_net': 三大法人淨部位
            }
        """
        # 計算三大法人合計
        institutional_long = (
            futures_data.get('foreign_long', 0) +
            futures_data.get('trust_long', 0) +
            futures_data.get('dealer_long', 0)
        )
        
        institutional_short = (
            futures_data.get('foreign_short', 0) +
            futures_data.get('trust_short', 0) +
            futures_data.get('dealer_short', 0)
        )
        
        institutional_net = institutional_long - institutional_short
        
        # 計算散戶部位 (總部位 - 法人部位)
        total_long = futures_data.get('total_long', 0)
        total_short = futures_data.get('total_short', 0)
        
        retail_long = total_long - institutional_long
        retail_short = total_short - institutional_short
        retail_net = retail_long - retail_short
        
        # 計算散戶多空比
        if retail_short > 0:
            retail_ratio = retail_long / retail_short
        else:
            retail_ratio = 0
        
        result = {
            'retail_long': retail_long,
            'retail_short': retail_short,
            'retail_net': retail_net,
            'retail_ratio': round(retail_ratio, 2),
            'institutional_long': institutional_long,
            'institutional_short': institutional_short,
            'institutional_net': institutional_net
        }
        
        return result
    
    def interpret_retail_sentiment(self, retail_ratio):
        """
        解讀散戶情緒 (逆向指標!)
        
        散戶多空比越高 → 散戶過度樂觀 → 反而是賣出訊號
        散戶多空比越低 → 散戶過度悲觀 → 反而是買入訊號
        """
        if retail_ratio >= 1.5:
            return {
                'sentiment': '極度樂觀',
                'signal': '⚠️ 警戒',
                'interpretation': '散戶過度看多,可能接近高點',
                'action': '考慮減碼或獲利了結',
                'color': '#ff3366'
            }
        elif retail_ratio >= 1.2:
            return {
                'sentiment': '偏樂觀',
                'signal': '⚠️ 注意',
                'interpretation': '散戶偏多,需謹慎',
                'action': '避免追高',
                'color': '#ff9500'
            }
        elif retail_ratio >= 0.8:
            return {
                'sentiment': '中性',
                'signal': '➖ 觀望',
                'interpretation': '散戶多空平衡',
                'action': '持續觀察',
                'color': '#ffaa00'
            }
        elif retail_ratio >= 0.6:
            return {
                'sentiment': '偏悲觀',
                'signal': '✅ 機會',
                'interpretation': '散戶偏空,可能是機會',
                'action': '可考慮布局',
                'color': '#00ff88'
            }
        else:
            return {
                'sentiment': '極度悲觀',
                'signal': '✅✅ 黃金機會',
                'interpretation': '散戶過度看空,可能接近低點',
                'action': '積極布局好時機',
                'color': '#00d9ff'
            }


if __name__ == '__main__':
    # 測試
    calculator = RetailInvestorCalculator()
    
    # 測試案例 1: 當前數據 (假設)
    test_data = {
        'total_long': 150000,
        'total_short': 150000,
        'foreign_long': 50000,
        'foreign_short': 73476,  # 外資淨空 -23476
        'trust_long': 10000,
        'trust_short': 5000,     # 投信淨多 +5000
        'dealer_long': 15000,
        'dealer_short': 7000,    # 自營商淨多 +8000
    }
    
    result = calculator.calculate_retail_positions(test_data)
    
    print("=== 散戶部位計算 ===")
    print(f"散戶多單: {result['retail_long']:,}口")
    print(f"散戶空單: {result['retail_short']:,}口")
    print(f"散戶淨部位: {result['retail_net']:+,}口")
    print(f"散戶多空比: {result['retail_ratio']}")
    
    print(f"\n三大法人多單: {result['institutional_long']:,}口")
    print(f"三大法人空單: {result['institutional_short']:,}口")
    print(f"三大法人淨部位: {result['institutional_net']:+,}口")
    
    interpretation = calculator.interpret_retail_sentiment(result['retail_ratio'])
    print(f"\n=== 散戶情緒解讀 (逆向指標) ===")
    print(f"情緒: {interpretation['sentiment']}")
    print(f"訊號: {interpretation['signal']}")
    print(f"解讀: {interpretation['interpretation']}")
    print(f"建議: {interpretation['action']}")
