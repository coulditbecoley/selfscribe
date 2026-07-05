"""Load settings + API keys from %USERPROFILE%\\.selfscribe\\config.toml.

Keys never live in the repo. Every validation failure raises ConfigError with
a single human-readable line — callers print it and exit, no stack trace.
"""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_DIR = Path.home() / ".selfscribe"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"

DEFAULT_VOCAB = [
    "Skald",
    "HitHQ",
    "HitList",
    "SelfScribe",
    "Coley",
    "Fenrir",
    "Obsidian",
    "Claude Code",
]


class ConfigError(Exception):
    """A config problem the user must fix; message is one printable line."""


@dataclass
class Config:
    groq_api_key: str = field(default="", repr=False)
    anthropic_api_key: str = field(default="", repr=False)

    hotkey_dictate: str = "ctrl+windows"
    hotkey_send: str = "ctrl+alt+windows"
    hotkey_mode: str = "hold"  # hold | toggle

    stt_backend: str = "groq"  # groq | local
    local_model: str = "base.en"

    cleanup_backend: str = "off"  # haiku | ollama | off
    cleanup_dictate: bool = True
    cleanup_send: bool = False
    cleanup_override: str = ""  # "" | "on" | "off"
    ollama_model: str = "llama3.2:1b"
    ollama_url: str = "http://localhost:11434"

    vocab: list[str] = field(default_factory=lambda: list(DEFAULT_VOCAB))

    source_path: Path | None = None

    def cleanup_enabled(self, target: str) -> bool:
        """Is the cleanup pass active for a given target ('dictate' | 'send')?"""
        if self.cleanup_backend == "off":
            return False
        if self.cleanup_override == "on":
            return True
        if self.cleanup_override == "off":
            return False
        if target == "dictate":
            return self.cleanup_dictate
        if target == "send":
            return self.cleanup_send
        raise ValueError(f"unknown cleanup target: {target!r}")


def _get(table: dict, section: str, key: str, expected: type, path: Path):
    value = table.get(section, {}).get(key)
    if value is not None and not isinstance(value, expected):
        raise ConfigError(
            f"Config error: [{section}].{key} must be {expected.__name__} in {path}"
        )
    return value


def load_config(path: Path | None = None) -> Config:
    """Read the dotfile (env vars fall back for keys) and validate."""
    if path is None:
        env_path = os.environ.get("SELFSCRIBE_CONFIG")
        path = Path(env_path) if env_path else DEFAULT_CONFIG_PATH
    raw: dict = {}
    if path.exists():
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Config error: {path} is not valid TOML ({exc})") from exc

    cfg = Config(source_path=path if path.exists() else None)

    keys = raw.get("keys", {})
    cfg.groq_api_key = keys.get("groq") or os.environ.get("GROQ_API_KEY", "")
    cfg.anthropic_api_key = keys.get("anthropic") or os.environ.get("ANTHROPIC_API_KEY", "")

    for attr, section, key, expected in [
        ("hotkey_dictate", "hotkeys", "dictate", str),
        ("hotkey_send", "hotkeys", "dictate_send", str),
        ("hotkey_mode", "hotkeys", "mode", str),
        ("stt_backend", "stt", "backend", str),
        ("local_model", "stt", "local_model", str),
        ("cleanup_backend", "cleanup", "backend", str),
        ("cleanup_dictate", "cleanup", "dictate", bool),
        ("cleanup_send", "cleanup", "send", bool),
        ("cleanup_override", "cleanup", "override", str),
        ("ollama_model", "cleanup", "ollama_model", str),
        ("ollama_url", "cleanup", "ollama_url", str),
        ("vocab", "vocab", "terms", list),
    ]:
        value = _get(raw, section, key, expected, path)
        if value is not None:
            setattr(cfg, attr, value)

    _validate(cfg, path)
    return cfg


def _validate(cfg: Config, path: Path) -> None:
    if cfg.hotkey_mode not in ("hold", "toggle"):
        raise ConfigError(f"Config error: [hotkeys].mode must be 'hold' or 'toggle' in {path}")
    if cfg.stt_backend not in ("groq", "local"):
        raise ConfigError(f"Config error: [stt].backend must be 'groq' or 'local' in {path}")
    if cfg.cleanup_backend not in ("haiku", "ollama", "off"):
        raise ConfigError(
            f"Config error: [cleanup].backend must be 'haiku', 'ollama' or 'off' in {path}"
        )
    if cfg.cleanup_override not in ("", "on", "off"):
        raise ConfigError(
            f"Config error: [cleanup].override must be '', 'on' or 'off' in {path}"
        )
    if not all(isinstance(t, str) for t in cfg.vocab):
        raise ConfigError(f"Config error: [vocab].terms must be a list of strings in {path}")

    if cfg.stt_backend == "groq" and not cfg.groq_api_key:
        raise ConfigError(
            f"Missing Groq API key: set [keys].groq in {path} (or GROQ_API_KEY), "
            "or switch [stt].backend to 'local'."
        )
    cleanup_in_use = cfg.cleanup_backend == "haiku" and (
        cfg.cleanup_enabled("dictate") or cfg.cleanup_enabled("send")
    )
    if cleanup_in_use and not cfg.anthropic_api_key:
        raise ConfigError(
            f"Missing Anthropic API key: set [keys].anthropic in {path} (or ANTHROPIC_API_KEY), "
            "or set [cleanup].backend to 'ollama' or 'off'."
        )
