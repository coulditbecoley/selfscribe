import pytest

from selfscribe.hotkeys import ComboTracker, normalize_key, parse_combo

DICTATE = frozenset({"ctrl", "windows"})
SEND = frozenset({"ctrl", "alt", "windows"})


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class Recorder:
    def __init__(self):
        self.events = []

    def start(self, target):
        self.events.append(("start", target))

    def stop(self, target):
        self.events.append(("stop", target))

    def upgrade(self, target):
        self.events.append(("upgrade", target))


def make(mode):
    rec, clock = Recorder(), FakeClock()
    tracker = ComboTracker(
        {"dictate": DICTATE, "send": SEND},
        mode,
        on_start=rec.start,
        on_stop=rec.stop,
        on_upgrade=rec.upgrade,
        clock=clock,
    )
    return tracker, rec, clock


def test_parse_combo_normalizes():
    assert parse_combo("Ctrl+Win") == frozenset({"ctrl", "windows"})
    assert parse_combo("left ctrl + right alt + windows") == SEND
    with pytest.raises(ValueError):
        parse_combo("  ")


def test_normalize_key_variants():
    assert normalize_key("Left Windows") == "windows"
    assert normalize_key("right ctrl") == "ctrl"
    assert normalize_key("F13") == "f13"
    # pynput-style names
    assert normalize_key("cmd") == "windows"
    assert normalize_key("cmd_r") == "windows"
    assert normalize_key("ctrl_l") == "ctrl"
    assert normalize_key("alt_gr") == "alt"
    assert normalize_key("shift_r") == "shift"


def test_pynput_key_name_mapping():
    from pynput import keyboard as pk

    from selfscribe.hotkeys import pynput_key_name

    assert pynput_key_name(pk.Key.cmd, pk.KeyCode) == "windows"
    assert pynput_key_name(pk.Key.ctrl_l, pk.KeyCode) == "ctrl"
    assert pynput_key_name(pk.Key.f13, pk.KeyCode) == "f13"
    assert pynput_key_name(pk.KeyCode(char="A"), pk.KeyCode) == "a"
    # ctrl+a arrives as the control char \x01 with vk 65
    assert pynput_key_name(pk.KeyCode(char="\x01", vk=65), pk.KeyCode) == "a"


def test_hold_start_and_stop():
    tracker, rec, _ = make("hold")
    tracker.handle("ctrl", True)
    tracker.handle("windows", True)
    assert rec.events == [("start", "dictate")]
    tracker.handle("windows", False)
    assert rec.events == [("start", "dictate"), ("stop", "dictate")]


def test_hold_superset_pressed_all_at_once_prefers_send():
    tracker, rec, _ = make("hold")
    tracker.handle("ctrl", True)
    tracker.handle("alt", True)
    tracker.handle("windows", True)
    assert rec.events[0] == ("start", "send")


def test_hold_upgrades_to_send_within_grace():
    tracker, rec, clock = make("hold")
    tracker.handle("ctrl", True)
    tracker.handle("windows", True)  # dictate fires first
    clock.t = 0.1
    tracker.handle("alt", True)  # superset completes inside grace
    tracker.handle("alt", False)
    assert rec.events == [("start", "dictate"), ("upgrade", "send"), ("stop", "send")]


def test_hold_does_not_upgrade_after_grace():
    tracker, rec, clock = make("hold")
    tracker.handle("ctrl", True)
    tracker.handle("windows", True)
    clock.t = 5.0
    tracker.handle("alt", True)
    tracker.handle("ctrl", False)
    assert rec.events == [("start", "dictate"), ("stop", "dictate")]


def test_toggle_press_starts_press_stops():
    tracker, rec, clock = make("toggle")
    tracker.handle("ctrl", True)
    tracker.handle("windows", True)
    tracker.handle("windows", False)
    tracker.handle("ctrl", False)
    assert rec.events == [("start", "dictate")]
    clock.t = 3.0  # past grace: this press is a stop, not an upgrade echo
    tracker.handle("ctrl", True)
    tracker.handle("windows", True)
    assert rec.events == [("start", "dictate"), ("stop", "dictate")]


def test_toggle_superset_press_upgrades_not_stops():
    tracker, rec, clock = make("toggle")
    tracker.handle("ctrl", True)
    tracker.handle("windows", True)  # start dictate
    clock.t = 0.05
    tracker.handle("alt", True)  # same gesture completes send combo
    assert rec.events == [("start", "dictate"), ("upgrade", "send")]
    for k in ("ctrl", "windows", "alt"):
        tracker.handle(k, False)
    clock.t = 4.0
    tracker.handle("ctrl", True)
    tracker.handle("windows", True)
    assert rec.events[-1] == ("stop", "send")


def test_disjoint_binding_ignored_while_hold_active():
    bindings = {"dictate": frozenset({"f13"}), "send": frozenset({"f14"})}
    rec = Recorder()
    tracker = ComboTracker(bindings, "hold", rec.start, rec.stop, rec.upgrade)
    tracker.handle("f13", True)
    tracker.handle("f14", True)  # other binding while active: no new session
    tracker.handle("f14", False)
    assert rec.events == [("start", "dictate")]
    tracker.handle("f13", False)
    assert rec.events == [("start", "dictate"), ("stop", "dictate")]


def test_bad_mode_rejected():
    with pytest.raises(ValueError):
        ComboTracker({"d": DICTATE}, "sideways", lambda t: None, lambda t: None)
