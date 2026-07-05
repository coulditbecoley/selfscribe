"""Speech-to-text backends. All expose transcribe(clip, ...) -> Transcript."""

from dataclasses import dataclass


@dataclass
class Transcript:
    text: str
    ms: float  # end-to-end transcription latency
    backend: str


class TranscriptionError(Exception):
    """Transcription failed; message is one printable line for the user."""
