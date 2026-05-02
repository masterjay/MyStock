#!/usr/bin/env python3
"""
[3v2/4] 題材輪動雷達 v2 - 支援 HiStock + CMoney 雙來源

讀入:
  - data/theme_stocks_cmoney.json  (CMoney 抓的, 優先, 已含當日股價)
  - data/theme_stocks.json         (HiStock 抓的, 備用)
  - data/foreign_top_stocks.json   (你既有的法人資料, 可選)

輸出: data/theme_radar.json (給前端用的題材熱度排行)

策略:
  - 當日股價: CMoney 直接給, HiStock 沒給就從 Yahoo 補
  - 5 日漲幅: 一律從 Yahoo Finance 算 (CMoney/HiStock 都沒有)
  - 加速度 = 今日漲幅 - (5日累積/5)

執行時間: 約 1-3 分鐘 (取決於成分股總數)

用法: python3 3v2_calc_theme_radar.py
"""
import requests
import json
import os
import sys
import statistics
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

CMONEY_PATH = "data/theme_stocks_cmoney.json"
HISTOCK_PATH = "data/theme_stocks.json"
FOREIGN_PATH = "data/foreign_top_stocks.json"
OUTPUT_PATH = "data/theme_radar.json"

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{code}.{exch}?interval=1d&range=10d"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def fetch_yahoo_history(code: str) -> dict | None:
    """從 Yahoo Finance 抓 10 日 K 線, 優先試 .TW 再試 .TWO"""
    for exch in ("TW", "TWO"):
        url = YAHOO_URL.format(code=code, exch=exch)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code != 200:
                continue
            data = resp.json()
            result = data.get("chart", {}).get("result")
            if not result:
                continue
            quote = result[0]["indicators"]["quote"][0]
            closes = quote.get("close", [])
            volumes = quote.get("volume", [])

            valid = [(c, v) for c, v in zip(closes, volumes)
                     if c is not None and v is not None]
            if len(valid) < 6:
                continue

            closes_clean = [c for c, _ in valid]
            volumes_clean = [v for _, v in valid]

            today_close = closes_clean[-1]
            yesterday_close = closes_clean[-2]
            five_days_ago = closes_clean[-6]

            return {
                "today_change_pct": (today_close - yesterday_close) / yesterday_close * 100,
                "five_day_change_pct": (today_close - five_days_ago) / five_days_ago * 100,
                "today_volume": volumes_clean[-1],
                "today_close": today_close,
            }
        except Exception:
            continue
    return None


def load_foreign_buy_codes() -> tuple[set, set, set]:
    """載入法人買超個股, 回傳 (外資買超, 投信買超, 雙買) 三個集合"""
    if not os.path.exists(FOREIGN_PATH):
        return set(), set(), set()
    try:
        with open(FOREIGN_PATH, encoding="utf-8") as f:
            data = json.load(f)

        # 真實結構: top_buy / trust_top_buy 是清單, 各筆都含 code, net, trust_net
        # 注意: top_buy 裡的個股是「外資買超 Top」, 不代表 trust_net 一定 > 0
        # 反之亦然. 所以要從這四個清單共同推算
        foreign_buy = set()  # 外資買超 (net > 0)
        trust_buy = set()    # 投信買超 (trust_net > 0)

        # 從所有四個清單蒐集 (因為一檔股可能同時出現在多個清單)
        all_lists = []
        for key in ("top_buy", "top_sell", "trust_top_buy", "trust_top_sell"):
            all_lists.extend(data.get(key, []))

        for item in all_lists:
            code = str(item.get("code", "")).strip()
            if not code:
                continue
            net = item.get("net", 0) or 0
            trust_net = item.get("trust_net", 0) or 0
            if net > 0:
                foreign_buy.add(code)
            if trust_net > 0:
                trust_buy.add(code)

        both_buy = foreign_buy & trust_buy  # 雙買
        return foreign_buy, trust_buy, both_buy
    except Exception as e:
        print(f"⚠️  讀取法人資料失敗: {e}", file=sys.stderr)
        return set(), set(), set()


def merge_theme_data() -> tuple[dict, str]:
    """合併 CMoney 與 HiStock 來源, 統一格式"""
    sources_used = []
    merged = {}  # {theme_key: {stocks: [{code, name, ...}], source: "cmoney"|"histock"}}

    # 優先載入 CMoney (有今日股價)
    if os.path.exists(CMONEY_PATH):
        with open(CMONEY_PATH, encoding="utf-8") as f:
            cmoney_data = json.load(f)
        for tk, tdata in cmoney_data.get("themes", {}).items():
            merged[tk] = {
                "stocks": tdata["stocks"],  # 已是 list[dict]
                "source": "cmoney",
            }
        if cmoney_data.get("themes"):
            sources_used.append("CMoney")

    # 補充載入 HiStock (沒有今日股價, 要從 Yahoo 補)
    if os.path.exists(HISTOCK_PATH):
        with open(HISTOCK_PATH, encoding="utf-8") as f:
            histock_data = json.load(f)
        for tk, tdata in histock_data.get("themes", {}).items():
            if tk in merged:
                continue  # CMoney 優先
            # 把 HiStock 的 {code: name} 轉成 list[dict]
            stocks = [{"code": code, "name": name, "price": None,
                       "change_pct": None, "volume": None}
                      for code, name in tdata["stocks"].items()]
            merged[tk] = {"stocks": stocks, "source": "histock"}
        if histock_data.get("themes"):
            sources_used.append("HiStock")

    return merged, " + ".join(sources_used) if sources_used else "(none)"


def status_label(score: dict) -> str:
    avg_today = score["avg_today_change_pct"]
    avg_5d = score["avg_5d_change_pct"]
    accel = score["acceleration"]
    breadth = score["breadth_pct"]

    if avg_5d > 5 and accel > 0 and breadth > 60:
        return "🔥 主流"
    if avg_5d > 5 and accel < 0:
        return "⚠️ 高位整理"
    if avg_5d < 0 and accel > 1 and breadth > 50:
        return "🚀 接棒中"
    if avg_5d > 0 and accel > 0 and breadth > 50:
        return "📈 強勢"
    if avg_5d < -3 and accel < 0:
        return "💤 退潮"
    return "😐 觀望"


def main():
    merged, sources = merge_theme_data()
    if not merged:
        print(f"❌ 找不到任何題材資料")
        print(f"   請先執行 2b_fetch_cmoney_stocks.py 或 2_fetch_theme_stocks.py")
        sys.exit(1)

    foreign_buy, trust_buy, both_buy = load_foreign_buy_codes()
    print(f"=== 題材輪動雷達 v2 ===")
    print(f"資料來源: {sources}")
    print(f"題材數: {len(merged)}")
    print(f"外資買超: {len(foreign_buy)} 檔, 投信買超: {len(trust_buy)} 檔, "
          f"雙買: {len(both_buy)} 檔")
    print()

    # 收集所有需要查詢 5 日歷史的代號
    all_codes = set()
    for tdata in merged.values():
        for s in tdata["stocks"]:
            all_codes.add(s["code"])
    print(f"需查詢 {len(all_codes)} 檔個股的 Yahoo 歷史資料 (算 5 日漲幅)...")

    # 並行抓 Yahoo
    yahoo_cache = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        future_to_code = {ex.submit(fetch_yahoo_history, c): c for c in all_codes}
        completed = 0
        for f in as_completed(future_to_code):
            code = future_to_code[f]
            info = f.result()
            if info:
                yahoo_cache[code] = info
            completed += 1
            if completed % 20 == 0:
                print(f"  ... {completed}/{len(all_codes)}")
    print(f"✅ Yahoo 抓到 {len(yahoo_cache)}/{len(all_codes)} 檔")
    print()

    # 計算每個題材
    radar = []
    for theme_key, tdata in merged.items():
        stock_results = []
        for s in tdata["stocks"]:
            code = s["code"]
            yh = yahoo_cache.get(code)

            # 今日漲幅: CMoney 提供就用, 否則從 Yahoo
            if s.get("change_pct") is not None:
                today_pct = s["change_pct"]
            elif yh:
                today_pct = yh["today_change_pct"]
            else:
                continue  # 沒資料, 跳過

            # 5 日漲幅: 只能從 Yahoo
            if not yh:
                continue

            stock_results.append({
                "code": code,
                "name": s.get("name", ""),
                "price": s.get("price") or yh["today_close"],
                "change_pct": round(today_pct, 2),
                "five_day_pct": round(yh["five_day_change_pct"], 2),
                "volume": s.get("volume") or yh["today_volume"],
                "foreign_buy": code in foreign_buy,
                "trust_buy": code in trust_buy,
                "both_buy": code in both_buy,
            })

        if not stock_results:
            print(f"  ⚠️  {theme_key}: 無有效個股資料, 跳過")
            continue

        today_pcts = [s["change_pct"] for s in stock_results]
        five_day_pcts = [s["five_day_pct"] for s in stock_results]

        avg_today = statistics.mean(today_pcts)
        avg_5d = statistics.mean(five_day_pcts)
        accel = avg_today - avg_5d / 5

        rising = sum(1 for s in stock_results if s["change_pct"] > 0)
        breadth = rising / len(stock_results) * 100
        foreign_cnt = sum(1 for s in stock_results if s["foreign_buy"])
        trust_cnt = sum(1 for s in stock_results if s["trust_buy"])
        both_cnt = sum(1 for s in stock_results if s["both_buy"])

        sorted_stocks = sorted(stock_results, key=lambda x: x["change_pct"], reverse=True)

        score = {
            "theme": theme_key,
            "source": tdata["source"],
            "stock_count": len(stock_results),
            "avg_today_change_pct": round(avg_today, 2),
            "avg_5d_change_pct": round(avg_5d, 2),
            "acceleration": round(accel, 2),
            "breadth_pct": round(breadth, 1),
            "foreign_buy_count": foreign_cnt,
            "trust_buy_count": trust_cnt,
            "both_buy_count": both_cnt,
            "foreign_buy_ratio": round(foreign_cnt / len(stock_results) * 100, 1),
            "leaders": sorted_stocks[:5],
            "laggards": sorted_stocks[-3:][::-1],
        }
        score["status"] = status_label(score)
        radar.append(score)

    # 排序: 5 日漲幅由大到小
    radar.sort(key=lambda x: x["avg_5d_change_pct"], reverse=True)

    # 顯示
    print(f"{'#':<3}{'題材':<20}{'狀態':<14}{'今日%':>8}{'5日%':>8}"
          f"{'加速度':>8}{'寬度':>7}{'外資':>6}{'投信':>6}{'雙買':>6}")
    print("-" * 92)
    for i, s in enumerate(radar, 1):
        print(f"{i:<3}{s['theme']:<20}{s['status']:<14}"
              f"{s['avg_today_change_pct']:>+7.2f}%"
              f"{s['avg_5d_change_pct']:>+7.2f}%"
              f"{s['acceleration']:>+7.2f}"
              f"{s['breadth_pct']:>6.1f}%"
              f"{s['foreign_buy_count']:>3d}/{s['stock_count']:<2d}"
              f"{s['trust_buy_count']:>3d}/{s['stock_count']:<2d}"
              f"{s['both_buy_count']:>3d}/{s['stock_count']:<2d}")

    # 存檔
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sources": sources,
        "themes": radar,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n已儲存: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
