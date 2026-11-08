import sys

import pytest

import selfscribe.single_instance as si


def test_first_acquires_second_refused(monkeypatch):
    """acquire() logic over the _create_mutex OS seam (real cross-process
    behavior is covered by the end-to-end check in the build notes)."""
    calls = {"n": 0}

    def fake_create(name):
        calls["n"] += 1
        return (True, 111) if calls["n"] == 1 else (False, None)

    monkeypatch.setattr(si, "_create_mutex", fake_create)
    monkeypatch.setattr(si, "_handle", None)
    assert si.acquire() is True
    assert si.acquire() is False


def test_acquire_never_blocks_when_os_unavailable(monkeypatch):
    monkeypatch.setattr(si, "_create_mutex", lambda name: (True, None))
    assert si.acquire() is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows shortcut/mutex API")
def test_real_mutex_refuses_a_second_holder(monkeypatch):
    """Against the real Win32 mutex: a throwaway name, acquired twice in-process
    (the OS refuses the 2nd CreateMutexW with ERROR_ALREADY_EXISTS)."""
    monkeypatch.setattr(si, "MUTEX_NAME", "selfscribe-unittest-mutex-abc123")
    acquired1, handle1 = si._create_mutex(si.MUTEX_NAME)
    try:
        assert acquired1 is True and handle1
        acquired2, _ = si._create_mutex(si.MUTEX_NAME)
        assert acquired2 is False  # same process, mutex already exists
    finally:
        import ctypes

        ctypes.windll.kernel32.CloseHandle(handle1)
