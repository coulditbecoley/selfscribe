"""SS-18 security pass, as regression tests.

Covers: no secrets in the repo, keys never logged, no audio persisted,
telemetry schema can't leak content, clipboard restore, and (via the live
suite) offline guarantees for the local modes — see
test_stt_conformance.test_local_inference_is_offline and
test_cleanup.test_live_ollama_cleanup_quality_and_locality.
"""

import logging
import re
import subprocess
from pathlib import Path

import numpy as np
import pytest

import selfscribe.app as app_module
from selfscribe.audio import SAMPLE_RATE, Clip
from selfscribe.config import Config
from selfscribe.stt import Transcript

REPO = Path(__file__).parents[1]
KEY_PATTERNS = [re.compile(r"gsk_[A-Za-z0-9]{20,}"), re.compile(r"sk-ant-[A-Za-z0-9-]{20,}")]


def test_no_real_keys_in_tracked_files():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    offenders = []
    for rel in tracked:
        text = (REPO / rel).read_text(encoding="utf-8", errors="ignore")
        for pattern in KEY_PATTERNS:
            if pattern.search(text):
                offenders.append(rel)
    assert not offenders, f"key-shaped strings tracked in git: {offenders}"


def test_keys_never_reach_logs(monkeypatch, caplog):
    secret = "gsk_SUPERSECRET_TEST_VALUE_123456"
    cfg = Config(groq_api_key=secret)

    monkeypatch.setattr(
        app_module,
        "transcribe_clip",
        lambda clip, c: Transcript(text="hello there", ms=5.0, backend="groq"),
    )
    clip = Clip(pcm=np.ones(SAMPLE_RATE, dtype=np.int16))
    with caplog.at_level(logging.DEBUG, logger="selfscribe"):
        app_module.process_clip(clip, "send", cfg, inject=lambda t, press_enter: None)

    from selfscribe.stt import TranscriptionError

    def fail(clip, c):
        raise TranscriptionError("Groq rejected the API key (401) — check [keys].groq.")

    monkeypatch.setattr(app_module, "transcribe_clip", fail)
    monkeypatch.setattr(app_module, "soft_cue", lambda: None)
    app = app_module.App(cfg)
    with caplog.at_level(logging.DEBUG, logger="selfscribe"):
        app._process(clip, "send")

    assert secret not in caplog.text
    assert "SUPERSECRET" not in caplog.text


def test_error_messages_never_embed_key():
    import httpx

    from selfscribe.stt.groq import transcribe

    secret = "gsk_SUPERSECRET_TEST_VALUE_123456"

    class R:
        status_code = 401
        headers = {}
        text = "unauthorized"

        def json(self):
            return {}

    original = httpx.post
    httpx.post = lambda url, **kw: R()
    try:
        with pytest.raises(Exception) as exc:
            transcribe(Clip(pcm=np.zeros(SAMPLE_RATE, dtype=np.int16)), secret)
        assert secret not in str(exc.value)
    finally:
        httpx.post = original


def test_no_audio_files_written_by_pipeline(tmp_path, monkeypatch):
    """A full in-process utterance leaves zero audio artifacts on disk."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        app_module,
        "transcribe_clip",
        lambda clip, c: Transcript(text="spoken", ms=1.0, backend="groq"),
    )
    from selfscribe import telemetry

    monkeypatch.setattr(telemetry, "telemetry_path", lambda: tmp_path / "t.jsonl")
    clip = Clip(pcm=np.ones(SAMPLE_RATE, dtype=np.int16))
    app_module.process_clip(clip, "dictate", Config(groq_api_key="k"), inject=lambda t, **k: None)
    audio_files = [
        p for p in tmp_path.rglob("*") if p.suffix.lower() in (".wav", ".mp3", ".pcm", ".flac")
    ]
    assert audio_files == []
    telemetry_text = (tmp_path / "t.jsonl").read_text()
    assert "spoken" not in telemetry_text  # latency only, never content


def test_clipboard_restore_is_default_behavior():
    from selfscribe.inject import inject_text

    class Clip2:
        def __init__(self):
            self.value = "PRIOR"

        def paste(self):
            return self.value

        def copy(self, v):
            self.value = v

    class Keys:
        def paste(self, use_shift):
            pass

        def enter(self):
            pass

    clip = Clip2()
    result = inject_text(
        "new", keys=Keys(), clipboard=clip, sleep=lambda s: None, terminal_focused=False
    )
    assert clip.value == "PRIOR"
    assert result.clipboard_restored


@pytest.mark.live
def test_live_session_leaves_no_secrets_or_audio_traces(tts_wav):
    """AC: grep of all output after a real session shows zero secrets."""
    import os
    import time
    import tomllib

    from pynput import keyboard as pk

    user_cfg_path = Path.home() / ".selfscribe" / "config.toml"
    keys = tomllib.loads(user_cfg_path.read_text(encoding="utf-8")).get("keys", {})
    groq_key = keys.get("groq", "")
    if not groq_key:
        pytest.skip("no groq key")

    wav = tts_wav("security pass check one two three", "security_clip")
    audio_dir = wav.parent
    cfg_path = audio_dir / "security_config.toml"
    cfg_path.write_text(
        f'[keys]\ngroq = "{groq_key}"\n\n'
        '[hotkeys]\ndictate = "f13"\ndictate_send = "f14"\nmode = "hold"\n',
        encoding="utf-8",
    )
    telemetry_before = (Path.home() / ".selfscribe" / "telemetry.jsonl")
    telemetry_size = telemetry_before.stat().st_size if telemetry_before.exists() else 0

    env = dict(os.environ, SELFSCRIBE_CONFIG=str(cfg_path))
    proc = subprocess.Popen(
        [str(REPO / ".venv" / "Scripts" / "python.exe"), "-m", "selfscribe", "run",
         "--fake-audio", str(wav), "--no-tray"],
        env=env,
        cwd=str(REPO),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        assert "listening" in proc.stdout.readline()
        ctl = pk.Controller()
        ctl.press(pk.Key.f13)
        time.sleep(0.4)
        ctl.release(pk.Key.f13)
        time.sleep(3.0)
    finally:
        proc.kill()
        output = proc.stdout.read()
        cfg_path.unlink(missing_ok=True)

    assert groq_key not in output, "API key appeared in session logs"
    assert groq_key[8:24] not in output
    if telemetry_before.exists():
        new_telemetry = telemetry_before.read_text()[telemetry_size:]
        assert groq_key not in new_telemetry
        assert ".wav" not in new_telemetry
