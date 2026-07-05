"""SS-9 conformance: both backends implement transcribe(clip) -> Transcript
identically, selected purely by config; local inference is truly offline."""

import socket

import pytest

from selfscribe.audio import clip_from_wav_bytes
from selfscribe.config import Config, load_config
from selfscribe.stt import Transcript, get_transcriber, vocab_prompt


def test_vocab_prompt_shape():
    assert vocab_prompt(["SelfScribe", "Coley"]) == "SelfScribe, Coley."
    assert vocab_prompt([]) == ""


def test_get_transcriber_switches_on_config_only(monkeypatch):
    seen = []

    import selfscribe.stt.groq as groq_mod
    import selfscribe.stt.local as local_mod

    monkeypatch.setattr(
        groq_mod,
        "transcribe",
        lambda clip, key, initial_prompt="": seen.append("groq") or Transcript("g", 1, "groq"),
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
