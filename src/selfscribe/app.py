"""Application orchestrator: hotkey -> record -> transcribe -> (cleanup) -> inject.

Hotkey callbacks arrive on the pynput listener thread; each finished clip is
processed on its own worker thread so the listener never blocks. Only the
'send' target presses Enter. Any per-utterance failure is a soft cue + log
line, never a crash — the loop keeps listening.
"""

import logging
import sys
import threading
import time

from selfscribe.audio import Clip, Recorder
from selfscribe.config import Config, ConfigError, load_config
from selfscribe.hotkeys import HotkeyListener
from selfscribe.inject import inject_text
from selfscribe.stt import Transcript, TranscriptionError

log = logging.getLogger("selfscribe")


def soft_cue() -> None:
    """Non-intrusive 'that didn't count' signal."""
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:  # no audio device / non-Windows: silent is fine
        pass


def transcribe_clip(clip: Clip, cfg: Config) -> Transcript:
    """Route to the configured STT backend (registry grows in SS-8/9)."""
    from selfscribe.stt.groq import transcribe

    return transcribe(clip, cfg.groq_api_key, initial_prompt=", ".join(cfg.vocab))


def clean_text(text: str, cfg: Config, target: str) -> str:
    """Optional cleanup pass; no-op until SS-12 lands a backend."""
    return text


def process_clip(clip: Clip, target: str, cfg: Config, inject=inject_text) -> str | None:
    """Transcribe one clip and deliver it. Returns injected text or None."""
    transcript = transcribe_clip(clip, cfg)
    text = transcript.text.strip()
    if not text:
        log.info("empty transcript (%.0fms) — nothing to inject", transcript.ms)
        soft_cue()
        return None
    if cfg.cleanup_enabled(target):
        text = clean_text(text, cfg, target)
    inject(text, press_enter=(target == "send"))
    log.info("[%s] %.0fms %s: %r", target, transcript.ms, transcript.backend, text)
    return text


class App:
    def __init__(self, cfg: Config, recorder: Recorder | None = None):
        self.cfg = cfg
        self.recorder = recorder or Recorder()
        self.listener = HotkeyListener(
            cfg.hotkey_dictate,
            cfg.hotkey_send,
            cfg.hotkey_mode,
            on_start=self._on_start,
            on_stop=self._on_stop,
        )

    def _on_start(self, target: str) -> None:
        try:
            self.recorder.start()
            log.info("[%s] recording…", target)
        except Exception:
            log.exception("could not start recording")
            soft_cue()

    def _on_stop(self, target: str) -> None:
        try:
            clip = self.recorder.stop()
        except Exception:
            log.exception("could not stop recording")
            soft_cue()
            return
        if clip is None:
            log.info("[%s] discarded (%s)", target, self.recorder.discard_reason)
            soft_cue()
            return
        threading.Thread(
            target=self._process, args=(clip, target), daemon=True, name="selfscribe-clip"
        ).start()

    def _process(self, clip: Clip, target: str) -> None:
        try:
            process_clip(clip, target, self.cfg)
        except TranscriptionError as exc:
            log.error("[%s] %s", target, exc)
            soft_cue()
        except Exception:
            log.exception("[%s] unexpected failure — still listening", target)
            soft_cue()

    def start(self) -> None:
        self.listener.start()

    def stop(self) -> None:
        self.listener.stop()


class FakeRecorder(Recorder):
    """Test seam (--fake-audio): 'records' a canned WAV instead of the mic."""

    def __init__(self, wav_path: str):
        super().__init__()
        self._wav_path = wav_path

    def start(self) -> None:
        self.discard_reason = None

    def stop(self) -> Clip | None:
        from pathlib import Path

        from selfscribe.audio import clip_from_wav_bytes

        return clip_from_wav_bytes(Path(self._wav_path).read_bytes())


def run(fake_audio: str | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    recorder = FakeRecorder(fake_audio) if fake_audio else None
    app = App(cfg, recorder=recorder)
    app.start()
    print(
        f"selfscribe: listening — dictate={cfg.hotkey_dictate} "
        f"send={cfg.hotkey_send} mode={cfg.hotkey_mode} stt={cfg.stt_backend}",
        flush=True,
    )
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        app.stop()
        print("selfscribe: stopped")
    return 0
