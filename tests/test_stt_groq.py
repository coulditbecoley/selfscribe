import httpx
import numpy as np
import pytest
from conftest import FakeHttpClient, FakeResponse

import selfscribe.stt.groq as groq_mod
from selfscribe.audio import SAMPLE_RATE, Clip, clip_from_wav_bytes
from selfscribe.stt import TranscriptionError
from selfscribe.stt.groq import transcribe


def make_clip():
    return Clip(pcm=np.zeros(SAMPLE_RATE, dtype=np.int16))


def use_handler(monkeypatch, handler):
    monkeypatch.setattr(groq_mod, "_get_client", lambda: FakeHttpClient(handler))


def test_success_returns_text_and_latency(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(200, {"text": "  hello world  "})

    use_handler(monkeypatch, fake_post)
    result = transcribe(make_clip(), "gsk_x")
    assert result.text == "hello world"
    assert result.backend == "groq"
    assert result.ms >= 0
    assert captured["data"]["model"] == "whisper-large-v3-turbo"
    assert "prompt" not in captured["data"]


def test_initial_prompt_hook_is_sent(monkeypatch):
    captured = {}
    use_handler(
        monkeypatch,
        lambda url, **kw: (captured.update(kw), FakeResponse(200, {"text": "x"}))[1],
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

    use_handler(monkeypatch, fake_post)
    result = transcribe(make_clip(), "gsk_x", _sleep=sleeps.append)
    assert result.text == "recovered"
    assert sleeps == [1.5]


def test_429_exhausted_gives_one_line_error(monkeypatch):
    use_handler(monkeypatch, lambda url, **kw: FakeResponse(429))
    with pytest.raises(TranscriptionError) as exc:
        transcribe(make_clip(), "gsk_x", _sleep=lambda s: None)
    assert "429" in str(exc.value)
    assert "\n" not in str(exc.value)


def test_401_clear_message(monkeypatch):
    use_handler(monkeypatch, lambda url, **kw: FakeResponse(401))
    with pytest.raises(TranscriptionError) as exc:
        transcribe(make_clip(), "gsk_bad")
    assert "401" in str(exc.value)


def test_missing_key_rejected_before_network():
    with pytest.raises(TranscriptionError):
        transcribe(make_clip(), "")


def test_dropped_connection_retries(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.RemoteProtocolError("server closed the keep-alive connection")
        return FakeResponse(200, {"text": "ok"})

    use_handler(monkeypatch, fake_post)
    assert transcribe(make_clip(), "gsk_x").text == "ok"
    assert calls["n"] == 2


def test_timeout_fails_fast_without_retry(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, **kwargs):
        calls["n"] += 1
        raise httpx.ReadTimeout("slow")

    use_handler(monkeypatch, fake_post)
    with pytest.raises(TranscriptionError) as exc:
        transcribe(make_clip(), "gsk_x")
    assert "timed out" in str(exc.value)
    assert calls["n"] == 1


def test_5xx_retries_then_succeeds(monkeypatch):
    responses = [FakeResponse(503), FakeResponse(200, {"text": "back"})]
    use_handler(monkeypatch, lambda url, **kw: responses.pop(0))
    assert transcribe(make_clip(), "gsk_x", _sleep=lambda s: None).text == "back"


def test_retry_after_is_capped(monkeypatch):
    responses = [
        FakeResponse(429, headers={"retry-after": "120"}),
        FakeResponse(200, {"text": "x"}),
    ]
    sleeps = []
    use_handler(monkeypatch, lambda url, **kw: responses.pop(0))
    transcribe(make_clip(), "gsk_x", _sleep=sleeps.append)
    assert sleeps == [groq_mod.MAX_RETRY_AFTER_S]


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
