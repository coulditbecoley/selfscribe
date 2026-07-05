from selfscribe.inject import InjectionResult, inject_text


class FakeClipboard:
    def __init__(self, initial="previous"):
        self.value = initial
        self.history = []

    def paste(self):
        return self.value

    def copy(self, text):
        self.value = text
        self.history.append(text)


class FakeKeys:
    def __init__(self, paste_raises=False):
        self.calls = []
        self.paste_raises = paste_raises

    def paste(self, use_shift):
        if self.paste_raises:
            raise RuntimeError("paste blocked")
        self.calls.append(("paste", use_shift))

    def type_text(self, text):
        self.calls.append(("type", text))

    def enter(self):
        self.calls.append(("enter",))


def test_paste_sets_then_restores_clipboard():
    clip, keys = FakeClipboard("KEEP ME"), FakeKeys()
    result = inject_text(
        "hello", keys=keys, clipboard=clip, sleep=lambda s: None, terminal_focused=False
    )
    assert result == InjectionResult(method="paste", used_shift=False, clipboard_restored=True)
    assert clip.history == ["hello", "KEEP ME"]
    assert clip.value == "KEEP ME"
    assert keys.calls == [("paste", False)]


def test_terminal_gets_ctrl_shift_v():
    keys = FakeKeys()
    result = inject_text(
        "ls", keys=keys, clipboard=FakeClipboard(), sleep=lambda s: None, terminal_focused=True
    )
    assert result.used_shift is True
    assert keys.calls == [("paste", True)]


def test_paste_failure_falls_back_to_typing():
    keys = FakeKeys(paste_raises=True)
    clip = FakeClipboard("old")
    result = inject_text(
        "fallback text", keys=keys, clipboard=clip, sleep=lambda s: None, terminal_focused=False
    )
    assert result.method == "type"
    assert ("type", "fallback text") in keys.calls
    assert clip.value == "old"  # still restored


def test_explicit_type_method_skips_clipboard():
    clip, keys = FakeClipboard("untouched"), FakeKeys()
    result = inject_text("typed", method="type", keys=keys, clipboard=clip, sleep=lambda s: None)
    assert result.method == "type"
    assert clip.history == []
    assert clip.value == "untouched"


def test_press_enter_after_injection():
    keys = FakeKeys()
    inject_text(
        "prompt",
        press_enter=True,
        keys=keys,
        clipboard=FakeClipboard(),
        sleep=lambda s: None,
        terminal_focused=False,
    )
    assert keys.calls == [("paste", False), ("enter",)]


def test_no_enter_by_default():
    keys = FakeKeys()
    inject_text(
        "text", keys=keys, clipboard=FakeClipboard(), sleep=lambda s: None, terminal_focused=False
    )
    assert ("enter",) not in keys.calls
