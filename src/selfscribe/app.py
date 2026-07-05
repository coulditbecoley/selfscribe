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
from selfscribe.inject import foreground_process_name, inject_text, is_terminal_focused
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


def sanitize_for_injection(text: str) -> str:
    """Neutralize control characters before the text is pasted and (on the
    send path) Enter is pressed.

    Injected text goes to the clipboard and is pasted into whatever app has
    focus — often a terminal. An embedded newline in a terminal paste submits
    that line, so a multi-line transcript (or a hostile/compromised STT or
    cleanup response) could run intermediate lines as shell commands. v1
    dictation is single-line, so newlines/tabs collapse to spaces and other
    C0/C1 control chars are dropped; the caller decides on Enter separately.
    """
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").replace("\t", " ")
    cleaned = "".join(ch for ch in text if ch.isprintable())
    return " ".join(cleaned.split())


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
    focused_app = foreground_process_name()
    if cfg.cleanup_enabled(target, app=focused_app):
        text = clean_text(text, cfg, target)
        from selfscribe.stt import apply_vocab_fixes

        # the cleanup LLM may re-case vocab terms; repair the final text too
        text = apply_vocab_fixes(text, cfg.vocab, fuzzy=cfg.vocab_fuzzy)
    text = sanitize_for_injection(text)
    if not text:
        log.info("transcript was all control characters — nothing to inject")
        soft_cue()
        return None
    # Structural dictation commands run AFTER sanitization and only on the
    # dictate path. A newline pasted into a terminal submits that line, and
    # the command recognizer runs on untrusted STT/cleanup text — so a
    # terminal focused here would let a hostile response emit "new line" to
    # gain a line-submit primitive. The dictate path is for text fields, not
    # terminals (that's the send path's job), so we suppress command-produced
    # newlines whenever a terminal has focus: closes that vector and avoids
    # accidentally submitting a partial line into a shell.
    if target == "dictate" and cfg.commands_enabled and not is_terminal_focused():
        from selfscribe.commands import apply_commands

        text = apply_commands(text)
        if not text:
            soft_cue()
            return None
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
        # One clip at a time end-to-end: concurrent injections would race on
        # the shared clipboard inside inject_text's settle/restore sleeps.
        self._process_lock = threading.Lock()
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
        if self.recorder.recording:
            # The old tracker held the active session; without this the mic
            # stream would stay open and bleed into the next utterance.
            self.recorder.stop()
            self._notify_recording(False)
            log.info("hotkey mode switch discarded an active recording")
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
            with self._process_lock:
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
    """Test seam (--fake-audio): 'records' a canned WAV instead of the mic.

    The canned frames still go through Recorder._finish, so the min-length
    guard, VAD trim, and discard_reason semantics match the real pipeline.
    """

    def __init__(self, wav_path: str):
        super().__init__()
        self._wav_path = wav_path

    def start(self) -> None:
        self.discard_reason = None

    def stop(self) -> Clip | None:
        from pathlib import Path

        from selfscribe.audio import SAMPLE_RATE, clip_from_wav_bytes, resample

        clip = clip_from_wav_bytes(Path(self._wav_path).read_bytes())
        # normalize to 16 kHz like the real mic stream (webrtcvad in _finish
        # only accepts 8/16/32/48 kHz)
        pcm = resample(clip.pcm, clip.samplerate, SAMPLE_RATE)
        self.samplerate = SAMPLE_RATE
        return self._finish([pcm.reshape(-1, 1)])


def _build_tray(app: App):
    try:
        from selfscribe.tray import Tray

        tray = Tray(app.cfg, on_quit=app.stop, on_mode_change=app.set_hotkey_mode)
        app.on_recording_change = tray.set_recording
        return tray
    except Exception:
        log.exception("tray unavailable — running headless")
        return None


def _warm_local_model(cfg: Config) -> None:
    """Load faster-whisper during idle listening so the first utterance
    doesn't absorb the multi-second model init."""
    try:
        from selfscribe.stt.local import _get_model

        _get_model(cfg.local_model)
        log.info("local whisper model %s ready", cfg.local_model)
    except Exception:
        log.debug("local model preload failed", exc_info=True)


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
    if cfg.stt_backend == "local":
        threading.Thread(
            target=_warm_local_model, args=(cfg,), daemon=True, name="selfscribe-warm"
        ).start()
    print(
        f"selfscribe: listening — dictate={cfg.hotkey_dictate} "
        f"send={cfg.hotkey_send} mode={cfg.hotkey_mode} stt={cfg.stt_backend}",
        flush=True,
    )

    tray = _build_tray(app) if use_tray else None
    try:
        if tray is not None:
            try:
                tray.run()  # blocks until Quit or Ctrl+C
            except Exception:
                # pystray backend failures (no shell tray, RDP/service
                # session) degrade to headless instead of crashing
                log.exception("tray failed — continuing headless")
                tray = None
        if tray is None:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        if tray is not None:
            tray.stop()
    finally:
        app.stop()
        print("selfscribe: stopped")
    return 0
