"""Anthropic Claude API client for streaming summaries."""

import os
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(ENV_PATH)

api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise RuntimeError(f"ANTHROPIC_API_KEY not found in {ENV_PATH}")

client = Anthropic(api_key=api_key)
MODEL = "claude-haiku-4-5-20251001"


def stream_summary(system_prompt: str, user_prompt: str, max_tokens: int = 800):
    with client.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text
