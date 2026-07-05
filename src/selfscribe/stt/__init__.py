"""Speech-to-text backends. All expose transcribe(clip, ...) -> Transcript."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Transcript:
    text: str
    ms: float  # end-to-end transcription latency
    backend: str


class TranscriptionError(Exception):
    """Transcription failed; message is one printable line for the user."""


def vocab_prompt(vocab: list[str]) -> str:
    """Whisper initial_prompt biasing proper nouns upstream (SS-11)."""
    return ", ".join(vocab) + "." if vocab else ""


def get_transcriber(cfg) -> Callable[..., Transcript]:
    """Backend-agnostic transcribe(clip) from config — the SS-9 interface."""
    prompt = vocab_prompt(cfg.vocab)
    if cfg.stt_backend == "local":
        from selfscribe.stt import local

        return lambda clip: local.transcribe(clip, cfg.local_model, initial_prompt=prompt)
    from selfscribe.stt import groq

    return lambda clip: groq.transcribe(clip, cfg.groq_api_key, initial_prompt=prompt)
