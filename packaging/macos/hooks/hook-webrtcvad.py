# Overrides the pyinstaller-hooks-contrib hook, which copies metadata for the
# "webrtcvad" distribution. SelfScribe installs the prebuilt "webrtcvad-wheels"
# distribution instead (same import name), so the stock hook fails to build.
from PyInstaller.utils.hooks import copy_metadata

try:
    datas = copy_metadata("webrtcvad-wheels")
except Exception:  # metadata is optional; the module itself still bundles
    datas = []
