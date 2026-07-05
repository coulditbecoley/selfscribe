from selfscribe.config import Config
from selfscribe.tray import IDLE_COLOR, RECORDING_COLOR, Tray, dot_image


def make_tray(cfg=None, on_mode=None):
    return Tray(cfg or Config(groq_api_key="k"), on_quit=lambda: None, on_mode_change=on_mode)


def test_status_text_reflects_state():
    tray = make_tray()
    assert "listening" in tray.status_text()
    assert "groq" in tray.status_text()
    tray.recording = True
    assert "RECORDING" in tray.status_text()


def test_set_recording_swaps_icon():
    tray = make_tray()
    icon = tray.build_icon()
    tray.set_recording(True)
    assert icon.icon.tobytes() == dot_image(RECORDING_COLOR).tobytes()
    tray.set_recording(False)
    assert icon.icon.tobytes() == dot_image(IDLE_COLOR).tobytes()


def test_menu_actions_mutate_live_config():
    modes = []
    cfg = Config(groq_api_key="k")
    tray = make_tray(cfg, on_mode=modes.append)
    tray._set_backend("local")
    assert cfg.stt_backend == "local"
    tray._set_mode("toggle")
    assert cfg.hotkey_mode == "toggle"
    assert modes == ["toggle"]
    tray._cycle_cleanup()
    assert cfg.cleanup_override == "on"
    tray._cycle_cleanup()
    assert cfg.cleanup_override == "off"
    tray._cycle_cleanup()
    assert cfg.cleanup_override == ""


def test_app_notifies_recording_state():
    from selfscribe.app import App, FakeRecorder

    cfg = Config(groq_api_key="k", hotkey_dictate="f13", hotkey_send="f14")
    app = App(cfg, recorder=FakeRecorder.__new__(FakeRecorder))
    seen = []
    app.on_recording_change = seen.append
    app._notify_recording(True)
    app._notify_recording(False)
    assert seen == [True, False]
