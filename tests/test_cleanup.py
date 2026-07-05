import httpx
import pytest

from selfscribe.cleanup import CleanupError, get_cleaner
from selfscribe.cleanup.haiku import clean as haiku_clean
from selfscribe.cleanup.ollama import clean as ollama_clean
from selfscribe.config import Config

FILLER_WORDS = ("um", "uh", "you know", "i mean")


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


def test_get_cleaner_off_returns_none():
    assert get_cleaner(Config(cleanup_backend="off")) is None


def test_haiku_request_shape_and_extraction(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse(200, {"content": [{"type": "text", "text": " Cleaned. "}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = haiku_clean("um so cleaned", "sk-ant-x")
    assert out == "Cleaned."
    body = captured["json"]
    assert body["model"].startswith("claude-haiku-4-5")
    assert body["temperature"] == 0.0
    assert "Output ONLY the cleaned text" in body["system"]
    assert body["messages"] == [{"role": "user", "content": "um so cleaned"}]


def test_haiku_401_and_empty(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, **kw: FakeResponse(401))
    with pytest.raises(CleanupError) as exc:
        haiku_clean("x", "sk-bad")
    assert "401" in str(exc.value)
    monkeypatch.setattr(httpx, "post", lambda url, **kw: FakeResponse(200, {"content": []}))
    with pytest.raises(CleanupError):
        haiku_clean("x", "sk-ant-x")


def test_haiku_missing_key():
    with pytest.raises(CleanupError):
        haiku_clean("x", "")


def test_ollama_extraction_and_connect_error(monkeypatch):
    monkeypatch.setattr(
        httpx, "post", lambda url, **kw: FakeResponse(200, {"message": {"content": " ok "}})
    )
    assert ollama_clean("x", "http://localhost:11434", "m") == "ok"

    def raise_connect(url, **kw):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", raise_connect)
    with pytest.raises(CleanupError) as exc:
        ollama_clean("x", "http://localhost:11434", "m")
    assert "Ollama not reachable" in str(exc.value)


def test_app_clean_text_falls_back_to_raw(monkeypatch):
    from selfscribe import app as app_module

    cfg = Config(cleanup_backend="haiku", anthropic_api_key="k", groq_api_key="g")

    def boom(url, **kw):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    assert app_module.clean_text("raw words", cfg, "dictate") == "raw words"


@pytest.mark.live
def test_live_haiku_cleans_filler_faithfully():
    """SS-12 AC: filler-heavy dictation comes back clean and faithful."""
    from selfscribe.config import load_config

    cfg = load_config()
    if not cfg.anthropic_api_key:
        pytest.skip("no anthropic key")
    raw = (
        "um so like can you uh send the report to the team by friday "
        "you know because uh the deadline is monday"
    )
    cleaned = haiku_clean(raw, cfg.anthropic_api_key)
    print(f"\ncleaned: {cleaned!r}")
    low = f" {cleaned.lower()} "
    for filler in FILLER_WORDS:
        assert f" {filler} " not in low, f"filler {filler!r} survived: {cleaned!r}"
    assert "send the report to the team" in cleaned.lower()
    assert "friday" in cleaned.lower()
    assert "monday" in cleaned.lower()


@pytest.mark.live
def test_live_haiku_punctuates_question_without_answering():
    """SS-12 AC: a dictated question is punctuated, NOT answered."""
    from selfscribe.config import load_config

    cfg = load_config()
    if not cfg.anthropic_api_key:
        pytest.skip("no anthropic key")
    cleaned = haiku_clean("um what time is the meeting tomorrow", cfg.anthropic_api_key)
    print(f"\ncleaned: {cleaned!r}")
    assert cleaned.rstrip().endswith("?")
    assert "meeting" in cleaned.lower()
    # an answer would add content; the cleaned text must stay about as short
    assert len(cleaned) <= len("What time is the meeting tomorrow?") + 10
