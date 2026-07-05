import subprocess
import sys

from selfscribe import __version__


def test_version_flag_runs_from_module():
    out = subprocess.run(
        [sys.executable, "-m", "selfscribe", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == f"selfscribe {__version__}"


def test_parser_knows_subcommands():
    from selfscribe.__main__ import build_parser

    parser = build_parser()
    args = parser.parse_args(["check"])
    assert args.command == "check"
    args = parser.parse_args([])
    assert args.command is None
