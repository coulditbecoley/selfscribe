"""Single-instance guard via a Windows named mutex.

Double-clicking the desktop icon while SelfScribe is already running would
otherwise start a second process, and both would install the global hotkey
hook — every press would record twice. acquire() returns False for the second
instance so run() can bow out with a friendly message.
"""

import ctypes
import os
from ctypes import wintypes

# Overridable so tests can use a throwaway name instead of the global mutex.
MUTEX_NAME = os.environ.get("SELFSCRIBE_MUTEX", "selfscribe-single-instance-9f2a")
ERROR_ALREADY_EXISTS = 183

_handle = None  # kept alive for the process lifetime once acquired


def _create_mutex(name: str) -> tuple[bool, int | None]:
    """(acquired, handle). acquired is False when the mutex already exists.
    Returns (True, None) if the Win32 call is unavailable — never blocks the app.

    Uses a use_last_error WinDLL + ctypes.get_last_error() so the ERROR_ALREADY_
    EXISTS status is read from the value ctypes captures immediately after the
    call, not a later GetLastError() that other ctypes calls could have cleared.
    """
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (OSError, AttributeError):  # non-Windows / unavailable
        return True, None
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    handle = kernel32.CreateMutexW(None, False, name)
    err = ctypes.get_last_error()
    if not handle:
        return True, None
    if err == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle(handle)
        return False, None
    return True, handle


def acquire() -> bool:
    """True if this is the only instance; False if another already holds it."""
    global _handle
    acquired, handle = _create_mutex(MUTEX_NAME)
    if acquired and handle is not None:
        _handle = handle
    return acquired


def notify_already_running() -> None:
    """Non-fatal popup for the no-console (double-click) launch path."""
    try:
        ctypes.windll.user32.MessageBoxW(
            None, "SelfScribe is already running.", "SelfScribe", 0x40  # MB_ICONINFORMATION
        )
    except Exception:
        pass
