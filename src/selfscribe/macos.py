"""macOS-only helpers: dialogs, notifications, first-run key setup, permissions.

Dialogs go through osascript with the text passed as argv (never spliced into
the AppleScript source), so a key or message can't inject script. A bundled
.app has no console, so these are how SelfScribe talks to someone on a Mac.
"""

import re
import subprocess
from pathlib import Path

from selfscribe.config import DEFAULT_CONFIG_PATH

_DIALOG = """on run argv
    set r to display dialog (item 1 of argv) default answer "" with hidden answer ¬
        with title "SelfScribe" buttons {"Quit", "Save"} default button "Save"
    return text returned of r
end run"""

_ALERT = """on run argv
    display dialog (item 1 of argv) with title "SelfScribe" buttons {"OK"} default button "OK"
end run"""

_NOTIFY = """on run argv
    display notification (item 1 of argv) with title "SelfScribe"
end run"""


def _osascript(script: str, *args: str, timeout: float | None = None) -> str | None:
    """Run AppleScript; returns stdout, or None if the user cancelled/failed."""
    try:
        out = subprocess.run(
            ["osascript", "-e", script, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def notify(message: str) -> None:
    _osascript(_NOTIFY, message, timeout=10)


def alert(message: str) -> None:
    _osascript(_ALERT, message)


def ask_groq_key() -> str | None:
    """Ask for a Groq key in a hidden-text dialog. None if they quit."""
    key = _osascript(
        _DIALOG,
        "Welcome to SelfScribe.\n\nPaste your Groq API key to turn on speech to text. "
        "It's free: sign up at console.groq.com, then API Keys, Create API Key.\n\n"
        "The key is saved only on this Mac (~/.selfscribe/config.toml).",
    )
    key = (key or "").strip()
    return key or None


def save_groq_key(key: str, path: Path = DEFAULT_CONFIG_PATH) -> Path:
    """Write [keys].groq into the config, keeping everything else in the file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = f'groq = "{key}"'
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if re.search(r"(?m)^\s*groq\s*=", text):
        text = re.sub(r'(?m)^\s*groq\s*=.*$', line, text, count=1)
    elif re.search(r"(?m)^\s*\[keys\]\s*$", text):
        text = re.sub(r"(?m)^\s*\[keys\]\s*$", f"[keys]\n{line}", text, count=1)
    else:
        text = f"[keys]\n{line}\n\n{text}"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)  # key file readable by this user only
    return path


def accessibility_trusted(prompt: bool = False) -> bool:
    """Has macOS granted Accessibility (needed to read hotkeys and paste)?
    With prompt=True the system shows its own 'grant access' dialog."""
    try:
        import ApplicationServices as AS

        key = getattr(AS, "kAXTrustedCheckOptionPrompt", "AXTrustedCheckOptionPrompt")
        return bool(AS.AXIsProcessTrustedWithOptions({key: prompt}))
    except Exception:
        return True  # can't tell: don't nag


PERMISSIONS_HELP = (
    "SelfScribe needs three permissions in System Settings > Privacy & Security:\n\n"
    "1. Microphone (asked the first time you dictate)\n"
    "2. Accessibility (to paste text where your cursor is)\n"
    "3. Input Monitoring (to hear the hotkey)\n\n"
    "Turn SelfScribe on in Accessibility and Input Monitoring, then quit and reopen it.\n\n"
    "Hotkeys: hold Control+Command and speak, release to paste. "
    "Add Option (Control+Option+Command) to paste and press Return."
)
