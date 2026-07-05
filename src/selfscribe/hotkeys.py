"""Global hotkeys: hold-to-talk and press-to-toggle for two bindings.

ComboTracker is a pure state machine over (key, down/up) events so both modes
are unit-testable; HotkeyListener adapts pynput's global hook onto it (the
unmaintained `keyboard` library's hook silently receives nothing on this
Python 3.12 / Win 11 setup — verified against a raw WH_KEYBOARD_LL hook,
which works, and pynput, which works). Because the send binding may be a
superset of the dictate binding (ctrl+alt+win vs ctrl+win), a session that
starts as one target may be *upgraded* to a more specific target within a
short grace window — the audio is identical either way, only the routing
changes.
"""

import time
from collections.abc import Callable

# Seconds after session start during which a more specific combo takes over.
UPGRADE_GRACE_S = 0.35

_NORMALIZE = {
    "win": "windows",
    "cmd": "windows",  # pynput's name for the Windows key
    "control": "ctrl",
    "alt_gr": "alt",
}


def normalize_key(name: str) -> str:
    name = name.strip().lower()
    for prefix in ("left ", "right "):
        name = name.removeprefix(prefix)
    if name != "alt_gr":
        name = name.removesuffix("_l").removesuffix("_r")
    return _NORMALIZE.get(name, name)


def parse_combo(combo: str) -> frozenset[str]:
    keys = frozenset(normalize_key(part) for part in combo.split("+") if part.strip())
    if not keys:
        raise ValueError(f"empty hotkey combo: {combo!r}")
    return keys


class ComboTracker:
    """Tracks pressed keys and drives start/stop callbacks for named bindings."""

    def __init__(
        self,
        bindings: dict[str, frozenset[str]],
        mode: str,
        on_start: Callable[[str], None],
        on_stop: Callable[[str], None],
        on_upgrade: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        if mode not in ("hold", "toggle"):
            raise ValueError(f"mode must be 'hold' or 'toggle', got {mode!r}")
        self.bindings = bindings
        self.mode = mode
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_upgrade = on_upgrade
        self.clock = clock
        self.pressed: set[str] = set()
        self.active: str | None = None
        self._started_at = 0.0

    def handle(self, key: str, is_down: bool) -> None:
        before = self._satisfied()
        if is_down:
            self.pressed.add(key)
        else:
            self.pressed.discard(key)
        newly = self._satisfied() - before
        if self.mode == "hold":
            self._handle_hold(newly)
        else:
            self._handle_toggle(newly, is_down)

    def _satisfied(self) -> set[str]:
        return {t for t, keys in self.bindings.items() if keys <= self.pressed}

    def _most_specific(self, targets: set[str]) -> str:
        return max(targets, key=lambda t: len(self.bindings[t]))

    def _handle_hold(self, newly: set[str]) -> None:
        if self.active is None:
            satisfied = self._satisfied()
            if satisfied:
                self._start(self._most_specific(satisfied))
            return
        upgrades = {t for t in newly if self.bindings[t] > self.bindings[self.active]}
        if upgrades and self._within_grace():
            self._upgrade(self._most_specific(upgrades))
        elif not self.bindings[self.active] <= self.pressed:
            self._stop()

    def _handle_toggle(self, newly: set[str], is_down: bool) -> None:
        if not is_down or not newly:
            return
        target = self._most_specific(newly)
        if self.active is None:
            self._start(target)
        elif self.bindings[target] > self.bindings[self.active] and self._within_grace():
            self._upgrade(target)
        elif not self._within_grace():
            # Any tracked combo pressed again ends the session. Ignore presses
            # inside the grace window so the toggle-start keystroke itself
            # (subset fires before superset) can't immediately stop it.
            self._stop()

    def _within_grace(self) -> bool:
        return self.clock() - self._started_at <= UPGRADE_GRACE_S

    def _start(self, target: str) -> None:
        self.active = target
        self._started_at = self.clock()
        self.on_start(target)

    def _upgrade(self, target: str) -> None:
        self.active = target
        if self.on_upgrade:
            self.on_upgrade(target)

    def _stop(self) -> None:
        target, self.active = self.active, None
        if target is not None:
            self.on_stop(target)


def pynput_key_name(key, keycode_type) -> str:
    """Map a pynput key object to a normalized combo key name."""
    if isinstance(key, keycode_type):
        if key.char and key.char.isprintable():
            return key.char.lower()
        vk = key.vk or 0
        if 0x41 <= vk <= 0x5A:  # letters arrive as control chars while ctrl is held
            return chr(vk).lower()
        if 0x30 <= vk <= 0x39:
            return chr(vk)
        return f"vk{vk}"
    return normalize_key(key.name)


class HotkeyListener:
    """Adapts pynput's global keyboard hook onto a ComboTracker."""

    def __init__(
        self,
        dictate_combo: str,
        send_combo: str,
        mode: str,
        on_start: Callable[[str], None],
        on_stop: Callable[[str], None],
        on_upgrade: Callable[[str], None] | None = None,
    ):
        bindings = {
            "dictate": parse_combo(dictate_combo),
            "send": parse_combo(send_combo),
        }
        self.tracker = ComboTracker(bindings, mode, on_start, on_stop, on_upgrade)
        self._listener = None

    def start(self) -> None:
        from pynput import keyboard as pk  # lazy: installs a global OS hook

        self._listener = pk.Listener(
            on_press=lambda key: self._on_event(key, True, pk.KeyCode),
            on_release=lambda key: self._on_event(key, False, pk.KeyCode),
        )
        self._listener.start()
        self._listener.wait()

    def _on_event(self, key, is_down: bool, keycode_type) -> None:
        if key is None:
            return
        self.tracker.handle(pynput_key_name(key, keycode_type), is_down)

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
