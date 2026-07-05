"""Speech-to-text backends. All expose transcribe(clip, ...) -> Transcript."""

import re
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
    """Whisper initial_prompt biasing proper nouns upstream (SS-11).

    Whisper treats initial_prompt as preceding transcript context, so a
    natural sentence naming the terms biases better than a bare list.
    """
    if not vocab:
        return ""
    return f"This dictation may mention: {', '.join(vocab)}."


def _edit_distance(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 1:
        return 2  # capped: we only care about distance <= 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _term_pattern(term: str) -> str:
    """Case/spacing-tolerant regex for a vocab term (HitList ~ hitlist ~ hit list)."""
    parts = re.findall(r"[A-Z]+[a-z0-9]*|[a-z0-9]+", term) or [term]
    return r"\b" + r"\s?".join(re.escape(p) for p in parts) + r"\b"


def apply_vocab_fixes(text: str, vocab: list[str]) -> str:
    """Deterministic post-STT repair toward the exact configured term forms.

    The initial_prompt bias gets the sound right but models still pick their
    own spelling/casing (Groq turbo renders a clearly-biased 'Coley' as
    'Cooley'). Two conservative passes: (1) case/spacing repair of direct
    matches; (2) edit-distance-1 repair, capitalized tokens only, so common
    lowercase words are never touched. Zero latency, applies to any backend.
    """
    for term in vocab:
        text = re.sub(_term_pattern(term), term, text, flags=re.IGNORECASE)
    terms_by_lower = {t.lower(): t for t in vocab if " " not in t}

    def fix_token(match: re.Match) -> str:
        token = match.group(0)
        low = token.lower()
        if low in terms_by_lower:
            return terms_by_lower[low]
        for term_low, term in terms_by_lower.items():
            if len(term_low) >= 4 and _edit_distance(low, term_low) == 1:
                return term
        return token

    return re.sub(r"\b[A-Z][A-Za-z]+\b", fix_token, text)


def get_transcriber(cfg) -> Callable[..., Transcript]:
    """Backend-agnostic transcribe(clip) from config — the SS-9 interface."""
    prompt = vocab_prompt(cfg.vocab)
    if cfg.stt_backend == "local":
        from selfscribe.stt import local as backend_mod

        def raw(clip):
            return backend_mod.transcribe(clip, cfg.local_model, initial_prompt=prompt)
    else:
        from selfscribe.stt import groq as backend_mod

        def raw(clip):
            return backend_mod.transcribe(clip, cfg.groq_api_key, initial_prompt=prompt)

    def transcribe_with_vocab(clip) -> Transcript:
        transcript = raw(clip)
        transcript.text = apply_vocab_fixes(transcript.text, cfg.vocab)
        return transcript

    return transcribe_with_vocab
