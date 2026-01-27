#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
散戶多空比歷史數據收集器
輸出最近30天的散戶多空比和台指期貨價格
"""
import sqlite3
import json
from datetime import datetime

def collect_retail_ratio_history():
    """收集散戶多空比歷史數據"""
    print("=== 收集散戶多空比歷史數據 ===")
    
    conn = sqlite3.connect('data/market_data.db')
    cursor = conn.cursor()
    
    # 查詢最近30天的數據（包含台指期貨未平倉量作為點數參考）
    cursor.execute("""
        SELECT date, retail_long, retail_short, retail_ratio, open_interest
        FROM futures_data
        WHERE retail_ratio IS NOT NULL
        ORDER BY date DESC
        LIMIT 30
    """)
    
    rows = cursor.fetchall()
    
    # 轉換為JSON格式
    history = []
    # 反轉順序（從舊到新）
    rows = list(reversed(rows))
    
    for row in rows:
        date, r_long, r_short, r_ratio, open_interest = row
        
        # 計算散戶淨多空百分比
        # 正值 = 偏多，負值 = 偏空
        if r_long + r_short > 0:
            net_pct = ((r_long - r_short) / (r_long + r_short)) * 100
        else:
            net_pct = 0
        
        history.append({
            'date': date,
            'retail_long': r_long,
            'retail_short': r_short,
            'retail_ratio': r_ratio,
            'net_pct': round(net_pct, 2),
            'futures_oi': open_interest  # 未平倉量作為參考
        })
    
    conn.close()
    
    # 輸出JSON
    output = {
        'updated_at': datetime.now().isoformat(),
        'history': history
    }
    
    with open('data/retail_ratio_history.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 已輸出 {len(history)} 筆數據到 data/retail_ratio_history.json")
    
    if history:
        latest = history[-1]
        print(f"\n最新數據 ({latest['date']}):")
        print(f"  多單: {latest['retail_long']:,}")
        print(f"  空單: {latest['retail_short']:,}")
        print(f"  多空比: {latest['retail_ratio']:.2f}")
        print(f"  淨多空: {latest['net_pct']:.1f}%")
        print(f"  期貨未平倉: {latest['futures_oi']:,}")
    
    return output

if __name__ == '__main__':
    collect_retail_ratio_history()
