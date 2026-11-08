"""Shared fixtures. TTS WAV generation (Windows SAPI, or `say` on macOS) seeds the audio
corpus used by the VAD tests and the SS-10 accuracy harness (cached on disk,
gitignored, reproducible)."""

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

AUDIO_DIR = Path(__file__).parent / "harness" / "audio"

_SYNTH_PS = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
    16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile('{path}', $fmt)
$s.Speak('{text}')
$s.Dispose()
"""


def synth_wav(text: str, name: str | None = None) -> Path:
    """Synthesize `text` to a cached 16 kHz mono WAV; return its path."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    slug = name or hashlib.sha1(text.encode()).hexdigest()[:12]
    path = AUDIO_DIR / f"{slug}.wav"
    if not path.exists():
        if sys.platform == "darwin":
            # macOS: the built-in `say` voice, written as 16 kHz mono 16-bit WAV
            cmd = ["say", "-o", str(path), "--data-format=LEI16@16000", "--file-format=WAVE", text]
        else:
            script = _SYNTH_PS.format(path=str(path), text=text.replace("'", "''"))
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    return path


@pytest.fixture(scope="session")
def tts_wav():
    return synth_wav


class FakeResponse:
    """Shared httpx-response double (superset: headers for retry-after tests)."""

    def __init__(self, status_code, json_data=None, headers=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._json


class FakeHttpClient:
    """Stub for the keep-alive clients in stt.groq / cleanup.haiku."""

    def __init__(self, handler):
        self._handler = handler

    def post(self, url, **kwargs):
        return self._handler(url, **kwargs)
