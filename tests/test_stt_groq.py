import httpx
import numpy as np
import pytest

from selfscribe.audio import SAMPLE_RATE, Clip, clip_from_wav_bytes
from selfscribe.stt import TranscriptionError
from selfscribe.stt.groq import transcribe


def make_clip():
    return Clip(pcm=np.zeros(SAMPLE_RATE, dtype=np.int16))


class FakeResponse:
    def __init__(self, status_code, json_data=None, headers=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._json


def test_success_returns_text_and_latency(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(200, {"text": "  hello world  "})

    monkeypatch.setattr(httpx, "post", fake_post)
    result = transcribe(make_clip(), "gsk_x")
    assert result.text == "hello world"
    assert result.backend == "groq"
    assert result.ms >= 0
    assert captured["data"]["model"] == "whisper-large-v3-turbo"
    assert "prompt" not in captured["data"]


def test_initial_prompt_hook_is_sent(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        httpx, "post", lambda url, **kw: (captured.update(kw), FakeResponse(200, {"text": "x"}))[1]
    )
    transcribe(make_clip(), "gsk_x", initial_prompt="SelfScribe, HitList, Coley")
    assert captured["data"]["prompt"] == "SelfScribe, HitList, Coley"


def test_429_backs_off_then_succeeds(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    def fake_post(url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(429, headers={"retry-after": "1.5"})
        return FakeResponse(200, {"text": "recovered"})

    monkeypatch.setattr(httpx, "post", fake_post)
    result = transcribe(make_clip(), "gsk_x", _sleep=sleeps.append)
    assert result.text == "recovered"
    assert sleeps == [1.5]


def test_429_exhausted_gives_one_line_error(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, **kw: FakeResponse(429))
    with pytest.raises(TranscriptionError) as exc:
        transcribe(make_clip(), "gsk_x", _sleep=lambda s: None)
    assert "429" in str(exc.value)
    assert "\n" not in str(exc.value)


def test_401_clear_message(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, **kw: FakeResponse(401))
    with pytest.raises(TranscriptionError) as exc:
        transcribe(make_clip(), "gsk_bad")
    assert "401" in str(exc.value)


def test_missing_key_rejected_before_network():
    with pytest.raises(TranscriptionError):
        transcribe(make_clip(), "")


@pytest.mark.live
def test_live_roundtrip_accuracy_and_speed(tts_wav):
    """AC: a spoken sentence round-trips to accurate text, fast."""
    from selfscribe.config import load_config

    cfg = load_config()
    if not cfg.groq_api_key:
        pytest.skip("no Groq key configured")
    clip = clip_from_wav_bytes(
        tts_wav("testing one two three, the quick brown fox", "groq_live").read_bytes()
    )
    result = transcribe(clip, cfg.groq_api_key)
    text = result.text.lower()
    assert any(n in text for n in ("one two three", "1 2 3", "123"))
    assert "quick brown fox" in text
    print(f"\nlive groq: {result.ms:.0f}ms -> {result.text!r}")
    assert result.ms < 5000  # generous bound; typical is well under 1s
