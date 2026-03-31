#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
漲停跌停收集器
資料來源：證交所 https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL
"""
import requests
import sqlite3
from datetime import datetime
import json
import os

class LimitUpDownCollector:
    def __init__(self):
        self.base_url = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL"
        self.db_path = "data/market_data.db"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def fetch_limit_updown(self, date=None):
        """
        抓取漲停跌停名單
        date: 格式 'YYYYMMDD'，預設為今天
        """
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        
        params = {
            'date': date,
            'response': 'json'
        }
        
        try:
            print(f"📊 抓取漲停跌停名單 ({date})...")
            response = requests.get(self.base_url, params=params, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('stat') != 'OK':
                print(f"✗ API 回傳狀態異常: {data.get('stat')}")
                return None
            
            # 欄位: ['證券代號', '證券名稱', '成交股數', '成交金額', '開盤價', '最高價', '最低價', '收盤價', '漲跌價差', '成交筆數']
            limit_up = []
            limit_down = []
            
            for row in data.get('data', []):
                code = row[0]
                name = row[1]
                close = row[7]  # 收盤價
                change = row[8]  # 漲跌價差
                volume = row[2]  # 成交股數
                
                try:
                    # 移除特殊符號並計算漲跌幅
                    change_value = change.replace('X', '').replace('+', '').replace('-', '').replace(',', '')
                    if change_value and change_value != '0.00':
                        change_float = float(change_value)
                        close_float = float(close.replace(',', ''))
                        
                        # 計算昨日收盤價和漲跌幅
                        if change.startswith('-'):
                            yesterday = close_float + change_float
                            change_pct = -(change_float / yesterday * 100)
                        else:
                            yesterday = close_float - change_float
                            change_pct = change_float / yesterday * 100
                        
                        # 漲停標準：9.5% ~ 10.5% (排除異常股票)
                        if 9.5 <= change_pct <= 10.5:
                            limit_up.append({
                                'code': code,
                                'name': name,
                                'price': close_float,
                                'change': change,
                                'change_pct': round(change_pct, 2),
                                'volume': int(volume.replace(',', ''))
                            })
                        elif -10.5 <= change_pct <= -9.5:
                            limit_down.append({
                                'code': code,
                                'name': name,
                                'price': close_float,
                                'change': change,
                                'change_pct': round(change_pct, 2),
                                'volume': int(volume.replace(',', ''))
                            })
                except:
                    pass
            
            # 按漲跌幅排序
            limit_up.sort(key=lambda x: x['change_pct'], reverse=True)
            limit_down.sort(key=lambda x: x['change_pct'])
            
            result = {
                'date': date,
                'limit_up': limit_up,
                'limit_down': limit_down,
                'limit_up_count': len(limit_up),
                'limit_down_count': len(limit_down)
            }
            
            print(f"✓ 漲停: {len(limit_up)} 檔，跌停: {len(limit_down)} 檔")
            return result
            
        except requests.exceptions.RequestException as e:
            print(f"✗ 網路請求失敗: {e}")
            return None
        except Exception as e:
            print(f"✗ 資料解析失敗: {e}")
            return None
    
    def save_to_database(self, data):
        """儲存到資料庫"""
        if not data:
            return False
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 建立表格
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS limit_updown (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                code TEXT,
                name TEXT,
                price REAL,
                change TEXT,
                change_pct REAL,
                volume INTEGER,
                type TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, code, type)
            )
        """)
        
        # 刪除當日舊資料
        cursor.execute('DELETE FROM limit_updown WHERE date = ?', (data['date'],))
        
        # 插入漲停股
        for stock in data['limit_up']:
            cursor.execute("""
                INSERT INTO limit_updown (date, code, name, price, change, change_pct, volume, type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (data['date'], stock['code'], stock['name'], stock['price'], 
                  stock['change'], stock['change_pct'], stock['volume'], 'limit_up'))
        
        # 插入跌停股
        for stock in data['limit_down']:
            cursor.execute("""
                INSERT INTO limit_updown (date, code, name, price, change, change_pct, volume, type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (data['date'], stock['code'], stock['name'], stock['price'], 
                  stock['change'], stock['change_pct'], stock['volume'], 'limit_down'))
        
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
        
        # 查詢漲停股
        cursor.execute("""
            SELECT code, name, price, change, change_pct, volume
            FROM limit_updown 
            WHERE date = ? AND type = 'limit_up'
            ORDER BY change_pct DESC
        """, (date,))
        
        limit_up = []
        for row in cursor.fetchall():
            limit_up.append({
                'code': row[0],
                'name': row[1],
                'price': row[2],
                'change': row[3],
                'change_pct': row[4],
                'volume': row[5]
            })
        
        # 查詢跌停股
        cursor.execute("""
            SELECT code, name, price, change, change_pct, volume
            FROM limit_updown 
            WHERE date = ? AND type = 'limit_down'
            ORDER BY change_pct ASC
        """, (date,))
        
        limit_down = []
        for row in cursor.fetchall():
            limit_down.append({
                'code': row[0],
                'name': row[1],
                'price': row[2],
                'change': row[3],
                'change_pct': row[4],
                'volume': row[5]
            })
        
        conn.close()
        
        result = {
            'date': date,
            'limit_up': limit_up,
            'limit_down': limit_down,
            'limit_up_count': len(limit_up),
            'limit_down_count': len(limit_down)
        }
        
        # 確保 data 目錄存在
        os.makedirs('data', exist_ok=True)
        
        # 寫入 JSON 檔案
        output_path = 'data/limit_updown.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"✓ 已匯出到 {output_path}")
        return result

def main():
    collector = LimitUpDownCollector()
    
    # 抓取今日數據
    data = collector.fetch_limit_updown()
    
    if data:
        # 儲存到資料庫
        collector.save_to_database(data)
        
        # 匯出 JSON
        collector.export_to_json()
        
        # 顯示摘要
        print("\n" + "="*60)
        print("📊 漲停跌停統計")
        print("="*60)
        print(f"漲停: {data['limit_up_count']} 檔")
        if data['limit_up']:
            print("\n前10檔:")
            for stock in data['limit_up'][:10]:
                print(f"  {stock['code']} {stock['name']:<10} {stock['price']:<8.2f} {stock['change']:<10} +{stock['change_pct']:.2f}%")
        
        print(f"\n跌停: {data['limit_down_count']} 檔")
        if data['limit_down']:
            print("\n前10檔:")
            for stock in data['limit_down'][:10]:
                print(f"  {stock['code']} {stock['name']:<10} {stock['price']:<8.2f} {stock['change']:<10} {stock['change_pct']:.2f}%")
        print("="*60)

if __name__ == '__main__':
    main()
