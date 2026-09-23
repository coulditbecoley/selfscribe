"""Groq Whisper transcription — the primary, fast STT backend.

Request shape proven in the HitList voice spike (whisper-large-v3 there,
-turbo here for speed). The free tier caps at ~20 req/min: a 429 gets a
short backoff honoring Retry-After (capped), then a clear one-line error.
A dropped keep-alive connection or a 5xx retries; a timeout does not (the
caller falls back to the local backend instead of waiting again).
"""

import time

import httpx

from selfscribe.audio import Clip
from selfscribe.stt import BackendUnavailable, Transcript, TranscriptionError

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_MODEL = "whisper-large-v3-turbo"
MAX_TRIES = 3
BACKOFF_S = 2.0
MAX_RETRY_AFTER_S = 5.0  # never stall the pipeline on a long Retry-After

_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    """Keep-alive client: skips the TCP+TLS handshake on repeat utterances."""
    global _client
    if _client is None:
        _client = httpx.Client(timeout=30.0)
    return _client


def warm() -> None:
    """Open (or refresh) the pooled connection while the user is still
    talking, so the real upload skips the TCP+TLS handshake after idle."""
    _get_client().head(GROQ_TRANSCRIPTION_URL, timeout=5.0)


def transcribe(
    clip: Clip,
    api_key: str,
    initial_prompt: str = "",
    model: str = DEFAULT_MODEL,
    language: str = "en",
    timeout_s: float = 15.0,
    _sleep=time.sleep,
) -> Transcript:
    """Send a trimmed clip to Groq; return text + latency."""
    if not api_key:
        raise TranscriptionError("Groq API key missing — set [keys].groq in your config.")
    data = {"model": model, "response_format": "json", "language": language}
    if initial_prompt:
        data["prompt"] = initial_prompt

    wav = clip.wav_bytes()
    started = time.perf_counter()
    for attempt in range(1, MAX_TRIES + 1):
        try:
            response = _get_client().post(
                GROQ_TRANSCRIPTION_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": ("clip.wav", wav, "audio/wav")},
                data=data,
                timeout=timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise BackendUnavailable(f"Groq timed out after {timeout_s:.0f}s.") from exc
        except httpx.TransportError as exc:
            # usually a keep-alive connection the server already closed
            if attempt == MAX_TRIES:
                raise BackendUnavailable(
                    f"Groq unreachable ({type(exc).__name__}): check your connection."
                ) from exc
            continue
        if response.status_code == 429:
            if attempt == MAX_TRIES:
                raise BackendUnavailable(
                    "Groq rate limit hit (429, free tier is ~20 req/min) — "
                    "wait a few seconds and dictate again."
                )
            _sleep(_retry_delay(response.headers.get("retry-after"), attempt))
            continue
        if response.status_code >= 500 and attempt < MAX_TRIES:
            _sleep(0.5 * attempt)
            continue
        if response.status_code == 401:
            raise TranscriptionError("Groq rejected the API key (401) — check [keys].groq.")
        if response.status_code >= 500:
            raise BackendUnavailable(f"Groq server error ({response.status_code}).")
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


def _retry_delay(retry_after: str | None, attempt: int) -> float:
    try:
        delay = float(retry_after) if retry_after else BACKOFF_S * attempt
    except ValueError:  # HTTP-date form: not worth parsing for a dictation retry
        delay = BACKOFF_S * attempt
    return min(delay, MAX_RETRY_AFTER_S)
