"""Cleanup via Claude Haiku 4.5 — fast, cheap, low temperature."""

import httpx

from selfscribe.cleanup import SYSTEM_PROMPT, CleanupError

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_VERSION = "2023-06-01"


def clean(text: str, api_key: str, timeout_s: float = 15.0) -> str:
    if not api_key:
        raise CleanupError("Anthropic API key missing — set [keys].anthropic in your config.")
    response = httpx.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": max(1024, len(text)),
            "temperature": 0.0,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": text}],
        },
        timeout=timeout_s,
    )
    if response.status_code == 401:
        raise CleanupError("Anthropic rejected the API key (401) — check [keys].anthropic.")
    if response.status_code >= 400:
        raise CleanupError(f"Cleanup failed ({response.status_code}): {response.text[:200]}")
    blocks = response.json().get("content", [])
    cleaned = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
    if not cleaned:
        raise CleanupError("Cleanup returned empty text.")
    return cleaned
