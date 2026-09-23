import pytest

from selfscribe.config import Config, ConfigError, load_config


@pytest.fixture(autouse=True)
def _no_env_keys(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def write(tmp_path, text):
    p = tmp_path / "config.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_minimal_config_gets_sane_defaults(tmp_path):
    cfg = load_config(write(tmp_path, '[keys]\ngroq = "gsk_test"\n'))
    assert cfg.groq_api_key == "gsk_test"
    assert cfg.hotkey_mode == "hold"
    assert cfg.stt_backend == "groq"
    assert cfg.cleanup_backend == "off"
    assert cfg.cleanup_enabled("dictate") is False  # backend off => no cleanup anywhere
    assert cfg.cleanup_enabled("send") is False
    assert "SelfScribe" in cfg.vocab
    assert cfg.commands_enabled is True


def test_commands_can_be_disabled_via_config(tmp_path):
    cfg = load_config(write(tmp_path, '[keys]\ngroq="g"\n\n[commands]\nenabled = false\n'))
    assert cfg.commands_enabled is False


def test_per_app_cleanup_profiles_parsed(tmp_path):
    text = (
        '[keys]\ngroq="g"\nanthropic="a"\n\n'
        '[cleanup]\nbackend = "haiku"\n\n'
        '[cleanup.apps]\n"Code.exe" = false\n"OUTLOOK.EXE" = true\n'
    )
    cfg = load_config(write(tmp_path, text))
    assert cfg.cleanup_apps == {"code.exe": False, "outlook.exe": True}


def test_per_app_non_bool_value_rejected(tmp_path):
    text = '[keys]\ngroq="g"\n\n[cleanup.apps]\n"code.exe" = "no"\n'
    with pytest.raises(ConfigError) as exc:
        load_config(write(tmp_path, text))
    assert "cleanup.apps" in str(exc.value)


def test_missing_groq_key_is_one_line_error(tmp_path):
    with pytest.raises(ConfigError) as exc:
        load_config(write(tmp_path, "[stt]\nbackend = 'groq'\n"))
    assert "\n" not in str(exc.value)
    assert "Groq" in str(exc.value)


def test_local_backend_needs_no_keys(tmp_path):
    cfg = load_config(write(tmp_path, "[stt]\nbackend = 'local'\n"))
    assert cfg.stt_backend == "local"


def test_env_var_fallback_for_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_env")
    cfg = load_config(write(tmp_path, "[hotkeys]\nmode = 'toggle'\n"))
    assert cfg.groq_api_key == "gsk_env"
    assert cfg.hotkey_mode == "toggle"


def test_haiku_cleanup_requires_anthropic_key(tmp_path):
    with pytest.raises(ConfigError) as exc:
        load_config(
            write(tmp_path, '[keys]\ngroq = "g"\n\n[cleanup]\nbackend = "haiku"\n')
        )
    assert "Anthropic" in str(exc.value)


def test_haiku_key_required_when_only_a_per_app_profile_enables_cleanup(tmp_path):
    # both targets off, but a per-app profile turns cleanup on -> key required
    text = (
        '[keys]\ngroq="g"\n\n'
        '[cleanup]\nbackend = "haiku"\ndictate = false\nsend = false\n\n'
        '[cleanup.apps]\n"slack.exe" = true\n'
    )
    with pytest.raises(ConfigError) as exc:
        load_config(write(tmp_path, text))
    assert "Anthropic" in str(exc.value)


def test_haiku_key_not_required_when_all_per_app_profiles_off(tmp_path):
    text = (
        '[keys]\ngroq="g"\n\n'
        '[cleanup]\nbackend = "haiku"\ndictate = false\nsend = false\n\n'
        '[cleanup.apps]\n"code.exe" = false\n'
    )
    cfg = load_config(write(tmp_path, text))  # no key, but cleanup never fires
    assert cfg.cleanup_backend == "haiku"


def test_per_target_cleanup_defaults():
    cfg = Config(cleanup_backend="haiku", anthropic_api_key="k")
    assert cfg.cleanup_enabled("dictate") is True  # docs/email path cleans
    assert cfg.cleanup_enabled("send") is False  # Claude Code path stays raw


def test_per_app_overrides_per_target():
    cfg = Config(cleanup_backend="haiku", cleanup_apps={"code.exe": False, "slack.exe": True})
    # editor: per-app forces cleanup OFF even though dictate default is ON
    assert cfg.cleanup_enabled("dictate", app="Code.exe") is False
    # slack: per-app forces cleanup ON even on the send target (default OFF)
    assert cfg.cleanup_enabled("send", app="slack.exe") is True
    # unmapped app falls back to the per-target default
    assert cfg.cleanup_enabled("dictate", app="notepad.exe") is True
    assert cfg.cleanup_enabled("send", app="notepad.exe") is False


def test_tray_override_beats_per_app():
    cfg = Config(cleanup_backend="haiku", cleanup_override="off", cleanup_apps={"slack.exe": True})
    assert cfg.cleanup_enabled("dictate", app="slack.exe") is False


def test_backend_off_beats_per_app():
    cfg = Config(cleanup_backend="off", cleanup_apps={"slack.exe": True})
    assert cfg.cleanup_enabled("dictate", app="slack.exe") is False


def test_per_app_lookup_is_case_insensitive():
    cfg = Config(cleanup_backend="haiku", cleanup_apps={"code.exe": False})
    assert cfg.cleanup_enabled("dictate", app="CODE.EXE") is False


def test_cleanup_global_override():
    cfg = Config(cleanup_backend="haiku", cleanup_override="on")
    assert cfg.cleanup_enabled("send") is True
    cfg.cleanup_override = "off"
    assert cfg.cleanup_enabled("dictate") is False


def test_bad_toml_is_one_line_error(tmp_path):
    with pytest.raises(ConfigError) as exc:
        load_config(write(tmp_path, "keys = [broken"))
    assert "TOML" in str(exc.value)


def test_bad_enum_value_rejected(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, '[keys]\ngroq="g"\n[hotkeys]\nmode = "sideways"\n'))


def test_missing_file_with_env_key_still_boots(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_env")
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.groq_api_key == "gsk_env"
    assert cfg.source_path is None


def test_keys_never_in_repr():
    cfg = Config(groq_api_key="gsk_secret", anthropic_api_key="sk-ant-secret")
    assert "gsk_secret" not in repr(cfg)
    assert "sk-ant-secret" not in repr(cfg)


def test_audio_and_groq_model_options(tmp_path):
    path = write(
        tmp_path,
        '[keys]\ngroq = "gsk_x"\n[stt]\ngroq_model = "whisper-large-v3"\n'
        "[audio]\nkeep_open = false\n",
    )
    cfg = load_config(path)
    assert cfg.groq_model == "whisper-large-v3"
    assert cfg.keep_mic_open is False
    defaults = Config()
    assert defaults.keep_mic_open is True
    assert defaults.groq_model == "whisper-large-v3-turbo"
