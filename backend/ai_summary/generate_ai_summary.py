"""
產生每日 AI 大盤摘要,寫成 JSON 給前端讀。

執行流程:
1. build_market_context() 從 DB 抓資料
2. 呼叫 Claude Haiku 生成摘要
3. 寫進 backend/data/ai_summary.json

可獨立執行(測試),也可被 run_daily.py import。
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# 讓 import 正常運作(不論從哪個目錄執行)
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_summary.context_builder import build_market_context
from ai_summary.prompt_templates import SYSTEM_PROMPT, build_market_user_prompt
from ai_summary.claude_client import client, MODEL

# 輸出檔案路徑
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "ai_summary.json"


def generate_summary_text(system_prompt: str, user_prompt: str, max_tokens: int = 800) -> str:
    """非 streaming 版本,一次拿完整文字。production 用這個比較單純。"""
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    # response.content 是 list of ContentBlock,我們只要 text
    return "".join(block.text for block in response.content if block.type == "text")


def generate_and_save() -> dict:
    """主流程:組 context → 呼叫 Claude → 存 JSON。回傳寫入的資料。"""
    print(f"[{datetime.now().isoformat()}] 開始生成 AI 大盤摘要...")

    # 1. 抓資料
    ctx = build_market_context()
    if ctx is None:
        print("❌ 找不到大盤資料,跳過 AI 摘要")
        return None

    print(f"✅ 取得 {ctx['date']} 的資料")

    # 2. 組 prompt
    user_prompt = build_market_user_prompt(ctx)

    # 3. 呼叫 Claude
    try:
        summary = generate_summary_text(SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        print(f"❌ Claude API 呼叫失敗:{e}")
        return None

    print(f"✅ 摘要生成完成,長度 {len(summary)} 字元")

    # 4. 組 JSON 結構
    result = {
        "date": ctx["date"],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model": MODEL,
        "summary": summary,
        # 把原始 context 也存進去,方便除錯 / 前端做 fallback
        "context_snapshot": {
            "taiex_close": ctx["taiex_close"],
            "taiex_change_pct": ctx["taiex_change_pct"],
            "up_count": ctx["up_count"],
            "down_count": ctx["down_count"],
            "foreign_diff": ctx["foreign_diff"],
            "trust_diff": ctx["trust_diff"],
        },
    }

    # 5. 寫檔(用 utf-8 + 美化排版)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ 已寫入 {OUTPUT_PATH}")
    return result


if __name__ == "__main__":
    result = generate_and_save()
    if result:
        print("\n" + "=" * 60)
        print("📋 生成的摘要:")
        print("=" * 60)
        print(result["summary"])
