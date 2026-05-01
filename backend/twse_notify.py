#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TSWE 通知模組（Discord Webhook）

用法：
    from tswe_notify import notify_discord, NotifyLevel

    notify_discord(
        title="名單超額未跑",
        message="33 檔超過上限 15",
        level=NotifyLevel.ERROR,
        details={"建議": "加 --confirm 參數", "log": "tail research_generator.log"}
    )

環境變數：
    DISCORD_WEBHOOK_URL  必填，Discord 頻道的 webhook URL
"""

import os
import json
import logging
from enum import Enum
from datetime import datetime
from typing import Optional

import requests

log = logging.getLogger(__name__)


class NotifyLevel(Enum):
    """通知等級。對應 Discord embed 的顏色"""
    SUCCESS = ("✅", 0x3FB950)   # 綠
    INFO    = ("ℹ️", 0x58A6FF)   # 藍
    WARNING = ("⚠️", 0xD29922)   # 黃
    ERROR   = ("🚨", 0xF85149)   # 紅 (台股紅 = 異常更醒目)
    COST    = ("💰", 0xD29922)   # 黃 (成本警告)


def notify_discord(
    title: str,
    message: str,
    level: NotifyLevel = NotifyLevel.INFO,
    details: Optional[dict] = None,
    silent_on_failure: bool = True,
) -> bool:
    """
    送 Discord 通知。
    silent_on_failure=True 表示通知失敗不會 raise（避免影響主流程）。
    回傳是否成功送出。
    """
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        log.warning("[notify] DISCORD_WEBHOOK_URL 未設定，略過通知")
        return False

    emoji, color = level.value

    # 組 embed fields（如果有 details）
    fields = []
    if details:
        for k, v in details.items():
            # Discord field 限制：name 256、value 1024
            fields.append({
                "name": str(k)[:256],
                "value": str(v)[:1024],
                "inline": False,
            })

    payload = {
        "embeds": [{
            "title": f"{emoji} {title}"[:256],
            "description": message[:4096],
            "color": color,
            "fields": fields[:25],  # Discord 最多 25 個 fields
            "footer": {"text": "TSWE 研究報告自動化"},
            "timestamp": datetime.now().isoformat(),
        }]
    }

    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        if r.status_code in (200, 204):
            log.info(f"[notify] ✓ Discord 通知已送：{title}")
            return True
        else:
            log.warning(f"[notify] Discord 回應 {r.status_code}：{r.text[:200]}")
            if not silent_on_failure:
                r.raise_for_status()
            return False
    except Exception as e:
        log.warning(f"[notify] Discord 通知失敗：{e}")
        if not silent_on_failure:
            raise
        return False


def notify_blocked_overlimit(stock_count: int, max_stocks: int, est_cost: float) -> bool:
    """名單超額被攔下"""
    return notify_discord(
        title="名單超額、未產生報告",
        message=f"今日新高雷達 **{stock_count} 檔**，超過上限 {max_stocks}，"
                f"程式已停止避免暴量花費。",
        level=NotifyLevel.ERROR,
        details={
            "預估成本（如果跑全部）": f"${est_cost:.2f} USD (~NT${est_cost * 32:.0f})",
            "處理方式": (
                "SSH 進 GCP，依需求選一：\n"
                "• `python3 research_report_generator.py --confirm`（跑全部）\n"
                "• `python3 research_report_generator.py --max-stocks 10`（限 10 檔）\n"
                "• `python3 research_report_generator.py --min-strength 5`（提高門檻）"
            ),
            "log 路徑": "`~/MyStock/backend/research_generator.log`",
        }
    )


def notify_notion_failed(error_msg: str, mode: str) -> bool:
    """Notion 寫入失敗"""
    return notify_discord(
        title="Notion 寫入失敗",
        message=f"研究報告已產生但寫入 Notion 失敗，內容沒留到 Notion。",
        level=NotifyLevel.ERROR,
        details={
            "模式": mode,
            "錯誤": f"```\n{error_msg[:500]}\n```",
            "可能原因": (
                "• Notion token 過期或失效\n"
                "• 父頁面 integration 授權被移除\n"
                "• Notion API 暫時故障"
            ),
            "處理方式": "檢查 .env 的 NOTION_TOKEN 與 NOTION_DAY_REPORT 是否正確",
        }
    )


def notify_api_failed(failed_count: int, total_count: int, mode: str) -> bool:
    """Claude API 失敗超過 50%"""
    return notify_discord(
        title="Claude API 失敗率過高",
        message=f"本次 {total_count} 檔分析中，**{failed_count} 檔失敗**（{failed_count/total_count*100:.0f}%）。",
        level=NotifyLevel.WARNING,
        details={
            "模式": mode,
            "可能原因": (
                "• ANTHROPIC_API_KEY 失效或額度不足\n"
                "• Claude API 服務異常\n"
                "• 並行限制觸發（rate limit）"
            ),
            "處理方式": (
                "1. 檢查 https://console.anthropic.com/settings/usage 餘額\n"
                "2. 看 `research_generator.log` 找具體錯誤訊息"
            ),
        }
    )


def notify_cost_threshold(month: str, total_usd: float, threshold_usd: float) -> bool:
    """本月成本超過閾值"""
    return notify_discord(
        title="本月成本超過閾值",
        message=f"**{month}** 累計 ${total_usd:.2f} USD"
                f" (~NT${total_usd * 32:.0f})，已超過閾值 ${threshold_usd}。",
        level=NotifyLevel.COST,
        details={
            "處理建議": (
                "• 確認名單檔數是否異常\n"
                "• 考慮提高 --min-strength 或調低 --max-stocks\n"
                "• 若認為是預期內，可調高 .env 的 COST_THRESHOLD_USD"
            ),
            "明細位置": "`~/MyStock/backend/data/new_high_research_cost.json`",
        }
    )


def notify_empty_after_filter(original: int, min_strength: int) -> bool:
    """強度過濾後沒有任何標的（不一定是錯，但提醒一下）"""
    return notify_discord(
        title="強度過濾後 0 檔",
        message=f"今日新高名單 {original} 檔，但強度 ≥ {min_strength} 的有 **0 檔**，本日跳過分析。",
        level=NotifyLevel.INFO,
        details={
            "說明": "可能是市場震盪、或門檻訂太嚴。如果連續多天 0 檔，考慮調降 MIN_STRENGTH。",
        }
    )


# ─── 自我測試（直接跑這檔可以發測試訊息）─────────────────────
if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        load_dotenv(Path(__file__).resolve().parent / ".env")
    except ImportError:
        pass

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(message)s')

    print("發送 Discord 測試訊息...")
    ok = notify_discord(
        title="TSWE 通知模組測試",
        message="如果你看到這則訊息，表示 Discord webhook 已正確設定 ✅",
        level=NotifyLevel.SUCCESS,
        details={
            "時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "下一步": "可以開始跑 research_report_generator.py 了",
        }
    )
    print("✓ 測試成功" if ok else "✗ 測試失敗，檢查 DISCORD_WEBHOOK_URL")
