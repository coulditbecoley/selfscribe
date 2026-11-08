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
    parser.set_defaults(fake_audio=None, no_tray=False, allow_multiple=False)
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
    run_parser.add_argument(
        "--allow-multiple",
        action="store_true",
        help="allow more than one running instance (skip the single-instance guard)",
    )
    sub.add_parser("check", help="First-run check: config, keys, mic, VAD")
    startup_parser = sub.add_parser("startup", help="Manage start-at-login")
    startup_parser.add_argument("action", choices=["install", "remove", "status"])
    shortcut_parser = sub.add_parser("shortcut", help="Manage the desktop launcher icon")
    shortcut_parser.add_argument("action", choices=["install", "remove", "status"])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "run"
    if command == "run":
        from selfscribe.app import run

        return run(
            fake_audio=args.fake_audio,
            use_tray=not args.no_tray,
            single_instance=not args.allow_multiple,
        )
    if command == "check":
        from selfscribe.doctor import check

        return check()
    if command in ("startup", "shortcut") and sys.platform == "darwin":
        print(
            "On macOS, drag SelfScribe.app into Applications, then add it under "
            "System Settings > General > Login Items to start it at login.",
            file=sys.stderr,
        )
        return 1
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
    if command == "shortcut":
        from selfscribe import desktop
        from selfscribe.links import ShortcutError

        try:
            if args.action == "install":
                print(f"desktop icon created: {desktop.install()}")
            elif args.action == "remove":
                removed = desktop.uninstall()
                print("desktop icon removed" if removed else "desktop icon was not present")
            else:
                state = "installed" if desktop.is_installed() else "not installed"
                print(f"desktop icon: {state} ({desktop.link_path()})")
        except ShortcutError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
