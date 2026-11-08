# PyInstaller spec for SelfScribe.app. Build with packaging/macos/build.sh.
# Groq-only bundle: the optional faster-whisper backend is left out to keep it small.

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ["launcher.py"],
    pathex=["../../src"],
    hiddenimports=(
        collect_submodules("selfscribe")
        + collect_submodules("pynput")
        + collect_submodules("pystray")
    ),
    excludes=["faster_whisper", "ctranslate2", "torch", "tkinter"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SelfScribe",
    console=False,
    argv_emulation=False,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="SelfScribe")
app = BUNDLE(
    coll,
    name="SelfScribe.app",
    icon="SelfScribe.icns",
    bundle_identifier="io.skaldstudio.selfscribe",
    info_plist={
        "CFBundleName": "SelfScribe",
        "CFBundleDisplayName": "SelfScribe",
        "CFBundleShortVersionString": "0.1.0",
        "LSMinimumSystemVersion": "12.0",
        # Menu-bar app: no Dock icon, lives in the menu bar like the Windows tray.
        "LSUIElement": True,
        "NSMicrophoneUsageDescription": (
            "SelfScribe records your voice while you hold the hotkey and turns it into text."
        ),
        "NSAppleEventsUsageDescription": "SelfScribe shows setup dialogs and notifications.",
    },
)
