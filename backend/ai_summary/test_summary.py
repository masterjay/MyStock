"""手動測試 AI 大盤摘要 — 在 terminal 看 streaming 跑出來。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_summary.context_builder import build_market_context
from ai_summary.prompt_templates import SYSTEM_PROMPT, build_market_user_prompt
from ai_summary.claude_client import stream_summary


def main():
    print("📊 抓取大盤資料中...\n")
    ctx = build_market_context()
    if ctx is None:
        print("❌ 找不到大盤資料,DB 可能是空的")
        return

    print(f"✅ 取得 {ctx['date']} 的資料\n")
    print("=" * 60)
    print("📤 送給 Claude 的 user prompt:")
    print("=" * 60)
    user_prompt = build_market_user_prompt(ctx)
    print(user_prompt)
    print()
    print("=" * 60)
    print("🤖 Claude 生成摘要中(streaming):")
    print("=" * 60)

    for chunk in stream_summary(SYSTEM_PROMPT, user_prompt):
        print(chunk, end="", flush=True)
    print("\n")
    print("=" * 60)
    print("✅ 完成")


if __name__ == "__main__":
    main()
