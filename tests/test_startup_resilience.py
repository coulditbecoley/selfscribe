"""SS-15: start-at-login shortcut + the loop surviving failures."""

import sys

import numpy as np
import pytest

from selfscribe import startup
from selfscribe.app import App
from selfscribe.audio import SAMPLE_RATE, Clip, Recorder
from selfscribe.config import Config


@pytest.mark.skipif(sys.platform != "win32", reason="Windows shortcut/mutex API")
def test_startup_install_uninstall_roundtrip(tmp_path):
    link = startup.install(tmp_path)
    assert link.exists()
    assert startup.is_installed(tmp_path)
    assert startup.uninstall(tmp_path) is True
    assert not startup.is_installed(tmp_path)
    assert startup.uninstall(tmp_path) is False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows shortcut/mutex API")
def test_startup_install_survives_apostrophe_in_path(tmp_path):
    """Paths like C:\\Users\\O'Brien must not break the PowerShell script."""
    quoted_dir = tmp_path / "O'Brien"
    quoted_dir.mkdir()
    link = startup.install(quoted_dir)
    assert link.exists()
    assert startup.uninstall(quoted_dir) is True


def test_ps_quote_escapes_apostrophes():
    assert startup._ps_quote("C:\\Users\\O'Brien") == "'C:\\Users\\O''Brien'"


class FlakyRecorder(Recorder):
    """stop() raises once, then yields clips — simulates a device hiccup."""

    def __init__(self):
        super().__init__()
        self.calls = 0

    def start(self):
        pass

    def stop(self):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("device vanished")
        return Clip(pcm=np.ones(SAMPLE_RATE, dtype=np.int16))


def test_loop_survives_recorder_failure(monkeypatch):
    import selfscribe.app as app_module

    processed = []
    monkeypatch.setattr(app_module, "soft_cue", lambda: None)
    monkeypatch.setattr(
        app_module, "process_clip", lambda clip, target, cfg: processed.append(target)
    )
    app = App(Config(groq_api_key="k"), recorder=FlakyRecorder())

    app._on_stop("send")  # device error -> logged, no crash
    assert processed == []

    app._on_stop("send")  # next utterance works
    import time

    deadline = time.time() + 5
    while time.time() < deadline and not processed:
        time.sleep(0.05)
    assert processed == ["send"]


def test_loop_survives_transcription_failure(monkeypatch):
    """AC: after a forced transcription error the app still listens."""
    import selfscribe.app as app_module
    from selfscribe.stt import TranscriptionError

    cues = []
    monkeypatch.setattr(app_module, "soft_cue", lambda: cues.append(1))

    def boom(clip, target, cfg):
        raise TranscriptionError("Groq rejected the API key (401)")

    monkeypatch.setattr(app_module, "process_clip", boom)
    app = App(Config(groq_api_key="bad"))
    app._process(Clip(pcm=np.ones(SAMPLE_RATE, dtype=np.int16)), "send")  # no raise
    assert cues == [1]

    monkeypatch.setattr(app_module, "process_clip", lambda c, t, cfg: "ok")
    app._process(Clip(pcm=np.ones(SAMPLE_RATE, dtype=np.int16)), "send")  # recovered


def test_unexpected_error_also_survives(monkeypatch):
    import selfscribe.app as app_module

    monkeypatch.setattr(app_module, "soft_cue", lambda: None)

    def kaboom(clip, target, cfg):
        raise ValueError("totally unexpected")

    monkeypatch.setattr(app_module, "process_clip", kaboom)
    app = App(Config(groq_api_key="k"))
    app._process(Clip(pcm=np.ones(SAMPLE_RATE, dtype=np.int16)), "dictate")  # no raise


@pytest.mark.live
def test_live_forced_transcription_error_keeps_listening(tts_wav):
    """Real app subprocess + bad key: two presses -> two errors, still alive."""
    import os
    import subprocess
    import time
    from pathlib import Path

    from pynput import keyboard as pk

    scratch = Path(__file__).parent / "harness" / "audio"
    wav = tts_wav("testing one two three, the quick brown fox", "groq_live")
    bad_cfg = scratch / "bad_key_config.toml"
    bad_cfg.write_text(
        '[keys]\ngroq = "gsk_invalid_key_for_resilience_test"\n\n'
        '[hotkeys]\ndictate = "f13"\ndictate_send = "f14"\nmode = "hold"\n',
        encoding="utf-8",
    )
    env = dict(os.environ, SELFSCRIBE_CONFIG=str(bad_cfg))
    proc = subprocess.Popen(
        [os.path.join(".venv", "Scripts", "python.exe"), "-m", "selfscribe", "run",
         "--fake-audio", str(wav), "--no-tray"],
        env=env,
        cwd=str(Path(__file__).parents[1]),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        assert "listening" in proc.stdout.readline()
        ctl = pk.Controller()
        for _ in range(2):
            ctl.press(pk.Key.f14)
            time.sleep(0.4)
            ctl.release(pk.Key.f14)
            time.sleep(2.5)
        assert proc.poll() is None, "app died after transcription errors"
    finally:
        proc.kill()
        errors = proc.stdout.read()
        bad_cfg.unlink(missing_ok=True)
    assert errors.count("401") >= 2, f"expected two 401 errors, got: {errors!r}"
