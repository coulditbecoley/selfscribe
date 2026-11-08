"""Entry point for the bundled SelfScribe.app (double-click runs the app)."""

import sys

from selfscribe.__main__ import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["run"]))
