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
    # Bare `selfscribe` (no subcommand) must be structurally identical to
    # `selfscribe run` — every run flag needs a root-level default.
    parser.set_defaults(fake_audio=None, no_tray=False)
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
    startup_parser = sub.add_parser("startup", help="Manage start-at-login")
    startup_parser.add_argument("action", choices=["install", "remove", "status"])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "run"
    if command == "run":
        from selfscribe.app import run

        return run(fake_audio=args.fake_audio, use_tray=not args.no_tray)
    if command == "check":
        from selfscribe.doctor import check

        return check()
    if command == "startup":
        from selfscribe import startup

        try:
            if args.action == "install":
                print(f"start-at-login installed: {startup.install()}")
            elif args.action == "remove":
                removed = startup.uninstall()
                print("start-at-login removed" if removed else "start-at-login was not installed")
            else:
                state = "installed" if startup.is_installed() else "not installed"
                print(f"start-at-login: {state} ({startup.link_path()})")
        except startup.StartupError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
