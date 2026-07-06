"""Single-instance guard via a Windows named mutex.

Double-clicking the desktop icon while SelfScribe is already running would
otherwise start a second process, and both would install the global hotkey
hook — every press would record twice. acquire() returns False for the second
instance so run() can bow out with a friendly message.
"""

import ctypes
import os

# Overridable so tests can use a throwaway name instead of the global mutex.
MUTEX_NAME = os.environ.get("SELFSCRIBE_MUTEX", "selfscribe-single-instance-9f2a")
ERROR_ALREADY_EXISTS = 183

_handle = None  # kept alive for the process lifetime once acquired


def acquire() -> bool:
    """True if this is the only instance; False if another already holds it.
    Never blocks the app on failure (returns True if the OS call fails)."""
    global _handle
    try:
        kernel32 = ctypes.windll.kernel32
    except AttributeError:  # non-Windows: no guard, don't block
        return True
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return True
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _handle = handle
    return True


def notify_already_running() -> None:
    """Non-fatal popup for the no-console (double-click) launch path."""
    try:
        ctypes.windll.user32.MessageBoxW(
            None, "SelfScribe is already running.", "SelfScribe", 0x40  # MB_ICONINFORMATION
        )
    except Exception:
        pass
