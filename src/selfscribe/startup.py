"""Optional start-at-login via a Startup-folder shortcut (no admin needed).

The .lnk targets the venv's pythonw.exe (no console window) running
`-m selfscribe run`. Managed by `selfscribe startup install|remove|status`.
"""

import os
from pathlib import Path

# _ps_quote is re-exported so `selfscribe startup` keeps its quoting helper.
from selfscribe.links import (  # noqa: F401
    ShortcutError,
    _ps_quote,
    create_shortcut,
    launcher_dir,
    venv_pythonw,
)

StartupError = ShortcutError
LINK_NAME = "SelfScribe.lnk"


def startup_dir() -> Path:
    return (
        Path(os.environ["APPDATA"])
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )


def link_path(directory: Path | None = None) -> Path:
    return (directory or startup_dir()) / LINK_NAME


def _launcher() -> Path:
    return venv_pythonw()


def install(directory: Path | None = None) -> Path:
    return create_shortcut(
        link_path(directory), venv_pythonw(), "-m selfscribe run", launcher_dir()
    )


def uninstall(directory: Path | None = None) -> bool:
    link = link_path(directory)
    if link.exists():
        link.unlink()
        return True
    return False


def is_installed(directory: Path | None = None) -> bool:
    return link_path(directory).exists()
