#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TSWE 多頭回檔買點訊號掃描器

每日掃描股票池、找出符合「多頭回檔買點」的訊號：
  ① 多頭結構：close > MA60 且 MA20 > MA60
  ② MACD 柱深度負值：osc 處於過去 60 日最低 25%
  ③ KD 低檔金叉：K 從 <30 區間穿越 D
  ④ 真強勢股：最近 30 天內曾創 240 日新高
  ⑤ 大盤多頭：加權指數 > MA60

回測驗證：跨 200+ 檔、3 年資料、訓驗分割
真實預期：勝率 55-60%、平均 +3.86%、賺賠比 1.5:1、持有 20 天

執行方式：
  python3 pullback_signal_scanner.py            # 自動跑、有訊號才通知
  python3 pullback_signal_scanner.py --dry-run  # 不寫 Notion、不發 Discord
  python3 pullback_signal_scanner.py --force-notify  # 強制發通知（即使 0 訊號）
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# 載入 .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

# 重用既有模組
sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_pullback_strategy import (
    fetch_yahoo, fetch_twii, add_indicators, detect_signals
)
from stock_universe import get_universe

# 通知模組（同 research_report 用法）
try:
    from twse_notify import notify_discord, NotifyLevel
    NOTIFY_AVAILABLE = True
except ImportError:
    try:
        from tswe_notify import notify_discord, NotifyLevel
        NOTIFY_AVAILABLE = True
    except ImportError:
        NOTIFY_AVAILABLE = False
        def notify_discord(*args, **kwargs): return False

import requests
import pandas as pd

# ═══════════════════════════════════════════════════════════
# 路徑與設定
# ═══════════════════════════════════════════════════════════
BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
LATEST_FILE = DATA_DIR / "pullback_signal_latest.json"
LOG_FILE = DATA_DIR / "pullback_signal_log.jsonl"
NOTIFIED_LOG_FILE = DATA_DIR / "pullback_notified_log.json"  # 去重紀錄

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(BACKEND_DIR / "pullback_signal.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# Notion API（重用既有設定）
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
NOTION_PAGE_TITLE = "📍 回檔買點訊號"  # 永久重用的頁面


def notion_headers():
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise RuntimeError("NOTION_TOKEN 未設定")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


# ═══════════════════════════════════════════════════════════
# 持續天數 (day_count) 與去重邏輯
# ═══════════════════════════════════════════════════════════
def load_notified_log() -> dict:
    """讀去重紀錄。格式：{code: {first_seen, last_seen}}"""
    if not NOTIFIED_LOG_FILE.exists():
        return {}
    try:
        with open(NOTIFIED_LOG_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_notified_log(log_data: dict):
    """寫去重紀錄"""
    NOTIFIED_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(NOTIFIED_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)


def annotate_day_count(signals: list, today_str: str, prune_days: int = 7) -> tuple[list, list]:
    """
    對訊號清單加上 day_count 欄位、並更新 notified log。

    回傳：(updated_signals, new_signals)
      updated_signals: 全部訊號（含 day_count）、給 dashboard 顯示
      new_signals: 只有 D1 的訊號、給 Discord 通知（去重）

    邏輯：
      - 訊號的 last_seen 是「昨日」 → 連續、day_count = today - first_seen + 1
      - 不在 log 或中斷過 → 新訊號、day_count = 1
      - log 裡有但今天沒訊號的紀錄：保留（之後可能再出現）
      - 超過 prune_days 沒看到的紀錄：清掉
    """
    today_dt = pd.to_datetime(today_str).date()
    log_data = load_notified_log()
    new_signals = []  # D1

    today_codes = set()
    for sig in signals:
        code = sig["code"]
        today_codes.add(code)

        if code in log_data:
            entry = log_data[code]
            try:
                last_seen = pd.to_datetime(entry["last_seen"]).date()
                first_seen = pd.to_datetime(entry["first_seen"]).date()
            except Exception:
                last_seen = first_seen = None

            if last_seen and (today_dt - last_seen).days <= 3:
                # 視為「連續」（容許週末空檔最多 3 天）
                day_count = (today_dt - first_seen).days + 1
                sig["day_count"] = day_count
                sig["first_seen"] = entry["first_seen"]
                # 更新 last_seen
                log_data[code]["last_seen"] = today_str
            else:
                # 中斷過、重新計
                sig["day_count"] = 1
                sig["first_seen"] = today_str
                log_data[code] = {"first_seen": today_str, "last_seen": today_str}
                new_signals.append(sig)
        else:
            # 全新訊號
            sig["day_count"] = 1
            sig["first_seen"] = today_str
            log_data[code] = {"first_seen": today_str, "last_seen": today_str}
            new_signals.append(sig)

    # 清掉超過 prune_days 天沒看到的紀錄
    pruned_count = 0
    for code in list(log_data.keys()):
        try:
            last_seen = pd.to_datetime(log_data[code]["last_seen"]).date()
            if (today_dt - last_seen).days > prune_days:
                del log_data[code]
                pruned_count += 1
        except Exception:
            pass

    save_notified_log(log_data)

    log.info(f"day_count: D1 (新) = {len(new_signals)}、"
             f"D2+ (已通知過) = {len(signals) - len(new_signals)}、"
             f"清除過期紀錄 {pruned_count} 筆")

    return signals, new_signals


# ═══════════════════════════════════════════════════════════
# Part 1: 掃描每檔股票
# ═══════════════════════════════════════════════════════════
def scan_one_stock(stock: dict, market_df, days: int = 365,
                   strategy: str = "v2_F",
                   as_of: str = None) -> dict | None:
    """
    對單檔股票檢查「指定日期是否觸發訊號」。
    回傳：訊號 dict（觸發）或 None（沒觸發 / 失敗）

    as_of: 'YYYY-MM-DD' 字串。None 代表用最後一天的資料。
    """
    code = stock["code"]
    name = stock.get("name", "")
    try:
        df = fetch_yahoo(code, days)
        if len(df) < 80:
            return None

        df = add_indicators(df)
        df = detect_signals(
            df,
            require_recent_high=True,
            high_lookback=240,
            high_within_days=30,
            market_df=market_df,
            strategy=strategy,
        )

        # 篩到指定日期為止（如果有）
        if as_of:
            as_of_ts = pd.to_datetime(as_of)
            df = df[df.index <= as_of_ts]
            if len(df) < 80:
                return None

        # 只看「最後一天」是否觸發
        if not df["signal"].iloc[-1]:
            return None

        # 抓最後一天的細節做訊號描述
        last = df.iloc[-1]

        # 計算 5 日漲跌（如果可能）
        change_5d_pct = None
        if len(df) >= 6:
            prev_close = df["close"].iloc[-6]
            change_5d_pct = round(float((last["close"] - prev_close) / prev_close * 100), 2)

        return {
            "code": code,
            "name": name,
            "close": round(float(last["close"]), 2),
            "ma20": round(float(last["ma20"]), 2),
            "ma60": round(float(last["ma60"]), 2),
            "osc": round(float(last["osc"]), 3),
            "k": round(float(last["k"]), 1),
            "d": round(float(last["d"]), 1),
            "change_5d_pct": change_5d_pct,
            "above_ma60": bool(last["close"] > last["ma60"]),
            "sources": stock.get("sources", []),
            "source_count": stock.get("source_count", 0),
            "signal_date": last.name.strftime("%Y-%m-%d"),
        }
    except Exception as e:
        log.warning(f"  {code} 掃描失敗：{e}")
        return None


# ═══════════════════════════════════════════════════════════
# Part 2: Notion 寫入（重用研究報告的 daily 頁邏輯）
# ═══════════════════════════════════════════════════════════
def find_notion_page(title: str):
    """找永久頁，回傳 (page_id, url) 或 None"""
    parent_id = os.environ.get("NOTION_DAY_REPORT")
    if not parent_id:
        raise RuntimeError("NOTION_DAY_REPORT 未設定")

    r = requests.post(
        f"{NOTION_API}/search",
        headers=notion_headers(),
        json={"query": title, "filter": {"value": "page", "property": "object"}},
        timeout=30
    )
    if not r.ok:
        return None

    parent_normalized = parent_id.replace("-", "")
    for page in r.json().get("results", []):
        parent = page.get("parent", {})
        if parent.get("type") != "page_id":
            continue
        if parent.get("page_id", "").replace("-", "") != parent_normalized:
            continue
        title_arr = page.get("properties", {}).get("title", {}).get("title", [])
        title_text = "".join(t.get("plain_text", "") for t in title_arr)
        if title_text == title:
            return page["id"], page["url"]
    return None


def clear_page(page_id: str):
    """清空頁面 blocks"""
    r = requests.get(
        f"{NOTION_API}/blocks/{page_id}/children",
        headers=notion_headers(), params={"page_size": 100}, timeout=30
    )
    if not r.ok:
        return
    for block in r.json().get("results", []):
        try:
            requests.delete(f"{NOTION_API}/blocks/{block['id']}",
                          headers=notion_headers(), timeout=30)
        except Exception:
            pass


def append_blocks(page_id: str, blocks: list):
    """append blocks（自動分批）"""
    for i in range(0, len(blocks), 100):
        chunk = blocks[i:i+100]
        requests.patch(
            f"{NOTION_API}/blocks/{page_id}/children",
            headers=notion_headers(), json={"children": chunk}, timeout=30
        )


def create_page(title: str, blocks: list):
    """建立新頁"""
    parent_id = os.environ.get("NOTION_DAY_REPORT")
    payload = {
        "parent": {"page_id": parent_id},
        "properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}},
        "children": blocks[:100],
    }
    r = requests.post(f"{NOTION_API}/pages", headers=notion_headers(),
                      json=payload, timeout=30)
    r.raise_for_status()
    page = r.json()
    if len(blocks) > 100:
        append_blocks(page["id"], blocks[100:])
    return page["id"], page["url"]


def upsert_signal_page(blocks: list):
    """重用既有頁、找不到就建"""
    existing = find_notion_page(NOTION_PAGE_TITLE)
    if existing:
        page_id, page_url = existing
        log.info(f"覆寫訊號頁：{page_url}")
        clear_page(page_id)
        append_blocks(page_id, blocks)
        return page_id, page_url
    else:
        log.info("首次建立訊號頁")
        return create_page(NOTION_PAGE_TITLE, blocks)


# ═══════════════════════════════════════════════════════════
# Part 3: Notion blocks 渲染
# ═══════════════════════════════════════════════════════════
def render_blocks(signals: list, scan_meta: dict) -> list:
    """產生 Notion blocks"""
    today_str = scan_meta["date"]
    scanned_count = scan_meta["scanned_count"]
    market_bullish = scan_meta["market_bullish"]
    market_close = scan_meta["market_close"]
    market_ma60 = scan_meta["market_ma60"]

    # 標題 callout
    if not signals:
        callout_text = f"今日（{today_str}）無觸發訊號。掃描 {scanned_count} 檔。"
        callout_color = "gray_background"
        emoji = "💤"
    else:
        callout_text = (f"今日（{today_str}）觸發 {len(signals)} 個訊號。"
                        f"掃描 {scanned_count} 檔。")
        callout_color = "green_background"
        emoji = "✅"

    blocks = [
        {"object": "block", "type": "callout", "callout": {
            "rich_text": [{"type": "text", "text": {"content": callout_text}}],
            "icon": {"emoji": emoji},
            "color": callout_color,
        }},
        # 大盤狀態
        {"object": "block", "type": "callout", "callout": {
            "rich_text": [{"type": "text", "text": {
                "content": (f"📊 大盤狀態：加權收 {market_close:.0f}、"
                           f"MA60 {market_ma60:.0f}、"
                           f"{'多頭' if market_bullish else '空頭'} "
                           f"{'✓' if market_bullish else '✗'}")
            }}],
            "icon": {"emoji": "📊" if market_bullish else "⚠️"},
            "color": "blue_background" if market_bullish else "red_background",
        }},
    ]

    # 訊號詳情（每檔一個 toggle）
    if signals:
        blocks.append({"object": "block", "type": "heading_2",
                      "heading_2": {"rich_text": [{"type": "text", "text": {
                          "content": "🎯 觸發訊號清單"
                      }}]}})

        for sig in signals:
            # 持續天數標籤
            dc = sig.get("day_count", 0)
            if dc == 1:
                d_tag_text = " 🆕 D1"
                d_tag_color = "orange"
            elif dc > 1:
                d_tag_text = f" D{dc}"
                d_tag_color = "gray"
            else:
                d_tag_text = ""
                d_tag_color = "default"

            toggle_rich_text = [
                {"type": "text", "text": {"content": f"{sig['code']} {sig['name']} "},
                 "annotations": {"bold": True}},
                {"type": "text", "text": {"content": f"· 收 {sig['close']:.2f}"}},
            ]
            if d_tag_text:
                toggle_rich_text.append({
                    "type": "text", "text": {"content": d_tag_text},
                    "annotations": {"bold": True, "color": d_tag_color}
                })

            blocks.append({
                "object": "block", "type": "toggle",
                "toggle": {
                    "rich_text": toggle_rich_text,
                    "children": [
                        _para("📈 技術指標：",
                              f"close={sig['close']:.2f}, MA20={sig['ma20']:.2f}, "
                              f"MA60={sig['ma60']:.2f}, MACD柱={sig['osc']:+.3f}"),
                        _para("📊 KD 狀態：",
                              f"K={sig['k']:.1f}, D={sig['d']:.1f}（金叉、低檔）"),
                        _para("⚡ 5 日漲跌：",
                              f"{sig['change_5d_pct']:+.2f}%" if sig['change_5d_pct'] else "—"),
                        _para("📅 持續天數：",
                              f"D{dc}（首次觸發 {sig.get('first_seen', '－')})" if dc else "－"),
                        _para("🌐 出現在來源：",
                              ", ".join(sig['sources']) if sig['sources'] else "—"),
                    ]
                }
            })

    # 預期警告（永遠顯示）
    blocks.append({"object": "block", "type": "heading_2",
                  "heading_2": {"rich_text": [{"type": "text", "text": {
                      "content": "📋 操作指引"
                  }}]}})

    blocks.append({"object": "block", "type": "callout", "callout": {
        "rich_text": [{"type": "text", "text": {
            "content": (
                "⚠️ 預期表現（基於 3 年回測、跨 200+ 檔、訓驗分割）：\n"
                "• 勝率：55-60%（不是 100%！可能連輸 3-4 次）\n"
                "• 平均報酬：+2~4%（持有 20 天）\n"
                "• 單筆最差：可能 -20% 以上\n"
                "• 賺賠比：1.3-1.5:1\n\n"
                "📐 紀律：\n"
                "• 持有 20 天才有效（5/10 天較弱）\n"
                "• 大盤要在 MA60 之上才採用（已過濾）\n"
                "• 建議單筆部位 ≤ 8%（凱利 1/4）\n"
                "• 接受可能單筆 -20%、勿停損太緊"
            )
        }}],
        "icon": {"emoji": "💡"},
        "color": "yellow_background"
    }})

    return blocks


def _para(label: str, content: str) -> dict:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [
        {"type": "text", "text": {"content": label}, "annotations": {"bold": True}},
        {"type": "text", "text": {"content": content}}
    ]}}


# ═══════════════════════════════════════════════════════════
# Part 4: Discord 通知
# ═══════════════════════════════════════════════════════════
def send_signal_notification(signals: list, scan_meta: dict, notion_url: str):
    """發 Discord 通知。signals 為空時用於 --force-notify 測試"""
    if not signals:
        # 用於 force-notify 測試
        return notify_discord(
            title=f"回檔買點掃描 (0 訊號)",
            message=f"今日（{scan_meta['date']}）掃描 {scan_meta['scanned_count']} 檔，無訊號觸發。",
            level=NotifyLevel.INFO,
            details={
                "📊 大盤": ("多頭 ✓" if scan_meta['market_bullish'] else "空頭 ✗"),
                "說明": "這是 --force-notify 測試訊息。正常運作時 0 訊號不會通知。",
            }
        )

    # 組訊號文字（含 D-tag）
    sig_lines = []
    for sig in signals[:10]:
        d_tag = ""
        dc = sig.get("day_count", 0)
        if dc == 1:
            d_tag = " 🆕"  # 新訊號
        elif dc > 1:
            d_tag = f" D{dc}"

        line = (f"• **{sig['code']} {sig['name']}**{d_tag} "
                f"收 {sig['close']:.2f}（MACD {sig['osc']:+.2f}, K={sig['k']:.0f}）")
        sig_lines.append(line)
    if len(signals) > 10:
        sig_lines.append(f"... (+{len(signals) - 10} 檔)")
    signal_text = "\n".join(sig_lines)

    return notify_discord(
        title=f"回檔買點訊號 ({len(signals)} 檔新訊號)",
        message=f"今日（{scan_meta['date']}）觸發 {len(signals)} 個多頭回檔買點。",
        level=NotifyLevel.SUCCESS,
        details={
            "📍 觸發訊號": signal_text,
            "🔗 詳細分析": notion_url if notion_url else "（Notion 未連結）",
            "📊 預期表現": "勝率 ~55-60%、平均 +2~4%、最差可能 -20%",
            "📐 紀律": "持有 20 天、單筆部位 ≤ 8%",
        }
    )


# ═══════════════════════════════════════════════════════════
# Part 5: 主流程
# ═══════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="不寫 Notion、不發 Discord")
    parser.add_argument("--force-notify", action="store_true",
                        help="強制發 Discord（即使 0 訊號）")
    parser.add_argument("--min-sources", type=int, default=2,
                        help="只掃描出現在 N 個來源以上的股票（預設 2）")
    parser.add_argument("--max-stocks", type=int, default=80,
                        help="掃描股票數上限（預設 80）")
    parser.add_argument("--strategy", choices=["v1", "v2_F"], default="v2_F",
                        help="策略版本：v2_F（預設、F 版抓綠柱縮小）或 v1（原版）")
    parser.add_argument("--date", default=None,
                        help="掃描指定日期（YYYY-MM-DD）的訊號狀態，預設用最後可用資料。"
                             "注意：用此參數時，latest.json 會被覆寫，要用 --no-overwrite-latest 避免。")
    parser.add_argument("--no-overwrite-latest", action="store_true",
                        help="不覆寫 latest.json（搭配 --date 跑歷史資料時用）")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    # 1. 取得 universe
    log.info("讀取股票 universe...")
    universe = get_universe(verbose=True)
    universe = [u for u in universe if u["source_count"] >= args.min_sources]
    if args.max_stocks > 0:
        universe = universe[:args.max_stocks]
    log.info(f"掃描 {len(universe)} 檔（min-sources>={args.min_sources}）")

    if not universe:
        log.warning("無股票可掃")
        return 0

    # 2. 抓加權指數
    log.info("抓加權指數...")
    market_df_full = fetch_twii(180)  # 180 天足夠算 MA60

    # 如果指定 --date，把 market_df 截到該日為止
    if args.date:
        as_of_ts = pd.to_datetime(args.date)
        market_df = market_df_full[market_df_full.index <= as_of_ts]
        if len(market_df) == 0:
            log.error(f"--date {args.date} 早於可用資料、無法掃描")
            return 1
        log.info(f"使用 --date={args.date}（取到 {market_df.index[-1].date()} 為止）")
    else:
        market_df = market_df_full

    last_market = market_df.iloc[-1]
    market_bullish = bool(last_market["bullish"])
    market_close = float(last_market["close"])
    market_ma60 = float(last_market["ma60"])
    log.info(f"加權 {market_close:.0f}、MA60 {market_ma60:.0f}、"
             f"{'多頭' if market_bullish else '空頭'}（{last_market.name.date()}）")

    # 3. 並行掃描
    log.info(f"掃描中...（策略：{args.strategy}）")
    signals = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(scan_one_stock, u, market_df, 365, args.strategy, args.date): u
            for u in universe
        }
        for fut in as_completed(futures):
            sig = fut.result()
            if sig:
                signals.append(sig)

    log.info(f"✓ 掃描完成：{len(signals)} 個訊號")
    for s in signals:
        log.info(f"  {s['code']} {s['name']} 收 {s['close']:.2f}")

    # 4. 處理輸出
    # 用 --date 或市場資料最後日期當 today_str（不要用實際日期）
    today_str = args.date or last_market.name.strftime("%Y-%m-%d")

    # 4.1 計算每檔股票的 day_count（持續第幾天）
    # signals 會被加上 day_count 欄位、new_signals 是 D1 給 Discord 用
    # dry-run 跟 no-overwrite-latest 模式不更新 notified log（避免污染）
    if args.dry_run or args.no_overwrite_latest:
        log.info("[dry-run/no-overwrite] 跳過 day_count 計算（不污染 notified log）")
        new_signals = signals  # 全部當新訊號處理
        for s in signals:
            s["day_count"] = 0  # 用 0 表示「未計算」
            s["first_seen"] = today_str
    else:
        signals, new_signals = annotate_day_count(signals, today_str)

    scan_meta = {
        "date": today_str,
        "scanned_count": len(universe),
        "signal_count": len(signals),
        "new_signal_count": len(new_signals),
        "market_bullish": market_bullish,
        "market_close": market_close,
        "market_ma60": market_ma60,
    }

    if args.dry_run:
        log.info("[dry-run] 跳過 Notion 與 Discord")
        return 0

    # 5. Notion + Discord（只在有訊號時才動）
    page_url = ""
    if signals:
        # 有訊號 → 寫 Notion（含全部訊號、含 day_count）
        blocks = render_blocks(signals, scan_meta)
        try:
            page_id, page_url = upsert_signal_page(blocks)
            log.info(f"✓ Notion 寫入完成：{page_url}")
        except Exception as e:
            log.error(f"❌ Notion 寫入失敗：{e}")
            page_url = ""

        # Discord：只發 D1（新訊號）、避免重複
        if new_signals:
            sent = send_signal_notification(new_signals, scan_meta, page_url)
            if sent:
                log.info(f"✓ Discord 通知已送（{len(new_signals)} 個新訊號）")
        else:
            log.info(f"全部 {len(signals)} 個訊號都是 D2+ 已通知過、不重複發 Discord")
    elif args.force_notify:
        # 強制模式：0 訊號也通知（測試用）
        log.info("--force-notify: 0 訊號但仍寫 Notion + 發 Discord")
        blocks = render_blocks(signals, scan_meta)
        try:
            page_id, page_url = upsert_signal_page(blocks)
        except Exception as e:
            log.error(f"❌ Notion 寫入失敗：{e}")
            page_url = ""
        send_signal_notification(signals, scan_meta, page_url)
    else:
        # 0 訊號正常情況：什麼都不做
        log.info("0 訊號、不寫 Notion、不發 Discord（零訊號模式）")

    # 7. latest.json 和 log（永遠寫，給 dashboard 顯示用）
    latest_data = {
        "date": today_str,
        "strategy": args.strategy,
        "scanned_count": len(universe),
        "signal_count": len(signals),
        "signals": signals,
        "market_bullish": market_bullish,
        "market_close": market_close,
        "market_ma60": market_ma60,
        "notion_url": page_url,
        "updated_at": datetime.now().isoformat(timespec='seconds'),
    }
    if args.no_overwrite_latest:
        log.info(f"--no-overwrite-latest: 不覆寫 {LATEST_FILE.name}（dashboard 仍顯示原資料）")
        # 改寫到帶日期的檔案
        history_file = DATA_DIR / f"pullback_signal_{today_str}.json"
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(latest_data, f, ensure_ascii=False, indent=2)
        log.info(f"✓ 歷史資料寫入：{history_file.name}")
    else:
        with open(LATEST_FILE, 'w', encoding='utf-8') as f:
            json.dump(latest_data, f, ensure_ascii=False, indent=2)

    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps({
            "date": today_str,
            "scanned": len(universe),
            "signals": len(signals),
            "codes": [s["code"] for s in signals],
            "market_bullish": market_bullish,
            "notion_url": page_url,
        }, ensure_ascii=False) + '\n')

    log.info("✓ 完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
