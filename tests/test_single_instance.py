import selfscribe.single_instance as si


def test_second_acquire_is_refused_while_first_holds(monkeypatch):
    """The real mutex is process-global; simulate the OS layer so the guard
    logic is tested deterministically."""
    state = {"exists": False, "last_error": 0}

    class FakeKernel:
        def CreateMutexW(self, attrs, owned, name):
            if state["exists"]:
                state["last_error"] = si.ERROR_ALREADY_EXISTS
                return 12345  # a handle is still returned on ALREADY_EXISTS
            state["exists"] = True
            state["last_error"] = 0
            return 12345

        def GetLastError(self):
            return state["last_error"]

        def CloseHandle(self, h):
            return True

    class FakeWinDLL:
        kernel32 = FakeKernel()

    monkeypatch.setattr(si.ctypes, "windll", FakeWinDLL())
    monkeypatch.setattr(si, "_handle", None)

    assert si.acquire() is True  # first instance takes the mutex
    assert si.acquire() is False  # second instance is refused


def test_acquire_does_not_block_when_os_call_fails(monkeypatch):
    class FakeKernel:
        def CreateMutexW(self, *a):
            return 0  # failure

        def GetLastError(self):
            return 0

    class FakeWinDLL:
        kernel32 = FakeKernel()

    monkeypatch.setattr(si.ctypes, "windll", FakeWinDLL())
    assert si.acquire() is True  # never blocks the app on failure
