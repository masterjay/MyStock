#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三大法人買賣金額收集器
資料來源：證交所 https://www.twse.com.tw/rwd/zh/fund/BFI82U
"""
import requests
import sqlite3
from datetime import datetime
import json
import os

class InstitutionalMoneyCollector:
    def __init__(self):
        self.base_url = "https://www.twse.com.tw/rwd/zh/fund/BFI82U"
        self.db_path = "data/market_data.db"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def fetch_institutional_money(self, date=None):
        """
        抓取三大法人買賣金額
        date: 格式 'YYYYMMDD'，預設為今天
        """
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        
        params = {
            'dayDate': date,
            'type': 'day',
            'response': 'json'
        }
        
        try:
            print(f"📊 抓取三大法人買賣金額 ({date})...")
            response = requests.get(self.base_url, params=params, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('stat') != 'OK':
                print(f"✗ API 回傳狀態異常: {data.get('stat')}")
                return None
            
            # data['data'] 格式：
            # [0] = ['自營商(自行買賣)', '買進金額', '賣出金額', '買賣差額']
            # [1] = ['自營商(避險)', ...]
            # [2] = ['投信', ...]
            # [3] = ['外資及陸資(不含外資自營商)', ...]
            # [4] = ['外資自營商', ...]
            # [5] = ['合計', ...]
            
            if not data.get('data') or len(data['data']) < 6:
                print(f"✗ 資料不足")
                return None
            
            raw_data = data['data']
            
            # 解析數據（金額單位：元，轉換成億）
            def to_billion(value_str):
                return float(value_str.replace(',', '')) / 100000000
            
            result = {
                'date': date,
                'dealer_self_buy': to_billion(raw_data[0][1]),
                'dealer_self_sell': to_billion(raw_data[0][2]),
                'dealer_self_diff': to_billion(raw_data[0][3]),
                
                'dealer_hedge_buy': to_billion(raw_data[1][1]),
                'dealer_hedge_sell': to_billion(raw_data[1][2]),
                'dealer_hedge_diff': to_billion(raw_data[1][3]),
                
                'trust_buy': to_billion(raw_data[2][1]),
                'trust_sell': to_billion(raw_data[2][2]),
                'trust_diff': to_billion(raw_data[2][3]),
                
                'foreign_buy': to_billion(raw_data[3][1]),
                'foreign_sell': to_billion(raw_data[3][2]),
                'foreign_diff': to_billion(raw_data[3][3]),
                
                'total_buy': to_billion(raw_data[5][1]),
                'total_sell': to_billion(raw_data[5][2]),
                'total_diff': to_billion(raw_data[5][3]),
            }
            
            # 抓取當日總成交金額來計算法人成交比重
            market_total = self.get_market_total(date)
            if market_total:
                result['market_total'] = market_total
                result['institutional_ratio'] = (result['total_buy'] / market_total * 100) if market_total > 0 else 0
            
            print(f"✓ 成功抓取三大法人數據")
            return result
            
        except requests.exceptions.RequestException as e:
            print(f"✗ 網路請求失敗: {e}")
            return None
        except (KeyError, ValueError, IndexError) as e:
            print(f"✗ 資料解析失敗: {e}")
            return None
    
    def get_market_total(self, date):
        """取得當日市場總成交金額（億元）"""
        try:
            # 從證交所每日市況 API 取得
            url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
            params = {'date': date, 'response': 'json'}
            
            response = requests.get(url, params=params, headers=self.headers, timeout=30)
            data = response.json()
            
            if data.get('stat') == 'OK':
                tables = data.get('tables', [])
                if len(tables) > 6:
                    # Table 6 是「大盤統計資訊」
                    table6 = tables[6]
                    for row in table6.get('data', []):
                        # 找「總計」行
                        if '總計' in row[0]:
                            total_str = row[1]  # 成交金額(元)
                            return float(total_str.replace(',', '')) / 100000000  # 轉億元
        except Exception as e:
            print(f"  取得市場總額失敗: {e}")
        return None
    
    def save_to_database(self, data):
        """儲存到資料庫"""
        if not data:
            return False
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 建立表格
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS institutional_money (
                date TEXT PRIMARY KEY,
                dealer_self_buy REAL,
                dealer_self_sell REAL,
                dealer_self_diff REAL,
                dealer_hedge_buy REAL,
                dealer_hedge_sell REAL,
                dealer_hedge_diff REAL,
                trust_buy REAL,
                trust_sell REAL,
                trust_diff REAL,
                foreign_buy REAL,
                foreign_sell REAL,
                foreign_diff REAL,
                total_buy REAL,
                total_sell REAL,
                total_diff REAL,
                market_total REAL,
                institutional_ratio REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 插入或更新數據
        cursor.execute('''
            INSERT OR REPLACE INTO institutional_money 
            (date, dealer_self_buy, dealer_self_sell, dealer_self_diff,
             dealer_hedge_buy, dealer_hedge_sell, dealer_hedge_diff,
             trust_buy, trust_sell, trust_diff,
             foreign_buy, foreign_sell, foreign_diff,
             total_buy, total_sell, total_diff,
             market_total, institutional_ratio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['date'],
            data['dealer_self_buy'], data['dealer_self_sell'], data['dealer_self_diff'],
            data['dealer_hedge_buy'], data['dealer_hedge_sell'], data['dealer_hedge_diff'],
            data['trust_buy'], data['trust_sell'], data['trust_diff'],
            data['foreign_buy'], data['foreign_sell'], data['foreign_diff'],
            data['total_buy'], data['total_sell'], data['total_diff'],
            data.get('market_total'), data.get('institutional_ratio')
        ))
        
        conn.commit()
        conn.close()
        print(f"✓ 數據已儲存到資料庫")
        return True
    
    def export_to_json(self, date=None):
        """匯出到 JSON 供前端使用"""
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM institutional_money 
            WHERE date = ?
        ''', (date,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            print(f"✗ 找不到 {date} 的數據")
            return None
        
        result = {
            'date': row[0],
            'data': [
                {'name': '自營商(自行買賣)', 'buy': row[1], 'sell': row[2], 'diff': row[3]},
                {'name': '自營商(避險)', 'buy': row[4], 'sell': row[5], 'diff': row[6]},
                {'name': '投信', 'buy': row[7], 'sell': row[8], 'diff': row[9]},
                {'name': '外資及陸資', 'buy': row[10], 'sell': row[11], 'diff': row[12]},
            ],
            'total': {'buy': row[13], 'sell': row[14], 'diff': row[15]},
            'market_total': row[16],
            'institutional_ratio': row[17]
        }
        
        # 確保 data 目錄存在
        os.makedirs('data', exist_ok=True)
        
        # 寫入 JSON 檔案
        output_path = 'data/institutional_money.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"✓ 已匯出到 {output_path}")
        return result

def main():
    collector = InstitutionalMoneyCollector()
    
    # 抓取今日數據
    data = collector.fetch_institutional_money()
    
    if data:
        # 儲存到資料庫
        collector.save_to_database(data)
        
        # 匯出 JSON
        collector.export_to_json()
        
        # 顯示摘要
        print("\n" + "="*60)
        print("📊 三大法人買賣金額統計")
        print("="*60)
        print(f"自營商(自行)：買 {data['dealer_self_buy']:.2f}億  賣 {data['dealer_self_sell']:.2f}億  差額 {data['dealer_self_diff']:+.2f}億")
        print(f"自營商(避險)：買 {data['dealer_hedge_buy']:.2f}億  賣 {data['dealer_hedge_sell']:.2f}億  差額 {data['dealer_hedge_diff']:+.2f}億")
        print(f"投信        ：買 {data['trust_buy']:.2f}億  賣 {data['trust_sell']:.2f}億  差額 {data['trust_diff']:+.2f}億")
        print(f"外資及陸資  ：買 {data['foreign_buy']:.2f}億  賣 {data['foreign_sell']:.2f}億  差額 {data['foreign_diff']:+.2f}億")
        print("="*60)
        print(f"合計        ：買 {data['total_buy']:.2f}億  賣 {data['total_sell']:.2f}億  差額 {data['total_diff']:+.2f}億")
        if data.get('institutional_ratio'):
            print(f"法人成交比重：{data['institutional_ratio']:.2f}%")
        print("="*60)

if __name__ == '__main__':
    main()
