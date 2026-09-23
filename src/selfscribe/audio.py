"""Mic capture (16 kHz mono, in-memory) + VAD silence trimming.

Audio never touches disk: frames accumulate in RAM and leave this module as
a Clip. trim_silence takes an injectable is_speech(frame_bytes, samplerate)
so the windowing/padding logic is unit-testable without webrtcvad.
"""

import io
import threading
import time
import wave
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16000
FRAME_MS = 30  # webrtcvad accepts 10/20/30 ms frames
MIN_CLIP_MS = 300
PAD_MS = 120
VAD_AGGRESSIVENESS = 2
PREROLL_MS = 250  # audio kept from just before the key press (keep_open only)
STALE_S = 2.0  # no audio callback for this long -> reopen the stream


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

    keep_open=True holds one input stream open for the whole session: start()
    then just flips a flag (no device open on the hotkey hook thread, which
    Windows drops if a callback blocks ~300 ms) and the last PREROLL_MS of
    audio is prepended, so a word begun as the combo lands isn't clipped.
    keep_open=False opens/closes the device per press (mic indicator only
    lit while recording).
    """

    def __init__(
        self,
        samplerate: int = SAMPLE_RATE,
        device: int | str | None = None,
        keep_open: bool = False,
    ):
        self.samplerate = samplerate
        self.device = device
        self.keep_open = keep_open
        self.discard_reason: str | None = None
        self._frames: list[np.ndarray] = []
        self._preroll: deque[np.ndarray] = deque()
        self._preroll_len = 0
        self._preroll_samples = 0  # pre-roll length at the head of _frames
        self._recording = False
        self._stream = None
        self._last_block = 0.0
        self._lock = threading.Lock()  # audio callback thread vs hotkey thread

    @property
    def recording(self) -> bool:
        return self._recording

    def open(self) -> None:
        """Open the input stream now (startup), or reopen a dead one."""
        import sounddevice as sd

        self.close()
        with self._lock:  # never prepend audio from a previous stream
            self._preroll.clear()
            self._preroll_len = 0
        stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="int16",
            device=self.device,
            callback=self._on_block,
        )
        stream.start()
        self._last_block = time.monotonic()
        self._stream = stream

    def close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:  # device already gone: nothing left to release
                pass

    def _stream_dead(self) -> bool:
        # An unplugged/sleep-resumed device can leave the stream "open" but
        # silent; no callback for STALE_S means reopen before recording.
        return (
            self._stream is None
            or not self._stream.active
            or time.monotonic() - self._last_block > STALE_S
        )

    def start(self) -> None:
        if self._recording:
            return
        if self._stream_dead():
            self.open()
        with self._lock:
            self._frames = list(self._preroll)
            self._preroll_samples = self._preroll_len
            self._preroll.clear()
            self._preroll_len = 0
            self.discard_reason = None
            self._recording = True

    def _on_block(self, indata, frames, time_info, status) -> None:
        block = indata.copy()
        self._last_block = time.monotonic()
        with self._lock:
            if self._recording:
                self._frames.append(block)
                return
            self._preroll.append(block)
            self._preroll_len += len(block)
            limit = self.samplerate * PREROLL_MS // 1000
            while self._preroll and self._preroll_len - len(self._preroll[0]) >= limit:
                self._preroll_len -= len(self._preroll.popleft())

    def stop(self) -> Clip | None:
        if self.keep_open and self._recording and self._stream is not None:
            # Let the driver deliver the audio still in flight at key release
            # (closing the stream used to drain it). ~60 ms on a USB headset.
            time.sleep(min(self._stream.latency + 0.03, 0.2))
        with self._lock:
            self._recording = False
            frames, self._frames = self._frames, []
            preroll, self._preroll_samples = self._preroll_samples, 0
        if not self.keep_open:
            self.close()
        return self._finish(frames, preroll_samples=preroll)

    def _finish(self, frames: list[np.ndarray], preroll_samples: int = 0) -> Clip | None:
        self._frames = []
        if not frames:
            self.discard_reason = "empty"
            return None
        pcm = np.concatenate(frames).ravel()
        # blip guard measures the key press only, not the prepended pre-roll
        if (len(pcm) - preroll_samples) * 1000.0 / self.samplerate < MIN_CLIP_MS:
            self.discard_reason = "too_short"
            return None
        trimmed = trim_silence(pcm, self.samplerate)
        if trimmed is None:
            self.discard_reason = "silence"
            return None
        return Clip(pcm=trimmed, samplerate=self.samplerate)
