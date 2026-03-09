#!/usr/bin/env python3
"""
VIX 恐慌指數收集器
資料來源: Yahoo Finance (^VIX)
輸出: ../data/vix.json
"""
import json
import os
from datetime import datetime
from pathlib import Path

def get_vix_signal(value):
    if value < 15:
        return {"level": 1, "label": "市場過熱", "color": "#4cca8f", "action": "維持定時定額，嚴禁追高"}
    elif value < 20:
        return {"level": 2, "label": "平穩觀察", "color": "#d4a843", "action": "正常扣款，無特別動作"}
    elif value < 30:
        return {"level": 3, "label": "波段修正", "color": "#e8a030", "action": "試探性加碼，投入預備金約 20%"}
    elif value < 40:
        return {"level": 4, "label": "恐慌殺盤", "color": "#e8504a", "action": "第一波重倉加碼，投入預備金 40-50%"}
    else:
        return {"level": 5, "label": "極端崩盤", "color": "#c0392b", "action": "終極加碼，分 2-3 批 All-in"}

def fetch_vix():
    try:
        import yfinance as yf
    except ImportError:
        print("  安裝 yfinance...")
        import subprocess
        subprocess.run(["pip3", "install", "yfinance", "--break-system-packages", "-q"])
        import yfinance as yf

    print("  抓取 ^VIX 歷史資料...")
    ticker = yf.Ticker("^VIX")
    hist = ticker.history(period="6mo")

    if hist.empty:
        print("  ✗ 無法取得 VIX 資料")
        return False

    current = round(float(hist["Close"].iloc[-1]), 2)
    prev    = round(float(hist["Close"].iloc[-2]), 2)
    change  = round(current - prev, 2)
    change_pct = round((change / prev) * 100, 2)

    history = [
        {
            "date": idx.strftime("%Y-%m-%d"),
            "close": round(float(val), 2)
        }
        for idx, val in hist["Close"].items()
    ]

    result = {
        "current": current,
        "prev_close": prev,
        "change": change,
        "change_pct": change_pct,
        "signal": get_vix_signal(current),
        "history": history,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    out_dir = Path(__file__).parent.parent / "data"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "vix.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    sig = result["signal"]
    print(f"  ✓ VIX: {current} ({'+' if change>=0 else ''}{change}) → 【{sig['label']}】")
    print(f"  → {sig['action']}")
    return True

if __name__ == "__main__":
    fetch_vix()
