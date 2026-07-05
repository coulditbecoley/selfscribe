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
    run_parser = sub.add_parser("run", help="Start the dictation loop (default)")
    run_parser.add_argument(
        "--fake-audio",
        metavar="WAV",
        default=None,
        help="testing: 'record' this WAV instead of the mic",
    )
    run_parser.add_argument(
        "--no-tray",
        action="store_true",
        help="run headless without the tray icon",
    )
    sub.add_parser("check", help="First-run check: config, keys, mic, VAD")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "run"
    if command == "run":
        from selfscribe.app import run

        return run(
            fake_audio=getattr(args, "fake_audio", None),
            use_tray=not getattr(args, "no_tray", False),
        )
    if command == "check":
        from selfscribe.doctor import check

        return check()
    return 2


if __name__ == "__main__":
    sys.exit(main())
