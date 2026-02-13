#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
散戶多空比歷史數據收集器 v2.0
同時輸出 TX (大台) 和 MXF (微台) 的散戶多空比
"""
import sqlite3
import json
from datetime import datetime

def collect_mxf_ratio_history(days=30):
    """收集微台指散戶多空比歷史數據"""
    print(f"=== 收集微台指 (MXF) 散戶多空比歷史 ({days}天) ===")
    
    conn = sqlite3.connect('data/market_data.db')
    cursor = conn.cursor()
    
    # 查詢 MXF 數據
    cursor.execute("""
        SELECT date, retail_long, retail_short, retail_ratio, 
               total_oi, close_price, foreign_net
        FROM mxf_futures_data
        WHERE retail_ratio IS NOT NULL
        ORDER BY date DESC
        LIMIT ?
    """, (days,))
    
    mxf_rows = cursor.fetchall()
    
    # 查詢 TX 數據 (如果有的話)
    cursor.execute("""
        SELECT date, retail_long, retail_short, retail_ratio, 
               open_interest, foreign_net
        FROM futures_data
        WHERE retail_ratio IS NOT NULL
        ORDER BY date DESC
        LIMIT ?
    """, (days,))
    
    tx_rows = cursor.fetchall()
    conn.close()
    
    # 轉換 MXF 為 JSON 格式
    mxf_history = []
    for row in reversed(mxf_rows):  # 從舊到新
        date, r_long, r_short, r_ratio, total_oi, close_price, foreign_net = row
        
        mxf_history.append({
            'date': date,
            'retail_long': r_long,
            'retail_short': r_short,
            'retail_ratio': round(r_ratio, 2),
            'total_oi': total_oi,
            'close_price': close_price,
            'foreign_net': foreign_net
        })
    
    # 轉換 TX 為 JSON 格式
    tx_history = []
    for row in reversed(tx_rows):
        date, r_long, r_short, r_ratio, oi, foreign_net = row
        
        tx_history.append({
            'date': date,
            'retail_long': r_long,
            'retail_short': r_short,
            'retail_ratio': round(r_ratio, 2),
            'open_interest': oi,
            'foreign_net': foreign_net
        })
    
    # 輸出 JSON
    output = {
        'updated_at': datetime.now().isoformat(),
        'mxf': {
            'name': '微型台指期貨 (MXF)',
            'description': '散戶參與度高，更能反映散戶情緒',
            'history': mxf_history
        },
        'tx': {
            'name': '台指期貨 (TX)',
            'description': '法人為主，反映機構態度',
            'history': tx_history
        }
    }
    
    with open('data/retail_ratio_history.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 已輸出數據:")
    print(f"  • MXF 微台指: {len(mxf_history)} 筆")
    print(f"  • TX 大台: {len(tx_history)} 筆")
    
    if mxf_history:
        latest = mxf_history[-1]
        print(f"\n最新 MXF 數據 ({latest['date']}):")
        print(f"  多單: {latest['retail_long']:,}")
        print(f"  空單: {latest['retail_short']:,}")
        print(f"  多空比: {latest['retail_ratio']:.2f}%")
        print(f"  收盤價: {latest['close_price']:,}")
        print(f"  未平倉: {latest['total_oi']:,}")
    
    return output

def collect_tx_ratio_history(days=30):
    """收集 TX 大台散戶多空比歷史數據 (舊版相容)"""
    print(f"=== 收集 TX (大台) 散戶多空比歷史 ({days}天) ===")
    
    conn = sqlite3.connect('data/market_data.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT date, retail_long, retail_short, retail_ratio, open_interest
        FROM futures_data
        WHERE retail_ratio IS NOT NULL
        ORDER BY date DESC
        LIMIT ?
    """, (days,))
    
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for row in reversed(rows):
        date, r_long, r_short, r_ratio, oi = row
        
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
            'futures_oi': oi
        })
    
    output = {
        'updated_at': datetime.now().isoformat(),
        'history': history
    }
    
    with open('data/tx_ratio_history.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 已輸出 {len(history)} 筆 TX 數據到 data/tx_ratio_history.json")
    
    return output

if __name__ == '__main__':
    # 收集 MXF (主要)
    collect_mxf_ratio_history(30)
    
    # 收集 TX (輔助)
    # collect_tx_ratio_history(30)
