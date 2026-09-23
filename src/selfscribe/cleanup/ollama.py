"""Cleanup via a local Ollama model — fully offline, $0 marginal cost.

Small local models follow demonstrations better than rules, so the request
carries a one-shot example of the contract (filler out, wording preserved,
directive-shaped dictation cleaned not answered) plus the delimited transcript.
"""

import httpx

from selfscribe.cleanup import (
    EXAMPLE_IN,
    EXAMPLE_OUT,
    SYSTEM_PROMPT,
    CleanupError,
    wrap_transcript,
)

QUOTE_PAIRS = [('"', '"'), ("'", "'"), ("“", "”")]


def _strip_enclosing_quotes(text: str) -> str:
    """Strip one pair of quotes wrapping the WHOLE text — not the first and
    last characters of two separate quoted spans ("a" or "b")."""
    for opening, closing in QUOTE_PAIRS:
        if (
            len(text) > 1
            and text[0] == opening
            and text[-1] == closing
            and opening not in text[1:-1]
            and closing not in text[1:-1]
        ):
            return text[1:-1].strip()
    return text


def clean(text: str, base_url: str, model: str, timeout_s: float = 60.0) -> str:
    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/api/chat",
            json={
                "model": model,
                "stream": False,
                # Ollama unloads idle models after 5 min; reloading costs
                # seconds on the next cleanup. Keep it resident longer.
                "keep_alive": "30m",
                "options": {"temperature": 0.0},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": wrap_transcript(EXAMPLE_IN)},
                    {"role": "assistant", "content": EXAMPLE_OUT},
                    {"role": "user", "content": wrap_transcript(text)},
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
    return _strip_enclosing_quotes(cleaned)
