"""Desktop launcher shortcut — a double-clickable icon that starts SelfScribe.

Targets the venv's pythonw.exe (no console window) with the generated mic icon.
Managed by `selfscribe shortcut install|remove|status`.
"""

import os
from pathlib import Path

from selfscribe.assets import write_ico
from selfscribe.links import create_shortcut, launcher_dir, venv_pythonw

LINK_NAME = "SelfScribe.lnk"


def desktop_dir() -> Path:
    # USERPROFILE\Desktop is correct even when OneDrive redirects the shell
    # folder for most single-user setups; good enough for a personal tool.
    return Path(os.environ["USERPROFILE"]) / "Desktop"


def link_path(directory: Path | None = None) -> Path:
    return (directory or desktop_dir()) / LINK_NAME


def install(directory: Path | None = None) -> Path:
    icon = write_ico()
    return create_shortcut(
        link_path(directory), venv_pythonw(), "-m selfscribe run", launcher_dir(), icon=icon
    )


def uninstall(directory: Path | None = None) -> bool:
    link = link_path(directory)
    if link.exists():
        link.unlink()
        return True
    return False


def is_installed(directory: Path | None = None) -> bool:
    return link_path(directory).exists()
