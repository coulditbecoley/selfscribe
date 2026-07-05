"""CLI entry point: `python -m selfscribe` or the `selfscribe` script."""

import argparse
import sys

from selfscribe import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="selfscribe",
        description="Push-to-talk dictation: hotkey -> mic -> Whisper -> text at your cursor.",
    )
    parser.add_argument("--version", action="version", version=f"selfscribe {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="Start the dictation loop (default)")
    sub.add_parser("check", help="First-run check: config, keys, mic, VAD")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "run"
    if command == "run":
        from selfscribe.app import run

        return run()
    if command == "check":
        from selfscribe.doctor import check

        return check()
    return 2


if __name__ == "__main__":
    sys.exit(main())
