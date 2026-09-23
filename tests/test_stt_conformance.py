"""SS-9 conformance: both backends implement transcribe(clip) -> Transcript
identically, selected purely by config; local inference is truly offline."""

import socket

import pytest

from selfscribe.audio import clip_from_wav_bytes
from selfscribe.config import Config, load_config
from selfscribe.stt import Transcript, get_transcriber, vocab_prompt


def test_vocab_prompt_shape():
    assert vocab_prompt(["SelfScribe", "Coley"]) == "This dictation may mention: SelfScribe, Coley."
    assert vocab_prompt([]) == ""


def test_vocab_fixes_case_and_spacing():
    from selfscribe.stt import apply_vocab_fixes

    vocab = ["HitList", "SelfScribe", "Coley", "Claude Code"]
    assert apply_vocab_fixes("check the Hitlist tracker", vocab) == "check the HitList tracker"
    assert apply_vocab_fixes("open self scribe now", vocab) == "open SelfScribe now"
    assert apply_vocab_fixes("ask claude code", vocab) == "ask Claude Code"


def test_vocab_fixes_edit_distance_one_capitalized_only():
    from selfscribe.stt import apply_vocab_fixes

    vocab = ["Coley", "Skald"]
    assert apply_vocab_fixes("Cooley is building Scald Studio", vocab) == (
        "Coley is building Skald Studio"
    )
    # lowercase common words are never fuzzy-repaired
    assert apply_vocab_fixes("the holey sock is scaled", vocab) == "the holey sock is scaled"
    # distance 2 stays untouched
    assert apply_vocab_fixes("Kohli plays cricket", vocab) == "Kohli plays cricket"


def test_vocab_exact_terms_immune_to_fuzzy_rewrite():
    from selfscribe.stt import apply_vocab_fixes

    # two configured terms within edit distance 1 of each other: a token that
    # exactly matches one must never be rewritten to the other
    vocab = ["Coley", "Cooley"]
    assert apply_vocab_fixes("Cooley said hi", vocab) == "Cooley said hi"
    assert apply_vocab_fixes("Coley said hi", vocab) == "Coley said hi"


def test_vocab_fuzzy_can_be_disabled():
    from selfscribe.stt import apply_vocab_fixes

    vocab = ["Coley"]
    assert apply_vocab_fixes("Cooley said hi", vocab, fuzzy=False) == "Cooley said hi"
    # case repair of direct matches still applies with fuzzy off
    assert apply_vocab_fixes("coley said hi", vocab, fuzzy=False) == "Coley said hi"


def test_vocab_special_char_terms_never_rewrite_ordinary_words():
    from selfscribe.stt import apply_vocab_fixes

    vocab = [".NET", "C++"]
    # '.NET' must not turn 'net' into '.NET', 'C++' must not eat every 'C'
    text = "caught it in the net with plan C in C minor"
    assert apply_vocab_fixes(text, vocab) == text
    # and a backslash-containing term must not raise re.error
    assert apply_vocab_fixes("path stuff", ["term\\with\\slash"]) == "path stuff"


def test_get_transcriber_switches_on_config_only(monkeypatch):
    seen = []

    import selfscribe.stt.groq as groq_mod
    import selfscribe.stt.local as local_mod

    monkeypatch.setattr(
        groq_mod,
        "transcribe",
        lambda clip, key, initial_prompt="", **kw: (
            seen.append("groq") or Transcript("g", 1, "groq")
        ),
    )
    monkeypatch.setattr(
        local_mod,
        "transcribe",
        lambda clip, model, initial_prompt="": seen.append("local") or Transcript("l", 1, "local"),
    )
    assert get_transcriber(Config(groq_api_key="k"))(None).backend == "groq"
    assert get_transcriber(Config(stt_backend="local"))(None).backend == "local"
    assert seen == ["groq", "local"]


@pytest.fixture(scope="module")
def speech_clip(request):
    tts = request.getfixturevalue("tts_wav")
    return clip_from_wav_bytes(
        tts("testing one two three, the quick brown fox", "groq_live").read_bytes()
    )


@pytest.mark.live
@pytest.mark.parametrize("backend", ["groq", "local"])
def test_conformance_both_backends(backend, speech_clip):
    cfg = load_config()
    if backend == "groq" and not cfg.groq_api_key:
        pytest.skip("no groq key")
    cfg.stt_backend = backend
    result = get_transcriber(cfg)(speech_clip)
    assert isinstance(result, Transcript)
    assert result.backend == backend
    assert result.ms > 0
    assert "quick brown fox" in result.text.lower()
    print(f"\n{backend}: {result.ms:.0f}ms -> {result.text!r}")


@pytest.mark.live
def test_local_inference_is_offline(speech_clip):
    """AC: with the network off, local dictation still transcribes."""
    from selfscribe.stt.local import _get_model

    _get_model("base.en")  # warm the cache (may download once)

    real_socket = socket.socket

    def no_network(*args, **kwargs):
        raise AssertionError("network call during local inference")

    socket.socket = no_network
    try:
        cfg = Config(stt_backend="local")
        result = get_transcriber(cfg)(speech_clip)
        assert "quick brown fox" in result.text.lower()
    finally:
        socket.socket = real_socket


def test_groq_failure_falls_back_to_local(monkeypatch):
    import selfscribe.stt as stt
    import selfscribe.stt.groq as groq_mod
    import selfscribe.stt.local as local_mod
    from selfscribe.stt import BackendUnavailable, TranscriptionError

    def groq_down(clip, key, **kw):
        raise BackendUnavailable("Groq timed out after 15s.")

    monkeypatch.setattr(groq_mod, "transcribe", groq_down)
    monkeypatch.setattr(
        local_mod, "transcribe", lambda clip, model, initial_prompt="": Transcript("l", 1, "local")
    )
    monkeypatch.setattr(stt, "local_available", lambda: True)
    assert get_transcriber(Config(groq_api_key="k"))(None).backend == "local"

    monkeypatch.setattr(stt, "local_available", lambda: False)
    with pytest.raises(BackendUnavailable):
        get_transcriber(Config(groq_api_key="k"))(None)

    # a bad key is a config problem to surface, never masked by the fallback
    def bad_key(clip, key, **kw):
        raise TranscriptionError("Groq rejected the API key (401)")

    monkeypatch.setattr(groq_mod, "transcribe", bad_key)
    monkeypatch.setattr(stt, "local_available", lambda: True)
    with pytest.raises(TranscriptionError, match="401"):
        get_transcriber(Config(groq_api_key="k"))(None)


def test_groq_model_comes_from_config(monkeypatch):
    import selfscribe.stt.groq as groq_mod

    seen = {}
    monkeypatch.setattr(
        groq_mod,
        "transcribe",
        lambda clip, key, initial_prompt="", model="": seen.update(model=model)
        or Transcript("g", 1, "groq"),
    )
    get_transcriber(Config(groq_api_key="k", groq_model="whisper-large-v3"))(None)
    assert seen["model"] == "whisper-large-v3"
