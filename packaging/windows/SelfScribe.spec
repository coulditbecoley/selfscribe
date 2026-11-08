# PyInstaller spec for SelfScribe.exe (Windows). Build with packaging/windows/build.ps1.
# Groq-only bundle, like the Mac app: faster-whisper is left out to keep it small.

from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ["../macos/launcher.py"],
    pathex=["../../src"],
    hiddenimports=(
        collect_submodules("selfscribe")
        + collect_submodules("pynput")
        + collect_submodules("pystray")
    ),
    hookspath=["../macos/hooks"],
    excludes=["faster_whisper", "ctranslate2", "torch"],
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SelfScribe",
    console=False,  # tray app: no console window
    icon="SelfScribe.ico",
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="SelfScribe")
