"""Tray icon + recording indicator.

Gray dot = listening, red dot = recording — visible at a glance. The menu
exposes the runtime switches (cleanup override, STT backend, hotkey mode)
and Quit. Backend/cleanup changes just mutate the live Config (the pipeline
reads it per utterance); hotkey-mode changes rebuild the listener via the
callback the app provides.
"""

from collections.abc import Callable

from PIL import Image, ImageDraw

IDLE_COLOR = (110, 110, 110, 255)
RECORDING_COLOR = (220, 50, 47, 255)


def dot_image(color: tuple, size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = size // 8
    draw.ellipse([pad, pad, size - pad, size - pad], fill=color)
    return img


# Precomputed: set_recording runs on the hotkey listener thread.
IDLE_IMAGE = dot_image(IDLE_COLOR)
RECORDING_IMAGE = dot_image(RECORDING_COLOR)


class Tray:
    def __init__(
        self,
        cfg,
        on_quit: Callable[[], None],
        on_mode_change: Callable[[str], None] | None = None,
    ):
        self.cfg = cfg
        self.on_quit = on_quit
        self.on_mode_change = on_mode_change
        self.recording = False
        self._icon = None

    # --- state -----------------------------------------------------------
    def status_text(self) -> str:
        state = "RECORDING" if self.recording else "listening"
        cleanup = self.cfg.cleanup_override or "per-target"
        return (
            f"SelfScribe: {state} · {self.cfg.stt_backend} · "
            f"{self.cfg.hotkey_mode} · cleanup {cleanup}"
        )

    def _refresh(self, title: str | None = None) -> None:
        if self._icon is not None:
            self._icon.icon = RECORDING_IMAGE if self.recording else IDLE_IMAGE
            self._icon.title = title or self.status_text()

    def set_recording(self, active: bool) -> None:
        self.recording = active
        self._refresh()

    # --- menu actions ----------------------------------------------------
    def _set_backend(self, backend: str) -> None:
        error = None
        if backend == "groq" and not self.cfg.groq_api_key:
            error = "no Groq key in config"
        elif backend == "local":
            try:
                import faster_whisper  # noqa: F401
            except ImportError:
                error = "faster-whisper not installed"
        if error:
            self._refresh(title=f"SelfScribe: can't switch to {backend} — {error}")
            return
        self.cfg.stt_backend = backend
        self._refresh()

    def _set_mode(self, mode: str) -> None:
        self.cfg.hotkey_mode = mode
        if self.on_mode_change:
            self.on_mode_change(mode)
        self._refresh()

    def _cycle_cleanup(self) -> None:
        order = ["", "on", "off"]
        current = order.index(self.cfg.cleanup_override)
        self.cfg.cleanup_override = order[(current + 1) % len(order)]
        self._refresh()

    # --- pystray plumbing --------------------------------------------------
    def build_icon(self):
        import pystray

        menu = pystray.Menu(
            pystray.MenuItem(lambda item: self.status_text(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "STT backend",
                pystray.Menu(
                    pystray.MenuItem(
                        "Groq (fast, cloud)",
                        lambda: self._set_backend("groq"),
                        checked=lambda item: self.cfg.stt_backend == "groq",
                        radio=True,
                    ),
                    pystray.MenuItem(
                        "Local (offline)",
                        lambda: self._set_backend("local"),
                        checked=lambda item: self.cfg.stt_backend == "local",
                        radio=True,
                    ),
                ),
            ),
            pystray.MenuItem(
                "Hotkey mode",
                pystray.Menu(
                    pystray.MenuItem(
                        "Hold to talk",
                        lambda: self._set_mode("hold"),
                        checked=lambda item: self.cfg.hotkey_mode == "hold",
                        radio=True,
                    ),
                    pystray.MenuItem(
                        "Press to toggle",
                        lambda: self._set_mode("toggle"),
                        checked=lambda item: self.cfg.hotkey_mode == "toggle",
                        radio=True,
                    ),
                ),
            ),
            pystray.MenuItem(
                lambda item: f"Cleanup override: {self.cfg.cleanup_override or 'per-target'}",
                lambda: self._cycle_cleanup(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self._quit()),
        )
        self._icon = pystray.Icon("selfscribe", IDLE_IMAGE, self.status_text(), menu)
        return self._icon

    def _quit(self) -> None:
        if self._icon is not None:
            self._icon.stop()
        self.on_quit()

    def run(self) -> None:
        """Blocks until Quit; call from the main thread."""
        self.build_icon().run()

    def stop(self) -> None:
        if self._icon is not None:
            self._icon.stop()
