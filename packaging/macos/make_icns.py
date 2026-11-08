"""Render the app's mic icon to an .icns for the macOS bundle."""

import sys
from pathlib import Path

from selfscribe.assets import render_icon

out = Path(sys.argv[1] if len(sys.argv) > 1 else "SelfScribe.icns")
render_icon(1024).save(out, format="ICNS")
print(out)
