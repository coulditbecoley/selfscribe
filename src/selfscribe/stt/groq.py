"""Groq Whisper transcription — the primary, fast STT backend.

Request shape proven in the HitList voice spike (whisper-large-v3 there,
-turbo here for speed). The free tier caps at ~20 req/min: a 429 gets a
short backoff honoring Retry-After, then a clear one-line error.
"""

import time

import httpx

from selfscribe.audio import Clip
from selfscribe.stt import Transcript, TranscriptionError

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_MODEL = "whisper-large-v3-turbo"
MAX_TRIES = 3
BACKOFF_S = 2.0

_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    """Keep-alive client: skips the TCP+TLS handshake on repeat utterances."""
    global _client
    if _client is None:
        _client = httpx.Client(timeout=30.0)
    return _client


def transcribe(
    clip: Clip,
    api_key: str,
    initial_prompt: str = "",
    model: str = DEFAULT_MODEL,
    language: str = "en",
    timeout_s: float = 30.0,
    _sleep=time.sleep,
) -> Transcript:
    """Send a trimmed clip to Groq; return text + latency."""
    if not api_key:
        raise TranscriptionError("Groq API key missing — set [keys].groq in your config.")
    data = {"model": model, "response_format": "json", "language": language}
    if initial_prompt:
        data["prompt"] = initial_prompt

    started = time.perf_counter()
    for attempt in range(1, MAX_TRIES + 1):
        response = _get_client().post(
            GROQ_TRANSCRIPTION_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("clip.wav", clip.wav_bytes(), "audio/wav")},
            data=data,
            timeout=timeout_s,
        )
        if response.status_code == 429:
            if attempt == MAX_TRIES:
                raise TranscriptionError(
                    "Groq rate limit hit (429, free tier is ~20 req/min) — "
                    "wait a few seconds and dictate again."
                )
            retry_after = response.headers.get("retry-after")
            _sleep(float(retry_after) if retry_after else BACKOFF_S * attempt)
            continue
        if response.status_code == 401:
            raise TranscriptionError("Groq rejected the API key (401) — check [keys].groq.")
        if response.status_code >= 400:
            raise TranscriptionError(
                f"Groq transcription failed ({response.status_code}): {response.text[:200]}"
            )
        elapsed_ms = (time.perf_counter() - started) * 1000
        return Transcript(
            text=response.json().get("text", "").strip(),
            ms=elapsed_ms,
            backend="groq",
        )
    raise TranscriptionError("Groq transcription failed after retries.")
