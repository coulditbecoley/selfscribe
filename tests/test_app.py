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


def test_per_app_profile_forces_cleanup_off(clip, monkeypatch):
    """Focused app in [cleanup.apps]=false suppresses cleanup even on the
    dictate path where the default is on."""
    monkeypatch.setattr(app_module, "foreground_process_name", lambda: "code.exe")
    monkeypatch.setattr(app_module, "is_terminal_focused", lambda: False)
    seen = []
    monkeypatch.setattr(
        app_module,
        "transcribe_clip",
        lambda c, cfg: Transcript(text="um so hello", ms=1.0, backend="groq"),
    )
    monkeypatch.setattr(app_module, "clean_text", lambda t, cfg, tgt: seen.append(tgt) or "CLEAN")
    cfg = Config(groq_api_key="k", anthropic_api_key="a", cleanup_backend="haiku",
                 cleanup_apps={"code.exe": False})
    calls = []
    process_clip(clip, "dictate", cfg, inject=make_inject(calls))
    assert seen == []  # cleanup skipped for the editor
    assert calls == [("um so hello", False)]


def test_per_app_profile_forces_cleanup_on_for_send(clip, monkeypatch):
    """Focused app mapped true cleans even the send target (default raw)."""
    monkeypatch.setattr(app_module, "foreground_process_name", lambda: "slack.exe")
    monkeypatch.setattr(
        app_module,
        "transcribe_clip",
        lambda c, cfg: Transcript(text="um hello there", ms=1.0, backend="groq"),
    )
    monkeypatch.setattr(app_module, "clean_text", lambda t, cfg, tgt: "cleaned")
    cfg = Config(groq_api_key="k", anthropic_api_key="a", cleanup_backend="haiku",
                 cleanup_apps={"slack.exe": True})
    calls = []
    process_clip(clip, "send", cfg, inject=make_inject(calls))
    assert calls == [("cleaned", True)]


def test_cleaned_text_gets_vocab_repair(clip, monkeypatch):
    """The cleanup LLM may re-case vocab terms; the final text is repaired."""
    monkeypatch.setattr(
        app_module,
        "transcribe_clip",
        lambda c, cfg: Transcript(text="open HitList now", ms=1.0, backend="groq"),
    )
    monkeypatch.setattr(app_module, "clean_text", lambda t, cfg, target: "Open Hitlist now.")
    calls = []
    cfg = Config(groq_api_key="k", anthropic_api_key="a", cleanup_backend="haiku")
    process_clip(clip, "dictate", cfg, inject=make_inject(calls))
    assert calls == [("Open HitList now.", False)]


def test_dictate_path_applies_structural_commands(clip, monkeypatch):
    monkeypatch.setattr(app_module, "is_terminal_focused", lambda: False)
    monkeypatch.setattr(
        app_module,
        "transcribe_clip",
        lambda c, cfg: Transcript(text="first line new line second line", ms=1.0, backend="groq"),
    )
    calls = []
    process_clip(clip, "dictate", Config(groq_api_key="k"), inject=make_inject(calls))
    assert calls == [("first line\nsecond line", False)]


def test_send_path_never_applies_commands(clip, monkeypatch):
    """Claude Code path stays raw + single-line: 'new line' is literal words,
    and it never gains a newline that would submit early."""
    monkeypatch.setattr(
        app_module,
        "transcribe_clip",
        lambda c, cfg: Transcript(text="run tests new line then build", ms=1.0, backend="groq"),
    )
    calls = []
    process_clip(clip, "send", Config(groq_api_key="k"), inject=make_inject(calls))
    text, press_enter = calls[0]
    assert "\n" not in text
    assert text == "run tests new line then build"
    assert press_enter is True


def test_dictate_commands_suppressed_when_terminal_focused(clip, monkeypatch):
    """A newline pasted into a terminal submits that line; the dictate path is
    for text fields, so command newlines are suppressed when a terminal has
    focus (also blocks a compromised STT emitting 'new line')."""
    monkeypatch.setattr(app_module, "is_terminal_focused", lambda: True)
    monkeypatch.setattr(
        app_module,
        "transcribe_clip",
        lambda c, cfg: Transcript(text="rm files new line ok", ms=1.0, backend="groq"),
    )
    calls = []
    process_clip(clip, "dictate", Config(groq_api_key="k"), inject=make_inject(calls))
    text, _ = calls[0]
    assert "\n" not in text  # stays a single line in a terminal
    assert text == "rm files new line ok"


def test_commands_can_be_disabled(clip, monkeypatch):
    monkeypatch.setattr(app_module, "is_terminal_focused", lambda: False)
    monkeypatch.setattr(
        app_module,
        "transcribe_clip",
        lambda c, cfg: Transcript(text="a new line b", ms=1.0, backend="groq"),
    )
    calls = []
    process_clip(clip, "dictate", Config(groq_api_key="k", commands_enabled=False),
                 inject=make_inject(calls))
    assert calls == [("a new line b", False)]


def test_fake_recorder_goes_through_real_finish(tts_wav, tmp_path):
    """--fake-audio clips get the same trim/guard semantics as real ones."""
    import numpy as np

    from selfscribe.app import FakeRecorder
    from selfscribe.audio import Clip

    speech = tts_wav("testing one two three", "vad_speech")
    rec = FakeRecorder(str(speech))
    out = rec.stop()
    assert out is not None and out.duration_ms > 300

    silent = tmp_path / "silence.wav"
    silent.write_bytes(Clip(pcm=np.zeros(16000, dtype=np.int16)).wav_bytes())
    rec = FakeRecorder(str(silent))
    assert rec.stop() is None
    assert rec.discard_reason == "silence"


def test_fake_recorder_normalizes_odd_samplerates(tts_wav, tmp_path):
    """webrtcvad only accepts 8/16/32/48 kHz — a 44.1 kHz WAV must not error."""
    from selfscribe.app import FakeRecorder
    from selfscribe.audio import Clip, clip_from_wav_bytes, resample

    speech = clip_from_wav_bytes(tts_wav("testing one two three", "vad_speech").read_bytes())
    hi_rate = 44100
    hi_pcm = resample(speech.pcm, speech.samplerate, hi_rate)
    wav_44k = tmp_path / "hi.wav"
    wav_44k.write_bytes(Clip(pcm=hi_pcm, samplerate=hi_rate).wav_bytes())

    rec = FakeRecorder(str(wav_44k))
    out = rec.stop()
    assert out is not None
    assert out.samplerate == 16000
    assert out.duration_ms > 300
