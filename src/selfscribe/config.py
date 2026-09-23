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
    groq_model: str = "whisper-large-v3-turbo"
    local_model: str = "base.en"

    keep_mic_open: bool = True  # always-open stream: instant start + pre-roll

    cleanup_backend: str = "off"  # haiku | ollama | off
    cleanup_dictate: bool = True
    cleanup_send: bool = False
    cleanup_override: str = ""  # "" | "on" | "off"
    cleanup_apps: dict[str, bool] = field(default_factory=dict)  # process name -> on/off
    ollama_model: str = "llama3.2:1b"
    ollama_url: str = "http://localhost:11434"

    vocab: list[str] = field(default_factory=lambda: list(DEFAULT_VOCAB))
    vocab_fuzzy: bool = True  # edit-distance-1 repair of capitalized tokens

    commands_enabled: bool = True  # structural dictation commands (dictate path)

    source_path: Path | None = None

    def cleanup_enabled(self, target: str, app: str | None = None) -> bool:
        """Is the cleanup pass active for a target ('dictate' | 'send'), given
        the focused app's process name?

        Precedence: backend-off > tray override > per-app profile > per-target
        default. A per-app entry (e.g. code.exe = false) overrides the target
        default only for that focused application.
        """
        if self.cleanup_backend == "off":
            return False
        if self.cleanup_override == "on":
            return True
        if self.cleanup_override == "off":
            return False
        if app:
            app_choice = self.cleanup_apps.get(app.lower())
            if app_choice is not None:
                return app_choice
        if target == "dictate":
            return self.cleanup_dictate
        if target == "send":
            return self.cleanup_send
        raise ValueError(f"unknown cleanup target: {target!r}")


def cleanup_possible(cfg: "Config") -> bool:
    """Could the cleanup pass fire for any target/focused-app combination?
    Accounts for per-target defaults, per-app profiles, and the override."""
    return any(
        cfg.cleanup_enabled(target, app)
        for target in ("dictate", "send")
        for app in (None, *cfg.cleanup_apps)
    )


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
        ("groq_model", "stt", "groq_model", str),
        ("local_model", "stt", "local_model", str),
        ("keep_mic_open", "audio", "keep_open", bool),
        ("cleanup_backend", "cleanup", "backend", str),
        ("cleanup_dictate", "cleanup", "dictate", bool),
        ("cleanup_send", "cleanup", "send", bool),
        ("cleanup_override", "cleanup", "override", str),
        ("ollama_model", "cleanup", "ollama_model", str),
        ("ollama_url", "cleanup", "ollama_url", str),
        ("vocab", "vocab", "terms", list),
        ("vocab_fuzzy", "vocab", "fuzzy", bool),
        ("commands_enabled", "commands", "enabled", bool),
    ]:
        value = _get(raw, section, key, expected, path)
        if value is not None:
            setattr(cfg, attr, value)

    apps = raw.get("cleanup", {}).get("apps")
    if apps is not None:
        if not isinstance(apps, dict):
            raise ConfigError(f"Config error: [cleanup.apps] must be a table in {path}")
        for name, on in apps.items():
            if not isinstance(on, bool):
                raise ConfigError(
                    f"Config error: [cleanup.apps].\"{name}\" must be true or false in {path}"
                )
            cfg.cleanup_apps[name.lower()] = on

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
    cleanup_in_use = cfg.cleanup_backend == "haiku" and cleanup_possible(cfg)
    if cleanup_in_use and not cfg.anthropic_api_key:
        raise ConfigError(
            f"Missing Anthropic API key: set [keys].anthropic in {path} (or ANTHROPIC_API_KEY), "
            "or set [cleanup].backend to 'ollama' or 'off'."
        )
