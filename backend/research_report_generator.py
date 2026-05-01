#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TSWE 新高雷達研究報告產生器（方案 C：低版本 + 詳細版）

執行模式：
  - daily mode (Haiku): 每日跑、低版本，名單未變動時使用
  - detail mode (Sonnet): 名單有變動時，產出完整三面向分析

呼叫方式：
  python3 research_report_generator.py            # 自動判斷模式
  python3 research_report_generator.py --force-detail  # 強制詳細版
  python3 research_report_generator.py --force-daily   # 強制低版本
  python3 research_report_generator.py --dry-run       # 不呼叫 API、不寫 Notion

依賴：
  pip install anthropic requests --break-system-packages

環境變數：
  ANTHROPIC_API_KEY      Claude API 金鑰
  NOTION_TOKEN           Notion integration token
  NOTION_DAY_REPORT  研究報告父頁面 ID
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# 載入 .env (和 backend/ 其他模組相同慣例)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass  # 沒裝 python-dotenv 也能跑，會 fallback 到系統環境變數

# 通知模組（Discord）— 失敗會 graceful degrade，不影響主流程
try:
    from tswe_notify import (
        notify_blocked_overlimit,
        notify_notion_failed,
        notify_api_failed,
        notify_cost_threshold,
        notify_empty_after_filter,
    )
    NOTIFY_AVAILABLE = True
except ImportError:
    NOTIFY_AVAILABLE = False
    def notify_blocked_overlimit(*args, **kwargs): pass
    def notify_notion_failed(*args, **kwargs): pass
    def notify_api_failed(*args, **kwargs): pass
    def notify_cost_threshold(*args, **kwargs): pass
    def notify_empty_after_filter(*args, **kwargs): pass

# ═══════════════════════════════════════════════════════════
# 路徑設定
# ═══════════════════════════════════════════════════════════
BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
NEW_HIGH_FILE = DATA_DIR / "new_high_stocks.json"
STATE_FILE = DATA_DIR / "new_high_research_state.json"
LATEST_FILE = DATA_DIR / "new_high_research_latest.json"
LOG_FILE = DATA_DIR / "new_high_research_log.jsonl"
COST_FILE = DATA_DIR / "new_high_research_cost.json"
FOREIGN_TOP_FILE = DATA_DIR / "foreign_top_stocks.json"
MACD_SIGNAL_FILE = DATA_DIR / "macd_signal_stocks.json"

# ═══════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(BACKEND_DIR / "research_generator.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# Claude API 設定
# ═══════════════════════════════════════════════════════════
MODEL_HAIKU = "claude-haiku-4-5-20251001"
MODEL_SONNET = "claude-sonnet-4-6"

# 各模型的 token 價格（USD per 1M tokens）— 用於 cost monitor
PRICING = {
    MODEL_HAIKU: {"input": 1.0, "output": 5.0, "cache_read": 0.10},
    MODEL_SONNET: {"input": 3.0, "output": 15.0, "cache_read": 0.30},
}

# ═══════════════════════════════════════════════════════════
# Notion 設定
# ═══════════════════════════════════════════════════════════
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


# ═══════════════════════════════════════════════════════════
# Part 1: 模式判斷
# ═══════════════════════════════════════════════════════════
def load_today_list() -> list[dict]:
    """讀今日新高雷達結果"""
    if not NEW_HIGH_FILE.exists():
        log.error(f"找不到 {NEW_HIGH_FILE}")
        return []
    with open(NEW_HIGH_FILE, encoding='utf-8') as f:
        data = json.load(f)
    return data.get("stocks", [])


def load_yesterday_state() -> Optional[dict]:
    """讀昨日的 state"""
    if not STATE_FILE.exists():
        return None
    with open(STATE_FILE, encoding='utf-8') as f:
        return json.load(f)


def determine_mode(today_codes: set, yesterday_state: Optional[dict]) -> str:
    """判斷該跑 daily 還是 detail 模式"""
    if yesterday_state is None:
        log.info("首次執行，使用 detail 模式")
        return "detail"

    yesterday_codes = set(yesterday_state.get("codes", []))
    if today_codes != yesterday_codes:
        added = today_codes - yesterday_codes
        removed = yesterday_codes - today_codes
        log.info(f"名單變動：新增 {sorted(added)}、移除 {sorted(removed)} → detail 模式")
        return "detail"

    log.info("名單無變動 → daily 模式（低版本）")
    return "daily"


# ═══════════════════════════════════════════════════════════
# Part 2: 資料抓取
# ═══════════════════════════════════════════════════════════
def fetch_yahoo_chart(code: str, days: int = 60) -> dict:
    """從 Yahoo Finance 抓 OHLCV"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{code}.TW"
    params = {"interval": "1d", "range": f"{days}d"}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"Yahoo {code} 抓取失敗：{e}")
        return {}


def compute_technicals(chart: dict) -> dict:
    """從 Yahoo chart 算技術指標摘要"""
    try:
        result = chart["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        closes = [c for c in quote["close"] if c is not None]
        volumes = [v for v in quote["volume"] if v is not None]

        if len(closes) < 20:
            return {}

        latest = closes[-1]
        ma5 = sum(closes[-5:]) / 5
        ma20 = sum(closes[-20:]) / 20
        ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else None

        # 量比（當日量 / 20 日均量）
        vol_ratio = None
        if len(volumes) >= 20:
            ma20_vol = sum(volumes[-20:]) / 20
            vol_ratio = volumes[-1] / ma20_vol if ma20_vol > 0 else None

        # 近 5 日漲跌幅
        change_5d = None
        if len(closes) >= 6:
            change_5d = (closes[-1] - closes[-6]) / closes[-6] * 100

        # 近 20 日漲跌幅
        change_20d = None
        if len(closes) >= 21:
            change_20d = (closes[-1] - closes[-21]) / closes[-21] * 100

        return {
            "close": round(latest, 2),
            "ma5": round(ma5, 2),
            "ma20": round(ma20, 2),
            "ma60": round(ma60, 2) if ma60 else None,
            "vol_ratio": round(vol_ratio, 2) if vol_ratio else None,
            "above_ma5": latest > ma5,
            "above_ma20": latest > ma20,
            "above_ma60": latest > ma60 if ma60 else None,
            "high_60d": round(max(closes), 2),
            "low_60d": round(min(closes), 2),
            "change_5d_pct": round(change_5d, 2) if change_5d is not None else None,
            "change_20d_pct": round(change_20d, 2) if change_20d is not None else None,
        }
    except Exception as e:
        log.warning(f"技術指標計算失敗：{e}")
        return {}


def fetch_chip_data(code: str, foreign_data: dict, macd_data: dict) -> dict:
    """從現有 JSON 拿外資/投信籌碼資料"""
    chip = {}

    # foreign_top_stocks.json
    for item in foreign_data.get("stocks", []):
        if item.get("code") == code:
            chip["foreign_net"] = item.get("net")
            chip["trust_net"] = item.get("trust_net")
            break

    # macd_signal_stocks.json (signals 陣列)
    for item in macd_data.get("signals", []):
        if item.get("code") == code:
            chip["macd_source"] = item.get("source")
            chip["macd_concepts"] = [c.get("label") for c in item.get("concepts", [])]
            break

    return chip


def gather_stock_data(stock: dict, foreign_data: dict, macd_data: dict) -> dict:
    """整合一檔股票的所有資料"""
    code = stock["code"]
    chart = fetch_yahoo_chart(code)
    return {
        "code": code,
        "name": stock.get("name", ""),
        # screener 給的原始欄位（含新高分級、強度、量比、爆量等）
        "screener": {
            "today_close": stock.get("today_close"),
            "strength": stock.get("strength"),
            "high_20": stock.get("high_20"),
            "high_60": stock.get("high_60"),
            "high_120": stock.get("high_120"),
            "high_240": stock.get("high_240"),
            "high_all": stock.get("high_all"),
            "volume_ratio": stock.get("volume_ratio"),
            "volume_breakout": stock.get("volume_breakout"),
        },
        "technicals": compute_technicals(chart),
        "chips": fetch_chip_data(code, foreign_data, macd_data),
    }


# ═══════════════════════════════════════════════════════════
# Part 3: Claude API 呼叫
# ═══════════════════════════════════════════════════════════
SYSTEM_PROMPT_BASE = """你是台灣股市的研究員助理。輸出規則：
- 用繁體中文
- 台股紅漲綠跌（不要寫成美股配色）
- 不構成投資建議，僅整理公開資訊
- 嚴格依使用者要求的 JSON 格式回覆，不加任何前後綴文字、不加 markdown code fence
- 數字保留合理小數位（百分比 2 位、價格 1-2 位）"""


def build_daily_prompt(stock_data: dict) -> str:
    """低版本 prompt：簡短評等"""
    return f"""請依下列資料，給這檔股票一個簡短評估。

股票：{stock_data['code']} {stock_data['name']}
篩選器訊號：{json.dumps(stock_data['screener'], ensure_ascii=False)}
技術面：{json.dumps(stock_data['technicals'], ensure_ascii=False)}
籌碼：{json.dumps(stock_data['chips'], ensure_ascii=False)}

請以以下 JSON 格式回覆：
{{
  "code": "{stock_data['code']}",
  "rating": "★★★★",
  "summary": "30-50字摘要，講重點訊號或變化",
  "tag": "持續加碼/持平/警示/移除"
}}

評等規則：
- ★★★★★ 業績與技術面雙強、籌碼進駐
- ★★★★ 有單一突出面向（如爆量+多頭排列）
- ★★★ 中性、訊號不夠明確
- ★★ 偏弱、有警示訊號
- ★ 避開"""


def build_detail_prompt(stock_data: dict) -> str:
    """詳細版 prompt：完整三面向分析"""
    return f"""請依下列資料，給這檔股票完整三面向分析。

股票：{stock_data['code']} {stock_data['name']}
篩選器訊號：{json.dumps(stock_data['screener'], ensure_ascii=False)}
技術面：{json.dumps(stock_data['technicals'], ensure_ascii=False)}
籌碼：{json.dumps(stock_data['chips'], ensure_ascii=False)}

請以以下 JSON 格式回覆：
{{
  "code": "{stock_data['code']}",
  "name": "{stock_data['name']}",
  "industry_theme": "產業/題材歸類（如：半導體 / SiC / CPO 概念）",
  "rating": "★★★★",
  "fundamentals": "基本面分析（80-120字，著重營收、EPS、產業地位、催化劑）",
  "technicals": "技術面分析（60-100字，量價、均線、型態）",
  "chips": "籌碼面分析（40-80字，外資/投信、主力動向）",
  "entry_zone": "建議觀察進場區間或停損參考",
  "risks": "主要風險（30-50字）",
  "verdict": "綜合判斷一句話"
}}

評等規則同上：★★★★★ 雙強 / ★★★★ 單面突出 / ★★★ 中性 / ★★ 偏弱 / ★ 避開"""


def call_claude(prompt: str, model: str, use_cache: bool = True) -> tuple[dict, dict]:
    """
    呼叫 Claude API。
    回傳 (parsed_json, usage_dict)
    usage_dict 包含 input_tokens / output_tokens / cache_creation_tokens / cache_read_tokens
    """
    import anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY 未設定")

    client = anthropic.Anthropic(api_key=api_key)

    system_blocks = [{"type": "text", "text": SYSTEM_PROMPT_BASE}]
    if use_cache:
        system_blocks[0]["cache_control"] = {"type": "ephemeral"}

    resp = client.messages.create(
        model=model,
        max_tokens=1500,
        system=system_blocks,
        messages=[{"role": "user", "content": prompt}],
    )

    text = resp.content[0].text.strip()
    # 防呆：去掉可能的 markdown code fence
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()

    parsed = json.loads(text)

    usage = {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "cache_creation_tokens": getattr(resp.usage, 'cache_creation_input_tokens', 0),
        "cache_read_tokens": getattr(resp.usage, 'cache_read_input_tokens', 0),
        "model": model,
    }
    return parsed, usage


def analyze_stock(stock_data: dict, mode: str, dry_run: bool = False) -> tuple[dict, dict]:
    """單檔分析。回傳 (analysis, usage)"""
    code = stock_data["code"]
    if dry_run:
        return ({
            "code": code,
            "rating": "★★★",
            "summary": f"[dry-run] 模擬分析 {code}",
            "tag": "持平",
        }, {"input_tokens": 0, "output_tokens": 0, "cache_creation_tokens": 0, "cache_read_tokens": 0, "model": "dry-run"})

    try:
        if mode == "daily":
            return call_claude(build_daily_prompt(stock_data), MODEL_HAIKU)
        else:
            return call_claude(build_detail_prompt(stock_data), MODEL_SONNET)
    except Exception as e:
        log.error(f"分析 {code} 失敗：{e}")
        return ({"code": code, "error": str(e)},
                {"input_tokens": 0, "output_tokens": 0, "cache_creation_tokens": 0, "cache_read_tokens": 0, "model": "error"})


# ═══════════════════════════════════════════════════════════
# Part 4: Notion 寫入
# ═══════════════════════════════════════════════════════════
def notion_headers() -> dict:
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise RuntimeError("NOTION_TOKEN 未設定")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def render_daily_blocks(analyses: list[dict], summary_meta: dict) -> list[dict]:
    """低版本 → Notion blocks"""
    blocks = [
        {"object": "block", "type": "callout", "callout": {
            "rich_text": [{"type": "text", "text": {
                "content": f"模式：每日狀態 · 共 {len(analyses)} 檔 · 更新 {summary_meta['updated_at']}"
            }}],
            "icon": {"emoji": "📊"},
            "color": "gray_background"
        }}
    ]

    for a in analyses:
        if "error" in a:
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"type": "text", "text": {
                    "content": f"⚠️ {a['code']} 分析失敗：{a.get('error', '')[:80]}"
                }}]}
            })
            continue
        blocks.append({
            "object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [
                {"type": "text", "text": {"content": f"{a['code']} "},
                 "annotations": {"bold": True, "code": True}},
                {"type": "text", "text": {"content": f"{a.get('rating', '')} "}},
                {"type": "text", "text": {"content": f"[{a.get('tag', '')}] "},
                 "annotations": {"color": "blue"}},
                {"type": "text", "text": {"content": f"→ {a.get('summary', '')}"}},
            ]}
        })
    return blocks


def render_detail_blocks(analyses: list[dict], summary_meta: dict) -> list[dict]:
    """詳細版 → Notion blocks（每檔一個 toggle）"""
    blocks = [
        {"object": "block", "type": "callout", "callout": {
            "rich_text": [{"type": "text", "text": {
                "content": f"模式：詳細研究 · 共 {len(analyses)} 檔 · 名單變動觸發 · 更新 {summary_meta['updated_at']}"
            }}],
            "icon": {"emoji": "🔬"},
            "color": "blue_background"
        }}
    ]

    for a in analyses:
        if "error" in a:
            blocks.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {
                    "content": f"⚠️ {a['code']} 分析失敗：{a.get('error', '')[:200]}"
                }}]}
            })
            continue

        blocks.append({
            "object": "block", "type": "toggle",
            "toggle": {
                "rich_text": [
                    {"type": "text", "text": {"content": f"{a['code']} {a.get('name', '')} "},
                     "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": f"· {a.get('rating', '')} "}},
                    {"type": "text", "text": {"content": f"· {a.get('industry_theme', '')}"},
                     "annotations": {"color": "gray"}},
                ],
                "children": [
                    _para("📈 基本面：", a.get("fundamentals", "—")),
                    _para("📊 技術面：", a.get("technicals", "—")),
                    _para("💎 籌碼面：", a.get("chips", "—")),
                    {"object": "block", "type": "callout", "callout": {
                        "rich_text": [{"type": "text", "text": {
                            "content": (
                                f"🎯 {a.get('verdict', '—')}\n"
                                f"進場參考：{a.get('entry_zone', '—')}\n"
                                f"風險：{a.get('risks', '—')}"
                            )
                        }}],
                        "icon": {"emoji": "💡"},
                        "color": "yellow_background"
                    }}
                ]
            }
        })
    return blocks


def _para(label: str, content: str) -> dict:
    """產一個 paragraph block，前面是粗體 label"""
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [
        {"type": "text", "text": {"content": label}, "annotations": {"bold": True}},
        {"type": "text", "text": {"content": content}}
    ]}}


DAILY_PAGE_TITLE = "📊 每日狀態"  # 永久重用的每日狀態頁標題


def _append_blocks_in_chunks(page_id: str, blocks: list[dict]):
    """Notion 單次 append 上限 100 blocks，自動分批"""
    for i in range(0, len(blocks), 100):
        chunk = blocks[i:i+100]
        r = requests.patch(
            f"{NOTION_API}/blocks/{page_id}/children",
            headers=notion_headers(),
            json={"children": chunk}, timeout=30
        )
        if not r.ok:
            log.error(f"Notion append error: {r.status_code} {r.text}")
            r.raise_for_status()


def create_notion_page(title: str, blocks: list[dict]) -> tuple[str, str]:
    """建立全新 Notion 子頁，回傳 (page_id, url)。用於詳細版每次新建"""
    parent_id = os.environ.get("NOTION_DAY_REPORT")
    if not parent_id:
        raise RuntimeError("NOTION_DAY_REPORT 未設定")

    payload = {
        "parent": {"page_id": parent_id},
        "properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}},
        "children": blocks[:100],
    }
    r = requests.post(f"{NOTION_API}/pages", headers=notion_headers(),
                      json=payload, timeout=30)
    if not r.ok:
        log.error(f"Notion API error: {r.status_code} {r.text}")
        r.raise_for_status()
    page = r.json()

    # 超過 100 blocks 用 append 補上
    if len(blocks) > 100:
        _append_blocks_in_chunks(page["id"], blocks[100:])

    return page["id"], page["url"]


def find_daily_page() -> Optional[tuple[str, str]]:
    """
    在父頁面下找名為 DAILY_PAGE_TITLE 的子頁。
    回傳 (page_id, url) 或 None。
    用於每日模式重用同一頁。
    """
    parent_id = os.environ.get("NOTION_DAY_REPORT")
    if not parent_id:
        raise RuntimeError("NOTION_DAY_REPORT 未設定")

    # 用 search API 找頁面（限定父頁面下的子頁）
    r = requests.post(
        f"{NOTION_API}/search",
        headers=notion_headers(),
        json={
            "query": DAILY_PAGE_TITLE,
            "filter": {"value": "page", "property": "object"},
        },
        timeout=30
    )
    if not r.ok:
        log.warning(f"Notion search 失敗：{r.status_code} {r.text}")
        return None

    results = r.json().get("results", [])
    parent_id_normalized = parent_id.replace("-", "")

    for page in results:
        # 確認 parent 是我們的目標頁面
        parent = page.get("parent", {})
        if parent.get("type") != "page_id":
            continue
        page_parent_id = parent.get("page_id", "").replace("-", "")
        if page_parent_id != parent_id_normalized:
            continue

        # 確認標題匹配
        title_arr = page.get("properties", {}).get("title", {}).get("title", [])
        if not title_arr:
            continue
        title_text = "".join(t.get("plain_text", "") for t in title_arr)
        if title_text == DAILY_PAGE_TITLE:
            log.info(f"找到既有每日頁：{page['url']}")
            return page["id"], page["url"]

    log.info("未找到既有每日頁，將建立新的")
    return None


def clear_page_blocks(page_id: str):
    """
    清空頁面的所有 blocks（保留頁面本身和 properties）。
    用於每日模式覆寫前。
    """
    # 先列出所有 children
    r = requests.get(
        f"{NOTION_API}/blocks/{page_id}/children",
        headers=notion_headers(),
        params={"page_size": 100},
        timeout=30
    )
    if not r.ok:
        log.warning(f"列出 children 失敗：{r.status_code}")
        return

    blocks = r.json().get("results", [])
    deleted = 0
    for block in blocks:
        try:
            requests.delete(
                f"{NOTION_API}/blocks/{block['id']}",
                headers=notion_headers(),
                timeout=30
            )
            deleted += 1
        except Exception as e:
            log.warning(f"刪除 block {block['id']} 失敗：{e}")

    log.info(f"清空舊內容：刪除 {deleted} 個 blocks")

    # 處理超過 100 的情況（罕見，但防呆）
    if r.json().get("has_more"):
        log.warning("頁面有超過 100 個 blocks 需要清理，建議手動清空")


def upsert_daily_page(blocks: list[dict], today_str: str) -> tuple[str, str]:
    """
    每日模式：找既有「每日狀態」頁，清空後寫入；找不到就建立新的。
    頁面標題永遠是 DAILY_PAGE_TITLE，但 callout 裡會顯示今日日期。
    """
    existing = find_daily_page()

    if existing:
        page_id, page_url = existing
        log.info(f"覆寫每日狀態頁：{page_url}")
        clear_page_blocks(page_id)
        # 重新寫入
        _append_blocks_in_chunks(page_id, blocks)
        return page_id, page_url
    else:
        # 第一次跑、建立新頁
        return create_notion_page(DAILY_PAGE_TITLE, blocks)


# ═══════════════════════════════════════════════════════════
# Part 5: Cost Monitor
# ═══════════════════════════════════════════════════════════
def calculate_cost(usage: dict) -> float:
    """根據單次 usage 計算 USD 成本"""
    model = usage.get("model")
    if model not in PRICING:
        return 0.0
    p = PRICING[model]
    cost = (
        usage.get("input_tokens", 0) / 1_000_000 * p["input"]
        + usage.get("output_tokens", 0) / 1_000_000 * p["output"]
        + usage.get("cache_creation_tokens", 0) / 1_000_000 * p["input"] * 1.25
        + usage.get("cache_read_tokens", 0) / 1_000_000 * p["cache_read"]
    )
    return cost


def update_cost_monitor(today_str: str, mode: str, total_cost_usd: float, stock_count: int):
    """累加月度成本，超過閾值警告"""
    THRESHOLD_USD = float(os.environ.get("COST_THRESHOLD_USD", "5.0"))

    cost_data = {}
    if COST_FILE.exists():
        with open(COST_FILE, encoding='utf-8') as f:
            cost_data = json.load(f)

    month_key = today_str[:7]  # "2026-05"
    if month_key not in cost_data:
        cost_data[month_key] = {"total_usd": 0.0, "runs": [], "alert_sent": False}

    # 確保 alert_sent 欄位存在（向後相容）
    if "alert_sent" not in cost_data[month_key]:
        cost_data[month_key]["alert_sent"] = False

    prev_total = cost_data[month_key]["total_usd"]
    cost_data[month_key]["total_usd"] += total_cost_usd
    cost_data[month_key]["runs"].append({
        "date": today_str,
        "mode": mode,
        "cost_usd": round(total_cost_usd, 5),
        "stocks": stock_count,
    })

    # 留最近 6 個月
    sorted_months = sorted(cost_data.keys(), reverse=True)
    cost_data = {k: cost_data[k] for k in sorted_months[:6]}

    month_total = cost_data[month_key]["total_usd"]
    log.info(f"💰 本月累計：${month_total:.4f} (~NT${month_total * 32:.0f})")

    # 第一次跨過閾值才通知（避免每天洗版）
    if month_total > THRESHOLD_USD and not cost_data[month_key]["alert_sent"]:
        log.warning(f"⚠️ 本月成本已超過 ${THRESHOLD_USD} 閾值！送出 Discord 通知")
        if notify_cost_threshold(month_key, month_total, THRESHOLD_USD):
            cost_data[month_key]["alert_sent"] = True

    with open(COST_FILE, 'w', encoding='utf-8') as f:
        json.dump(cost_data, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════
# Part 6: 主流程
# ═══════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-detail", action="store_true", help="強制跑詳細版")
    parser.add_argument("--force-daily", action="store_true", help="強制跑低版本")
    parser.add_argument("--dry-run", action="store_true", help="不呼叫 API、不寫 Notion，只跑流程")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 檔（測試用）")
    parser.add_argument("--confirm", action="store_true", help="確認跑超過 MAX_STOCKS_PER_RUN 數量的名單")
    parser.add_argument("--max-stocks", type=int, default=0,
                        help="本次最大分析檔數（0=用環境變數 MAX_STOCKS_PER_RUN，預設 15）")
    parser.add_argument("--min-strength", type=int, default=-1,
                        help="只分析強度 >= N 的股票（0=全部、預設 4）")
    args = parser.parse_args()

    # 1. 讀名單
    today_list_full = load_today_list()
    if not today_list_full:
        log.warning("今日新高名單為空，跳過")
        return 0

    original_count = len(today_list_full)

    # ─── 強度過濾（A 方案：只跑強度 4-5）───────────
    min_strength = args.min_strength if args.min_strength >= 0 else int(
        os.environ.get("MIN_STRENGTH", "4")
    )
    if min_strength > 0:
        today_list = [s for s in today_list_full if s.get("strength", 0) >= min_strength]
        filtered_out = original_count - len(today_list)
        if filtered_out > 0:
            log.info(f"強度過濾：保留 {len(today_list)}/{original_count} 檔"
                     f"（強度 >= {min_strength}），過濾掉 {filtered_out} 檔弱勢標的")
    else:
        today_list = today_list_full

    if not today_list:
        log.warning(f"強度 >= {min_strength} 的股票數為 0，跳過")
        notify_empty_after_filter(original_count, min_strength)
        return 0

    if args.limit > 0:
        today_list = today_list[:args.limit]
        log.info(f"--limit {args.limit} 模式：只跑前 {args.limit} 檔")

    # ─── 安全閘門：上限檢查 ──────────────────────────
    max_stocks = args.max_stocks if args.max_stocks > 0 else int(
        os.environ.get("MAX_STOCKS_PER_RUN", "15")
    )
    if len(today_list) > max_stocks:
        if not args.confirm:
            est_cost = len(today_list) * 0.027
            log.error("=" * 60)
            log.error(f"⚠️  名單檔數 {len(today_list)} 超過上限 {max_stocks}")
            log.error(f"   detail 模式預估成本：${est_cost:.2f} USD"
                      f" (~NT${est_cost * 32:.0f})")
            log.error(f"   選項：")
            log.error(f"   (a) 加 --confirm 確認跑全部")
            log.error(f"   (b) 加 --max-stocks N 限制檔數")
            log.error(f"   (c) 加 --limit N 只跑前 N 檔")
            log.error(f"   (d) 加 --min-strength 5 提高門檻")
            log.error("=" * 60)
            # 送 Discord 通知（不會 raise）
            notify_blocked_overlimit(len(today_list), max_stocks, est_cost)
            return 1
        else:
            log.warning(f"⚠️  --confirm 已確認，跑全部 {len(today_list)} 檔")

    today_codes = {s["code"] for s in today_list}

    # 2. 決定模式
    yesterday_state = load_yesterday_state()
    if args.force_detail:
        mode = "detail"
    elif args.force_daily:
        mode = "daily"
    else:
        mode = determine_mode(today_codes, yesterday_state)

    log.info(f"模式：{mode}，名單檔數：{len(today_list)}")

    # 3. 載入輔助資料
    foreign_data = {}
    macd_data = {}
    try:
        if FOREIGN_TOP_FILE.exists():
            with open(FOREIGN_TOP_FILE, encoding='utf-8') as f:
                foreign_data = json.load(f)
        if MACD_SIGNAL_FILE.exists():
            with open(MACD_SIGNAL_FILE, encoding='utf-8') as f:
                macd_data = json.load(f)
    except Exception as e:
        log.warning(f"載入輔助資料失敗：{e}")

    # 4. 並行抓資料
    log.info("抓取技術面資料中（並行 5 條）...")
    with ThreadPoolExecutor(max_workers=5) as ex:
        stock_data_list = list(ex.map(
            lambda s: gather_stock_data(s, foreign_data, macd_data),
            today_list
        ))

    # 5. 並行呼叫 Claude（可中斷版本）
    log.info(f"呼叫 Claude API（{mode}, 並行 3 條）...")
    analyses_with_usage = []
    interrupted = False

    with ThreadPoolExecutor(max_workers=3) as ex:
        # 一次只丟入 max_workers 個任務，跑完才丟下一個
        # 這樣 Ctrl+C 時最多浪費 3 個進行中的請求
        pending = list(stock_data_list)
        active_futures = {}

        try:
            # 先丟初始批次
            while pending and len(active_futures) < 3:
                sd = pending.pop(0)
                fut = ex.submit(analyze_stock, sd, mode, args.dry_run)
                active_futures[fut] = sd

            # 主迴圈：完成一個就丟下一個
            while active_futures:
                done = next(as_completed(active_futures))
                analyses_with_usage.append(done.result())
                del active_futures[done]

                if pending:
                    sd = pending.pop(0)
                    fut = ex.submit(analyze_stock, sd, mode, args.dry_run)
                    active_futures[fut] = sd

        except KeyboardInterrupt:
            interrupted = True
            log.warning("=" * 60)
            log.warning(f"⚠️  收到 Ctrl+C")
            log.warning(f"   已完成：{len(analyses_with_usage)} 檔")
            log.warning(f"   進行中（會繼續跑完）：{len(active_futures)} 檔")
            log.warning(f"   未開始（已取消）：{len(pending)} 檔")
            log.warning("=" * 60)
            # 取消還沒開始的 futures
            for fut in active_futures:
                fut.cancel()
            # 等進行中的跑完（避免結果遺失）
            for fut in as_completed(active_futures, timeout=30):
                try:
                    analyses_with_usage.append(fut.result())
                except Exception as e:
                    log.warning(f"任務取消或失敗：{e}")

    analyses = [a for a, _ in analyses_with_usage]
    usages = [u for _, u in analyses_with_usage]

    # 排序回原順序
    code_order = [s["code"] for s in today_list]
    code_to_idx = {c: i for i, c in enumerate(code_order)}
    analyses.sort(key=lambda a: code_to_idx.get(a.get("code"), 999))

    # 6. 計算成本
    total_cost = sum(calculate_cost(u) for u in usages)
    log.info(f"本次成本：${total_cost:.5f} (~NT${total_cost * 32:.2f})")

    # 6.5 檢查 API 失敗率
    failed = sum(1 for a in analyses if "error" in a)
    if analyses and failed >= len(analyses) * 0.5:
        log.warning(f"API 失敗率過高：{failed}/{len(analyses)}")
        notify_api_failed(failed, len(analyses), mode)

    if interrupted and not analyses:
        log.error("被中斷且無任何結果，跳過 Notion 寫入")
        return 1

    # 7. 寫 Notion
    today_str = datetime.now().strftime("%Y-%m-%d")
    now_iso = datetime.now().isoformat(timespec='seconds')
    summary_meta = {"updated_at": now_iso, "mode": mode}

    if interrupted:
        # 中斷的話標題加註，避免覆蓋掉「正常完成」的舊報告
        title_suffix = f"（部分 {len(analyses)}/{len(today_list)}）"
    else:
        title_suffix = ""

    if mode == "daily":
        title = f"TSWE 每日狀態 {today_str}{title_suffix}"
        blocks = render_daily_blocks(analyses, summary_meta)
    else:
        title = f"TSWE 詳細研究 {today_str}{title_suffix}"
        blocks = render_detail_blocks(analyses, summary_meta)

    if args.dry_run:
        log.info(f"[dry-run] 跳過 Notion 寫入。標題：{title}，blocks：{len(blocks)}")
        page_url = "https://notion.so/dry-run"
        page_id = "dry-run"
    else:
        try:
            if mode == "daily" and not interrupted:
                log.info(f"覆寫每日狀態頁（內容日期：{today_str}）")
                page_id, page_url = upsert_daily_page(blocks, today_str)
            else:
                # detail 模式 或 daily 但被中斷 → 都建立新頁，避免覆蓋掉好的舊報告
                log.info(f"建立新頁：{title}")
                page_id, page_url = create_notion_page(title, blocks)
            log.info(f"✓ Notion 完成：{page_url}")
        except Exception as e:
            log.error(f"❌ Notion 寫入失敗：{e}")
            notify_notion_failed(str(e), mode)
            # 不要直接 return，讓後面 cost monitor 還能跑、log 還能寫
            page_id = "notion-failed"
            page_url = ""

    # 8. 更新 state / latest / log
    if not args.dry_run:
        # 中斷時不要更新 state，下次還會偵測到「名單變動」自動重跑
        if not interrupted:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    "codes": sorted(today_codes),
                    "updated_at": now_iso,
                    "mode": mode,
                }, f, ensure_ascii=False, indent=2)

        with open(LATEST_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "title": title,
                "url": page_url,
                "page_id": page_id,
                "mode": mode,
                "stock_count": len(today_list),
                "analyzed_count": len(analyses),
                "interrupted": interrupted,
                "cost_usd": round(total_cost, 5),
                "updated_at": now_iso,
            }, f, ensure_ascii=False, indent=2)

        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                "date": today_str,
                "mode": mode,
                "stocks": len(today_list),
                "analyzed": len(analyses),
                "interrupted": interrupted,
                "url": page_url,
                "cost_usd": round(total_cost, 5),
            }, ensure_ascii=False) + '\n')

        update_cost_monitor(today_str, mode, total_cost, len(analyses))

    log.info("✓ 完成" if not interrupted else "✓ 已中斷儲存")
    return 0 if not interrupted else 130  # 130 是被 SIGINT 中斷的慣例 exit code


if __name__ == "__main__":
    sys.exit(main())
