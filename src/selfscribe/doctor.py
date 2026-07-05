"""First-run check: config, keys, mic, VAD, backends. `selfscribe check`."""

import sys

from selfscribe.config import Config, ConfigError, load_config

OK, FAIL, WARN = "ok  ", "FAIL", "warn"


def _line(status: str, area: str, detail: str) -> bool:
    # FAIL details go to stderr so scripts capturing diagnostics see them.
    print(f"{status} {area}: {detail}", file=sys.stderr if status == FAIL else sys.stdout)
    return status != FAIL


def check_config() -> Config | None:
    try:
        cfg = load_config()
    except ConfigError as exc:
        _line(FAIL, "config", str(exc))
        return None
    _line(OK, "config", f"loaded from {cfg.source_path or 'defaults + environment'}")
    return cfg


def check_mic() -> bool:
    try:
        import sounddevice as sd

        from selfscribe.audio import SAMPLE_RATE

        sd.check_input_settings(samplerate=SAMPLE_RATE, channels=1, dtype="int16")
        device = sd.query_devices(kind="input")
        return _line(OK, "mic", f"{device['name']} @ {SAMPLE_RATE} Hz")
    except Exception as exc:
        return _line(FAIL, "mic", f"no usable input device ({exc})")


def check_vad() -> bool:
    try:
        import numpy as np

        from selfscribe.audio import SAMPLE_RATE, trim_silence

        silence = np.zeros(SAMPLE_RATE, dtype=np.int16)
        if trim_silence(silence, SAMPLE_RATE) is not None:  # survives python -O
            raise RuntimeError("VAD flagged pure silence as speech")
        return _line(OK, "vad", "webrtcvad trims silence")
    except Exception as exc:
        return _line(FAIL, "vad", f"voice activity detection broken ({exc})")


def check_stt(cfg: Config) -> bool:
    if cfg.stt_backend == "local":
        try:
            import faster_whisper  # noqa: F401

            return _line(OK, "stt", f"local faster-whisper ready (model {cfg.local_model})")
        except ImportError:
            return _line(FAIL, "stt", "backend=local but faster-whisper missing — "
                                      "pip install selfscribe[local]")
    if not cfg.groq_api_key:
        return _line(FAIL, "stt", "backend=groq but no key — set [keys].groq")
    try:
        import numpy as np

        from selfscribe.audio import SAMPLE_RATE, Clip
        from selfscribe.stt.groq import transcribe

        clip = Clip(pcm=np.zeros(int(SAMPLE_RATE * 0.4), dtype=np.int16))
        result = transcribe(clip, cfg.groq_api_key, timeout_s=10)
        return _line(OK, "stt", f"groq reachable, key accepted ({result.ms:.0f}ms)")
    except Exception as exc:
        return _line(FAIL, "stt", f"groq check failed — {exc}")


def check_cleanup(cfg: Config) -> bool:
    if cfg.cleanup_backend == "off":
        return _line(OK, "cleanup", "off")
    if not (cfg.cleanup_enabled("dictate") or cfg.cleanup_enabled("send")):
        return _line(OK, "cleanup", f"{cfg.cleanup_backend} configured but off for both targets")
    if cfg.cleanup_backend == "haiku":
        if cfg.anthropic_api_key:
            return _line(OK, "cleanup", "haiku (key present)")
        return _line(FAIL, "cleanup", "backend=haiku but no key — set [keys].anthropic")
    try:
        import httpx

        response = httpx.get(f"{cfg.ollama_url.rstrip('/')}/api/tags", timeout=5)
        models = [m.get("name", "") for m in response.json().get("models", [])]
        if any(m.startswith(cfg.ollama_model.split(":")[0]) for m in models):
            return _line(OK, "cleanup", f"ollama running, {cfg.ollama_model} available")
        return _line(WARN, "cleanup", f"ollama running but {cfg.ollama_model} not pulled — "
                                      f"run: ollama pull {cfg.ollama_model}")
    except Exception:
        return _line(FAIL, "cleanup", f"ollama not reachable at {cfg.ollama_url}")


def check_startup() -> bool:
    from selfscribe import startup

    state = "installed" if startup.is_installed() else (
        "not installed (optional — selfscribe startup install)"
    )
    return _line(OK, "startup", state)


def check() -> int:
    cfg = check_config()
    if cfg is None:
        return 1
    results = [
        check_mic(),
        check_vad(),
        check_stt(cfg),
        check_cleanup(cfg),
        check_startup(),
    ]
    if all(results):
        print("all checks passed — hold your hotkey and speak")
        return 0
    print("fix the FAIL lines above, then re-run: selfscribe check", file=sys.stderr)
    return 1
