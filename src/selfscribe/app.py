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
    """Route to the configured STT backend."""
    from selfscribe.stt import get_transcriber

    return get_transcriber(cfg)(clip)


def clean_text(text: str, cfg: Config, target: str) -> str:
    """Cleanup pass for targets that want it; raw text on any failure —
    pasting the uncleaned transcript beats pasting nothing."""
    from selfscribe.cleanup import get_cleaner

    cleaner = get_cleaner(cfg)
    if cleaner is None:
        return text
    try:
        return cleaner(text)
    except Exception as exc:
        log.warning("[%s] cleanup failed (%s) — injecting raw transcript", target, exc)
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
    from selfscribe.telemetry import record_utterance

    record_utterance(transcript.backend, transcript.ms, len(text), target)
    return text


class App:
    def __init__(self, cfg: Config, recorder: Recorder | None = None):
        self.cfg = cfg
        self.recorder = recorder or Recorder()
        self.on_recording_change: object = None  # Callable[[bool], None]
        self.listener = self._build_listener(cfg.hotkey_mode)

    def _build_listener(self, mode: str) -> HotkeyListener:
        return HotkeyListener(
            self.cfg.hotkey_dictate,
            self.cfg.hotkey_send,
            mode,
            on_start=self._on_start,
            on_stop=self._on_stop,
        )

    def set_hotkey_mode(self, mode: str) -> None:
        """Rebuild the listener in the new mode (tray menu switch)."""
        self.listener.stop()
        self.cfg.hotkey_mode = mode
        self.listener = self._build_listener(mode)
        self.listener.start()
        log.info("hotkey mode -> %s", mode)

    def _notify_recording(self, active: bool) -> None:
        if self.on_recording_change:
            try:
                self.on_recording_change(active)
            except Exception:
                log.debug("recording indicator update failed", exc_info=True)

    def _on_start(self, target: str) -> None:
        try:
            self.recorder.start()
            self._notify_recording(True)
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
        finally:
            self._notify_recording(False)
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


def run(fake_audio: str | None = None, use_tray: bool = True) -> int:
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

    if use_tray:
        try:
            from selfscribe.tray import Tray

            tray = Tray(cfg, on_quit=app.stop, on_mode_change=app.set_hotkey_mode)
            app.on_recording_change = tray.set_recording
            tray.run()  # blocks until Quit
            app.stop()
            print("selfscribe: stopped")
            return 0
        except Exception:
            log.exception("tray unavailable — running headless")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        app.stop()
        print("selfscribe: stopped")
    return 0
