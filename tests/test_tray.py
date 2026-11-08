from selfscribe.assets import render_icon
from selfscribe.config import Config
from selfscribe.tray import IDLE_IMAGE, RECORDING_COLOR, RECORDING_IMAGE, Tray


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
    assert icon.icon is RECORDING_IMAGE
    tray.set_recording(False)
    assert icon.icon is IDLE_IMAGE


def test_tray_idle_icon_matches_app_icon():
    """Tray shows the same mic art as the desktop/taskbar shortcut."""
    assert IDLE_IMAGE.tobytes() == render_icon(64).tobytes()
    assert RECORDING_IMAGE.tobytes() == render_icon(64, bg=RECORDING_COLOR).tobytes()


def test_menu_actions_mutate_live_config(monkeypatch):
    import sys
    import types

    # the optional local backend may not be installed (CI); stub its import
    monkeypatch.setitem(sys.modules, "faster_whisper", types.ModuleType("faster_whisper"))
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


def test_backend_switch_refused_without_key():
    cfg = Config(stt_backend="local", groq_api_key="")
    tray = make_tray(cfg)
    tray._set_backend("groq")
    assert cfg.stt_backend == "local"  # refused: no key, would break every utterance


def test_mode_switch_stops_active_recording(monkeypatch):
    from selfscribe.app import App

    class StubListener:
        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr(App, "_build_listener", lambda self, mode: StubListener())
    cfg = Config(groq_api_key="k", hotkey_dictate="f13", hotkey_send="f14")

    class StubRecorder:
        def __init__(self):
            self.recording = True
            self.stopped = 0
            self.discard_reason = None

        def stop(self):
            self.recording = False
            self.stopped += 1
            return None

    app = App(cfg, recorder=StubRecorder())
    states = []
    app.on_recording_change = states.append
    app.set_hotkey_mode("toggle")
    assert app.recorder.stopped == 1  # orphaned session closed
    assert states == [False]
    assert cfg.hotkey_mode == "toggle"


def test_app_notifies_recording_state():
    from selfscribe.app import App, FakeRecorder

    cfg = Config(groq_api_key="k", hotkey_dictate="f13", hotkey_send="f14")
    app = App(cfg, recorder=FakeRecorder.__new__(FakeRecorder))
    seen = []
    app.on_recording_change = seen.append
    app._notify_recording(True)
    app._notify_recording(False)
    assert seen == [True, False]
