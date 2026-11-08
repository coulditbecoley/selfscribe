"""macOS helpers that are pure Python and testable on any OS."""

import os
import stat
import sys

import pytest

from selfscribe import macos


def test_save_groq_key_creates_config(tmp_path):
    path = tmp_path / "config.toml"
    macos.save_groq_key("gsk_new", path)
    assert path.read_text() == '[keys]\ngroq = "gsk_new"\n\n'


def test_save_groq_key_keeps_other_settings(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[hotkeys]\nmode = "toggle"\n')
    macos.save_groq_key("gsk_new", path)
    text = path.read_text()
    assert 'groq = "gsk_new"' in text
    assert 'mode = "toggle"' in text


def test_save_groq_key_fills_existing_keys_table(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[keys]\nanthropic = "sk-x"\n')
    macos.save_groq_key("gsk_new", path)
    import tomllib

    keys = tomllib.loads(path.read_text())["keys"]
    assert keys == {"groq": "gsk_new", "anthropic": "sk-x"}


def test_save_groq_key_replaces_old_key(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[keys]\ngroq = "gsk_old"\n')
    macos.save_groq_key("gsk_new", path)
    assert "gsk_old" not in path.read_text()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_saved_key_file_is_owner_only(tmp_path):
    path = macos.save_groq_key("gsk_new", tmp_path / "config.toml")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_dialog_text_is_passed_as_argv_not_script(monkeypatch):
    """A quote in the message must not be able to break out of the AppleScript."""
    seen = {}

    class Done:
        returncode, stdout = 0, ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return Done()

    monkeypatch.setattr(macos.subprocess, "run", fake_run)
    macos.alert('hi" & do shell script "rm -rf ~')
    assert seen["cmd"][:2] == ["osascript", "-e"]
    assert 'rm -rf' not in seen["cmd"][2]
    assert seen["cmd"][3] == 'hi" & do shell script "rm -rf ~'


def test_first_run_prompts_for_key_on_mac(monkeypatch, tmp_path):
    from selfscribe import app as app_module
    from selfscribe import config as config_module

    path = tmp_path / "config.toml"
    monkeypatch.setenv("SELFSCRIBE_CONFIG", str(path))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(app_module.sys, "platform", "darwin")
    monkeypatch.setattr(macos, "ask_groq_key", lambda: "gsk_typed")
    monkeypatch.setattr(macos, "DEFAULT_CONFIG_PATH", path)
    real_save = macos.save_groq_key
    monkeypatch.setattr(macos, "save_groq_key", lambda key: real_save(key, path))
    cfg = app_module._load_config_first_run()
    assert cfg.groq_api_key == "gsk_typed"
    assert config_module.load_config(path).groq_api_key == "gsk_typed"
