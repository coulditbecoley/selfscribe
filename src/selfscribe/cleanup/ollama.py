"""Cleanup via a local Ollama model — fully offline, $0 marginal cost."""

import httpx

from selfscribe.cleanup import SYSTEM_PROMPT, CleanupError


def clean(text: str, base_url: str, model: str, timeout_s: float = 60.0) -> str:
    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/api/chat",
            json={
                "model": model,
                "stream": False,
                "options": {"temperature": 0.0},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
            },
            timeout=timeout_s,
        )
    except httpx.ConnectError as exc:
        raise CleanupError(
            f"Ollama not reachable at {base_url} — is it installed and running?"
        ) from exc
    if response.status_code >= 400:
        raise CleanupError(f"Ollama cleanup failed ({response.status_code}): {response.text[:200]}")
    cleaned = response.json().get("message", {}).get("content", "").strip()
    if not cleaned:
        raise CleanupError("Ollama cleanup returned empty text.")
    return cleaned
