#!/usr/bin/env python3
import json
import os

# 加载映射表
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAP_FILE = os.path.join(SCRIPT_DIR, 'stock_industry_map.json')

try:
    with open(MAP_FILE, 'r', encoding='utf-8') as f:
        STOCK_MAP = json.load(f)
except:
    STOCK_MAP = {}

def get_industry(code, name):
    """根据股票代码和名称返回产业分类"""
    
    # 优先查映射表
    if code in STOCK_MAP:
        return STOCK_MAP[code]
    
    # 基于代码前缀的简单分类
    prefix = code[:2]
    code_map = {
        '11': '水泥工業', '12': '塑膠工業', '13': '電機機械',
        '14': '建材營造', '15': '航運業', '16': '觀光事業',
        '17': '鋼鐵工業', '18': '橡膠工業', '19': '汽車工業',
        '20': '食品工業', '21': '化學工業',
        '23': '半導體業', '24': '電腦及週邊設備業', '25': '光電業',
        '26': '通信網路業', '27': '電子零組件業', '28': '金融保險',
        '29': '資訊服務業', '30': '其他電子',
        '31': '半導體業', '32': '電腦及週邊設備業',
        '34': '光電業', '35': '電子零組件業', '36': '通信網路業',
        '37': '電子零組件業', '48': '電子零組件業', '49': '電子零組件業',
        '50': '電子通路業', '51': '貿易百貨', '57': '油電燃氣業',
        '62': '生技醫療業', '64': '生技醫療業', '65': '生技醫療業',
        '80': '金融保險', '91': '其他'
    }
    
    return code_map.get(prefix, '其他')
