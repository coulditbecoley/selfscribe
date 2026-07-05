"""Application orchestrator: config -> hotkeys -> record -> transcribe -> inject."""

import sys

from selfscribe.config import ConfigError, load_config


def run() -> int:
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    source = cfg.source_path or "defaults + environment"
    print(
        f"selfscribe: config loaded from {source} "
        f"(stt={cfg.stt_backend}, cleanup={cfg.cleanup_backend}, mode={cfg.hotkey_mode})"
    )
    print("selfscribe: dictation loop not wired yet (lands with SS-7)")
    return 0
