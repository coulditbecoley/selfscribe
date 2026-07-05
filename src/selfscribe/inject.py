"""Drop text at the cursor of whatever app has focus.

Primary path: save clipboard -> set text -> simulate paste -> restore
clipboard. Terminals get Ctrl+Shift+V (Ctrl+V can be literal ^V in some
shells); everything else gets Ctrl+V. If the paste keystroke can't be sent,
fall back to typed injection (pynput .type() -> SendInput unicode events),
which also serves paste-hostile fields. Only non-text clipboard content is
lost on restore — documented v1 tradeoff.
"""

import ctypes
import ctypes.wintypes as wt
import time
from dataclasses import dataclass
from pathlib import Path

TERMINAL_PROCESSES = {
    "windowsterminal.exe",
    "openconsole.exe",
    "conhost.exe",
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "wsl.exe",
    "mintty.exe",
    "alacritty.exe",
    "wezterm-gui.exe",
}

PASTE_SETTLE_S = 0.15  # clipboard set -> paste keystroke
RESTORE_DELAY_S = 0.35  # paste keystroke -> clipboard restore


@dataclass
class InjectionResult:
    method: str  # "paste" | "type"
    used_shift: bool = False
    clipboard_restored: bool = False


def foreground_process_name() -> str:
    """Executable name (lowercase) of the focused window's process, or ''."""
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(260)
        size = wt.DWORD(260)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return Path(buf.value).name.lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def is_terminal_focused() -> bool:
    return foreground_process_name() in TERMINAL_PROCESSES


class PynputKeys:
    """Real keystroke sender; swapped out in unit tests."""

    def __init__(self):
        from pynput.keyboard import Controller, Key

        self._ctl = Controller()
        self._key = Key

    def paste(self, use_shift: bool) -> None:
        mods = [self._key.ctrl] + ([self._key.shift] if use_shift else [])
        for m in mods:
            self._ctl.press(m)
        self._ctl.press("v")
        self._ctl.release("v")
        for m in reversed(mods):
            self._ctl.release(m)

    def type_text(self, text: str) -> None:
        self._ctl.type(text)

    def enter(self) -> None:
        self._ctl.press(self._key.enter)
        self._ctl.release(self._key.enter)


def inject_text(
    text: str,
    method: str = "paste",
    press_enter: bool = False,
    keys=None,
    clipboard=None,
    sleep=time.sleep,
    terminal_focused: bool | None = None,
) -> InjectionResult:
    """Deliver `text` to the focused app; optionally submit with Enter."""
    if keys is None:
        keys = PynputKeys()
    if clipboard is None:
        import pyperclip as clipboard

    if method == "type":
        keys.type_text(text)
        result = InjectionResult(method="type")
    else:
        try:
            prior = clipboard.paste()
        except Exception:
            prior = None
        use_shift = is_terminal_focused() if terminal_focused is None else terminal_focused
        clipboard.copy(text)
        sleep(PASTE_SETTLE_S)
        try:
            keys.paste(use_shift)
            result = InjectionResult(method="paste", used_shift=use_shift)
        except Exception:
            keys.type_text(text)
            result = InjectionResult(method="type")
        sleep(RESTORE_DELAY_S)
        if prior is not None:
            try:
                clipboard.copy(prior)
                result.clipboard_restored = True
            except Exception:
                pass

    if press_enter:
        sleep(0.1)
        keys.enter()
    return result
