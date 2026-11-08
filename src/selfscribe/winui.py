"""Windows dialogs for the packaged SelfScribe.exe (no console window).

Mirrors the macOS helpers: a first-run Groq key prompt and a plain alert.
Running from source keeps the console messages instead (see app.run).
"""

import ctypes


def alert(message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, message, "SelfScribe", 0x40)  # MB_ICONINFORMATION
    except Exception:
        pass


def ask_groq_key() -> str | None:
    """Hidden-text key prompt (tkinter ships with Python). None if cancelled."""
    try:
        import tkinter as tk
        from tkinter import simpledialog
    except ImportError:
        return None
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        key = simpledialog.askstring(
            "SelfScribe",
            "Welcome to SelfScribe.\n\nPaste your Groq API key to turn on speech to text.\n"
            "It's free: sign up at console.groq.com, then API Keys, Create API Key.\n\n"
            "The key is saved only on this PC (%USERPROFILE%\\.selfscribe\\config.toml).",
            show="*",
            parent=root,
        )
    finally:
        root.destroy()
    key = (key or "").strip()
    return key or None
