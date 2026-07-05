import numpy as np
import pytest

import selfscribe.app as app_module
from selfscribe.app import process_clip
from selfscribe.audio import SAMPLE_RATE, Clip
from selfscribe.config import Config
from selfscribe.stt import Transcript


@pytest.fixture
def clip():
    return Clip(pcm=np.zeros(SAMPLE_RATE, dtype=np.int16))


@pytest.fixture
def injections(monkeypatch):
    calls = []
    monkeypatch.setattr(
        app_module,
        "transcribe_clip",
        lambda clip, cfg: Transcript(text="  spoken words  ", ms=42.0, backend="groq"),
    )
    return calls


def make_inject(calls):
    return lambda text, press_enter=False: calls.append((text, press_enter))


def test_send_target_presses_enter(clip, injections):
    cfg = Config(groq_api_key="k")
    out = process_clip(clip, "send", cfg, inject=make_inject(injections))
    assert out == "spoken words"
    assert injections == [("spoken words", True)]


def test_dictate_target_never_presses_enter(clip, injections):
    cfg = Config(groq_api_key="k")
    process_clip(clip, "dictate", cfg, inject=make_inject(injections))
    assert injections == [("spoken words", False)]


def test_empty_transcript_injects_nothing(clip, monkeypatch):
    monkeypatch.setattr(
        app_module, "transcribe_clip", lambda c, cfg: Transcript(text="  ", ms=1.0, backend="groq")
    )
    calls = []
    out = process_clip(clip, "send", Config(groq_api_key="k"), inject=make_inject(calls))
    assert out is None
    assert calls == []


def test_send_path_stays_raw_even_with_cleanup_backend(clip, injections, monkeypatch):
    """Design decision #2: Claude Code path sends the raw transcript."""
    seen = []

    def spy_clean(text, cfg, target):
        seen.append(target)
        return "CLEANED"

    monkeypatch.setattr(app_module, "clean_text", spy_clean)
    cfg = Config(groq_api_key="k", anthropic_api_key="a", cleanup_backend="haiku")
    process_clip(clip, "send", cfg, inject=make_inject(injections))
    assert seen == []  # cleanup never invoked for send
    assert injections == [("spoken words", True)]

    process_clip(clip, "dictate", cfg, inject=make_inject(injections))
    assert seen == ["dictate"]  # dictate path cleans
    assert injections[-1] == ("CLEANED", False)
