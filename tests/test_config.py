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


def test_per_target_cleanup_defaults():
    cfg = Config(cleanup_backend="haiku", anthropic_api_key="k")
    assert cfg.cleanup_enabled("dictate") is True  # docs/email path cleans
    assert cfg.cleanup_enabled("send") is False  # Claude Code path stays raw


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
