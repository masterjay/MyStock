#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股情緒指數計算程式 v2.0 (CNN-style)
加入價格動能、市場廣度、創新高低等指標
"""

class TWSentimentCalculator:
    """台股情緒指數計算器 - CNN Style"""
    
    def __init__(self):
        # 新權重分配 (價格類 45% + 機構類 55%)
        self.weights = {
            'momentum': 0.20,    # 價格動能 (vs MA)
            'breadth': 0.15,     # 市場廣度 (漲跌比)
            'strength': 0.10,    # 價格強度 (新高低)
            'margin': 0.15,      # 融資使用率
            'futures': 0.15,     # 期貨多空比
            'foreign': 0.10,     # 外資淨部位
            'pcr': 0.15          # Put/Call Ratio
        }
    
    def calculate_sentiment(self, margin_ratio=None, futures_ratio=None, 
                          foreign_net=0, pcr_volume=None,
                          momentum_data=None, breadth_data=None, strength_data=None):
        """
        計算台股情緒指數 (0-100) - CNN Style
        
        Args:
            margin_ratio: 融資使用率 (%)
            futures_ratio: 期貨多空比
            foreign_net: 外資淨部位 (口)
            pcr_volume: PCR 成交量比
            momentum_data: {'close': 收盤價, 'ma20': 20日均, 'ma60': 60日均}
            breadth_data: {'up_count': 上漲家數, 'down_count': 下跌家數, 'up_ratio': 上漲比率}
            strength_data: {'new_highs': 創新高, 'new_lows': 創新低}
        
        Returns:
            dict: 情緒指數結果
        """
        components = {}
        total_weight = 0
        weighted_score = 0
        
        # === 價格類指標 (45%) ===
        
        # 1. 價格動能 (20%)
        if momentum_data and momentum_data.get('ma20'):
            score = self._calculate_momentum_score(momentum_data)
            components['momentum'] = {'score': int(score), 'weight': self.weights['momentum'], 'desc': '價格動能'}
            weighted_score += score * self.weights['momentum']
            total_weight += self.weights['momentum']
        
        # 2. 市場廣度 (15%)
        if breadth_data and breadth_data.get('up_ratio') is not None:
            score = self._calculate_breadth_score(breadth_data)
            components['breadth'] = {'score': int(score), 'weight': self.weights['breadth'], 'desc': '市場廣度'}
            weighted_score += score * self.weights['breadth']
            total_weight += self.weights['breadth']
        
        # 3. 價格強度 (10%)
        if strength_data and (strength_data.get('new_highs') or strength_data.get('new_lows')):
            score = self._calculate_strength_score(strength_data)
            components['strength'] = {'score': int(score), 'weight': self.weights['strength'], 'desc': '新高低比'}
            weighted_score += score * self.weights['strength']
            total_weight += self.weights['strength']
        
        # === 機構類指標 (55%) ===
        
        # 4. 融資使用率 (15%)
        if margin_ratio is not None:
            score = self._calculate_margin_score(margin_ratio)
            components['margin'] = {'score': int(score), 'weight': self.weights['margin'], 'desc': '融資使用率'}
            weighted_score += score * self.weights['margin']
            total_weight += self.weights['margin']
        
        # 5. 期貨多空比 (15%)
        if futures_ratio is not None:
            score = self._calculate_futures_score(futures_ratio)
            components['futures'] = {'score': int(score), 'weight': self.weights['futures'], 'desc': '期貨多空比'}
            weighted_score += score * self.weights['futures']
            total_weight += self.weights['futures']
        
        # 6. 外資淨部位 (10%)
        if foreign_net is not None:
            score = self._calculate_foreign_score(foreign_net)
            components['foreign'] = {'score': int(score), 'weight': self.weights['foreign'], 'desc': '外資淨部位'}
            weighted_score += score * self.weights['foreign']
            total_weight += self.weights['foreign']
        
        # 7. PCR (15%)
        if pcr_volume is not None:
            score = self._calculate_pcr_score(pcr_volume)
            components['pcr'] = {'score': int(score), 'weight': self.weights['pcr'], 'desc': 'Put/Call比'}
            weighted_score += score * self.weights['pcr']
            total_weight += self.weights['pcr']
        
        # 計算加權平均 (根據可用指標重新正規化)
        if total_weight > 0:
            total_score = weighted_score / total_weight
        else:
            total_score = 50
        
        total_score = max(0, min(100, int(total_score)))
        
        return {
            'score': total_score,
            'rating': self._get_rating(total_score),
            'components': components,
            'available_weight': round(total_weight * 100, 1)
        }
    
    # === 價格類指標計算 ===
    
    def _calculate_momentum_score(self, data):
        """
        價格動能分數 (vs 20日/60日均線)
        高於均線 = 貪婪, 低於均線 = 恐慌
        """
        close = data['close']
        ma20 = data.get('ma20', close)
        ma60 = data.get('ma60', ma20)
        
        # 計算偏離度 (%)
        dev_20 = ((close - ma20) / ma20) * 100 if ma20 else 0
        dev_60 = ((close - ma60) / ma60) * 100 if ma60 else 0
        
        # 綜合偏離度 (短期權重高)
        combined_dev = dev_20 * 0.6 + dev_60 * 0.4
        
        # 轉換為 0-100 分數
        # ±5% 對應 0-100 的完整範圍
        score = 50 + combined_dev * 10
        return max(0, min(100, score))
    
    def _calculate_breadth_score(self, data):
        """
        市場廣度分數 (上漲家數比率)
        >60% 上漲 = 貪婪, <40% 上漲 = 恐慌
        """
        up_ratio = data.get('up_ratio', 50)
        
        # up_ratio 已經是 0-100 的百分比
        # 直接映射: 30% -> 0分, 50% -> 50分, 70% -> 100分
        score = (up_ratio - 30) / 40 * 100
        return max(0, min(100, score))
    
    def _calculate_strength_score(self, data):
        """
        價格強度分數 (創新高 vs 創新低)
        新高多 = 貪婪, 新低多 = 恐慌
        """
        new_highs = data.get('new_highs', 0)
        new_lows = data.get('new_lows', 0)
        
        total = new_highs + new_lows
        if total == 0:
            return 50
        
        # 新高佔比
        high_ratio = new_highs / total
        
        # 映射到 0-100
        score = high_ratio * 100
        return max(0, min(100, score))
    
    # === 機構類指標計算 (保持原有邏輯) ===
    
    def _calculate_margin_score(self, ratio):
        """計算融資使用率分數"""
        # ratio 可能是小數 (0.59) 或百分比 (59.27)
        ratio_percent = ratio if ratio > 1 else ratio * 100
        
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
        # < -60000 = 0分 (極度恐慌)
        # -60000 ~ -30000 = 0-25分
        # -30000 ~ -10000 = 25-45分
        # -10000 ~ +10000 = 45-55分 (中性)
        # +10000 ~ +30000 = 55-75分
        # +30000 ~ +60000 = 75-100分
        # > +60000 = 100分 (極度貪婪)
        
        if net_position <= -60000:
            return 0
        elif net_position < -30000:
            # -60000 到 -30000 映射到 0-25
            return (net_position + 60000) / 30000 * 25
        elif net_position < -10000:
            # -30000 到 -10000 映射到 25-45
            return 25 + (net_position + 30000) / 20000 * 20
        elif net_position < 10000:
            # -10000 到 +10000 映射到 45-55
            return 45 + (net_position + 10000) / 20000 * 10
        elif net_position < 30000:
            # +10000 到 +30000 映射到 55-75
            return 55 + (net_position - 10000) / 20000 * 20
        elif net_position < 60000:
            # +30000 到 +60000 映射到 75-100
            return 75 + (net_position - 30000) / 30000 * 25
        else:
            return 100
    
    def _calculate_pcr_score(self, pcr):
        """PCR 分數 (逆向指標)"""
        if pcr >= 1.5:
            return max(0, 25 - (pcr - 1.5) / 0.5 * 25)
        elif pcr >= 1.2:
            return 25 + (1.5 - pcr) / 0.3 * 20
        elif pcr >= 0.8:
            return 45 + (1.2 - pcr) / 0.4 * 10
        elif pcr >= 0.6:
            return 55 + (0.8 - pcr) / 0.2 * 20
        else:
            return 75 + min((0.6 - pcr) / 0.2 * 25, 25)
    
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
            return '#FF4136'
        elif score <= 44:
            return '#FF851B'
        elif score <= 55:
            return '#FFDC00'
        elif score <= 75:
            return '#2ECC40'
        else:
            return '#01FF70'


if __name__ == '__main__':
    # 測試新版本
    calculator = TWSentimentCalculator()
    
    print("=" * 60)
    print("台股情緒指數 v2.0 (CNN-style) 測試")
    print("=" * 60)
    
    # 模擬今日數據
    result = calculator.calculate_sentiment(
        margin_ratio=0.57,
        futures_ratio=0.98,
        foreign_net=-23476,
        pcr_volume=0.85,
        momentum_data={'close': 23400, 'ma20': 23100, 'ma60': 22800},
        breadth_data={'up_count': 421, 'down_count': 552, 'up_ratio': 39.7},
        strength_data={'new_highs': 25, 'new_lows': 45}
    )
    
    print(f"\n📊 情緒指數: {result['score']} ({result['rating']})")
    print(f"   可用權重: {result['available_weight']}%")
    print("\n各項指標:")
    for key, comp in result['components'].items():
        print(f"   {comp['desc']}: {comp['score']}分 (權重 {comp['weight']*100:.0f}%)")
