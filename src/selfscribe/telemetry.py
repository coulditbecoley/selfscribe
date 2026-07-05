"""Per-utterance latency log. Local JSONL, no audio, no transcript text —
character count only, so the log can never leak what was said."""

import json
import logging
from datetime import datetime
from pathlib import Path

from selfscribe.config import DEFAULT_CONFIG_DIR

log = logging.getLogger("selfscribe")
ALLOWED_KEYS = {"ts", "backend", "ms", "chars", "target"}


def telemetry_path() -> Path:
    return DEFAULT_CONFIG_DIR / "telemetry.jsonl"


def record_utterance(
    backend: str, ms: float, chars: int, target: str, path: Path | None = None
) -> None:
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "backend": backend,
        "ms": round(ms, 1),
        "chars": chars,
        "target": target,
    }
    try:
        path = path or telemetry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:  # telemetry must never break dictation
        log.debug("telemetry write failed", exc_info=True)
