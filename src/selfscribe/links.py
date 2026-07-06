"""Shared Windows .lnk shortcut creation (start-at-login + desktop launcher).

Both shortcuts target the venv's pythonw.exe (no console window) running
`-m selfscribe run`. Paths are single-quote-escaped into the PowerShell script
so an apostrophe in a path (C:\\Users\\O'Brien) can't break or inject into it.
"""

import subprocess
import sys
from pathlib import Path

RUN_ARGS = "-m selfscribe run"


class ShortcutError(Exception):
    """Shortcut creation failed; message is one printable line."""


def venv_pythonw() -> Path:
    """The no-console launcher next to the current interpreter (falls back to
    python.exe if pythonw is absent)."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return pythonw if pythonw.exists() else Path(sys.executable)


def launcher_dir() -> Path:
    """Working directory for the shortcuts: the launcher's own dir (the venv
    Scripts dir). Stable alongside the interpreter, and cwd doesn't matter to
    `-m selfscribe run` (it resolves via the installed package)."""
    return venv_pythonw().parent


def _ps_quote(value) -> str:
    """Single-quoted PowerShell literal; '' escapes embedded apostrophes."""
    return "'" + str(value).replace("'", "''") + "'"


def create_shortcut(
    link: Path,
    target: Path,
    arguments: str,
    workdir: Path,
    icon: Path | None = None,
) -> Path:
    parts = [
        "$ws = New-Object -ComObject WScript.Shell",
        f"$s = $ws.CreateShortcut({_ps_quote(link)})",
        f"$s.TargetPath = {_ps_quote(target)}",
        f"$s.Arguments = {_ps_quote(arguments)}",
        f"$s.WorkingDirectory = {_ps_quote(workdir)}",
    ]
    if icon is not None:
        parts.append(f"$s.IconLocation = {_ps_quote(icon)}")
    parts.append("$s.Save()")
    script = "; ".join(parts)
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raw = (result.stderr or "").strip() or (result.stdout or "").strip() or "unknown error"
        raise ShortcutError(f"could not create the shortcut: {raw.splitlines()[0]}")
    return link
