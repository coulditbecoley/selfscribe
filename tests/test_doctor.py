from selfscribe.config import Config
from selfscribe.doctor import check_cleanup, check_vad


def test_cleanup_check_matches_runtime_semantics(capsys):
    # haiku configured but disabled for both targets: run works, check must too
    cfg = Config(cleanup_backend="haiku", cleanup_dictate=False, cleanup_send=False)
    assert check_cleanup(cfg) is True
    cfg = Config(cleanup_backend="haiku", cleanup_override="off")
    assert check_cleanup(cfg) is True
    # actually in use without a key -> FAIL, matching config._validate
    cfg = Config(cleanup_backend="haiku")
    assert check_cleanup(cfg) is False
    out = capsys.readouterr()
    assert "anthropic" in (out.out + out.err)


def test_vad_check_runs_without_assert():
    assert check_vad() is True
