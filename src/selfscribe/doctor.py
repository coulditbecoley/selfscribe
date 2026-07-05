"""First-run check: config, keys, mic, VAD. Grows through the build (SS-17)."""

import sys

from selfscribe.config import ConfigError, load_config


def check() -> int:
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"FAIL config: {exc}", file=sys.stderr)
        return 1
    print(f"ok   config: loaded from {cfg.source_path or 'defaults + environment'}")
    print(f"ok   keys: groq={'set' if cfg.groq_api_key else 'missing'}", end="")
    print(f", anthropic={'set' if cfg.anthropic_api_key else 'missing'}")
    return 0
