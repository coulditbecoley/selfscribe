"""Optional start-at-login via a Startup-folder shortcut (no admin needed).

The .lnk targets the venv's pythonw.exe (no console window) running
`-m selfscribe run`. Managed by `selfscribe startup install|remove|status`.
"""

import os
import subprocess
import sys
from pathlib import Path

LINK_NAME = "SelfScribe.lnk"


def startup_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / (
        "Programs"
    ) / "Startup"


def link_path(directory: Path | None = None) -> Path:
    return (directory or startup_dir()) / LINK_NAME


def _launcher() -> Path:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return pythonw if pythonw.exists() else Path(sys.executable)


def install(directory: Path | None = None) -> Path:
    link = link_path(directory)
    target = _launcher()
    workdir = target.parent
    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{link}'); "
        f"$s.TargetPath = '{target}'; "
        "$s.Arguments = '-m selfscribe run'; "
        f"$s.WorkingDirectory = '{workdir}'; "
        "$s.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return link


def uninstall(directory: Path | None = None) -> bool:
    link = link_path(directory)
    if link.exists():
        link.unlink()
        return True
    return False


def is_installed(directory: Path | None = None) -> bool:
    return link_path(directory).exists()
