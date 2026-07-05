"""Mic capture (16 kHz mono, in-memory) + VAD silence trimming.

Audio never touches disk: frames accumulate in RAM and leave this module as
a Clip. trim_silence takes an injectable is_speech(frame_bytes, samplerate)
so the windowing/padding logic is unit-testable without webrtcvad.
"""

import io
import wave
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16000
FRAME_MS = 30  # webrtcvad accepts 10/20/30 ms frames
MIN_CLIP_MS = 300
PAD_MS = 120
VAD_AGGRESSIVENESS = 2


@dataclass
class Clip:
    pcm: np.ndarray  # int16 mono
    samplerate: int = SAMPLE_RATE

    @property
    def duration_ms(self) -> float:
        return len(self.pcm) * 1000.0 / self.samplerate

    def wav_bytes(self) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.samplerate)
            wav.writeframes(self.pcm.astype(np.int16).tobytes())
        return buf.getvalue()


def clip_from_wav_bytes(data: bytes) -> Clip:
    with wave.open(io.BytesIO(data), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError("expected 16-bit mono WAV")
        pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
        return Clip(pcm=pcm, samplerate=wav.getframerate())


def resample(pcm: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    """Linear resample — fine for speech."""
    if from_rate == to_rate or len(pcm) == 0:
        return pcm
    target_len = int(len(pcm) * to_rate / from_rate)
    resampled = np.interp(
        np.linspace(0.0, len(pcm) - 1, target_len),
        np.arange(len(pcm)),
        pcm.astype(np.float64),
    )
    return resampled.astype(pcm.dtype)


def _webrtc_is_speech() -> Callable[[bytes, int], bool]:
    import webrtcvad

    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
    return vad.is_speech


def trim_silence(
    pcm: np.ndarray,
    samplerate: int = SAMPLE_RATE,
    is_speech: Callable[[bytes, int], bool] | None = None,
    pad_ms: int = PAD_MS,
) -> np.ndarray | None:
    """Cut leading/trailing non-speech; None if no speech at all."""
    if is_speech is None:
        is_speech = _webrtc_is_speech()
    frame_len = samplerate * FRAME_MS // 1000
    n_frames = len(pcm) // frame_len
    if n_frames == 0:
        return None
    flags = [
        is_speech(pcm[i * frame_len : (i + 1) * frame_len].tobytes(), samplerate)
        for i in range(n_frames)
    ]
    if not any(flags):
        return None
    first = flags.index(True)
    last = n_frames - 1 - flags[::-1].index(True)
    pad = pad_ms * samplerate // 1000
    start = max(0, first * frame_len - pad)
    end = min(len(pcm), (last + 1) * frame_len + pad)
    return pcm[start:end]


class Recorder:
    """Push-to-talk mic capture: start() on key down, stop() on key up.

    stop() returns a silence-trimmed Clip, or None with discard_reason set to
    'empty' | 'too_short' | 'silence' — a discarded blip is a soft cue for the
    caller, never an error.
    """

    def __init__(self, samplerate: int = SAMPLE_RATE, device: int | str | None = None):
        self.samplerate = samplerate
        self.device = device
        self.discard_reason: str | None = None
        self._frames: list[np.ndarray] = []
        self._stream = None

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        import sounddevice as sd

        if self._stream is not None:
            return
        self._frames = []
        self.discard_reason = None
        self._stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="int16",
            device=self.device,
            callback=self._on_block,
        )
        self._stream.start()

    def _on_block(self, indata, frames, time_info, status) -> None:
        self._frames.append(indata.copy())

    def stop(self) -> Clip | None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        return self._finish(self._frames)

    def _finish(self, frames: list[np.ndarray]) -> Clip | None:
        self._frames = []
        if not frames:
            self.discard_reason = "empty"
            return None
        pcm = np.concatenate(frames).ravel()
        if len(pcm) * 1000.0 / self.samplerate < MIN_CLIP_MS:
            self.discard_reason = "too_short"
            return None
        trimmed = trim_silence(pcm, self.samplerate)
        if trimmed is None:
            self.discard_reason = "silence"
            return None
        return Clip(pcm=trimmed, samplerate=self.samplerate)
