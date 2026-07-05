"""Local faster-whisper backend — free, offline, private.

The model lazy-loads on first use and is cached per process (first call pays
model load + download; later calls are inference-only). Inference makes no
network calls once the model is on disk.
"""

import threading
import time

import numpy as np

from selfscribe.audio import Clip, resample
from selfscribe.stt import Transcript, TranscriptionError

DEFAULT_MODEL = "base.en"
_models: dict[str, object] = {}
_models_lock = threading.Lock()  # warm-preload thread races the first utterance


def _get_model(name: str):
    with _models_lock:
        if name not in _models:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise TranscriptionError(
                    "Local backend needs faster-whisper — run: pip install selfscribe[local]"
                ) from exc
            _models[name] = WhisperModel(name, device="cpu", compute_type="int8")
        return _models[name]


WHISPER_RATE = 16000


def transcribe(
    clip: Clip,
    model_name: str = DEFAULT_MODEL,
    initial_prompt: str = "",
) -> Transcript:
    started = time.perf_counter()
    model = _get_model(model_name)
    # faster-whisper assumes 16 kHz for raw ndarray input; resample anything
    # else so it isn't interpreted at the wrong speed.
    pcm = resample(clip.pcm, clip.samplerate, WHISPER_RATE)
    audio = pcm.astype(np.float32) / 32768.0
    segments, _info = model.transcribe(
        audio,
        language="en",
        initial_prompt=initial_prompt or None,
    )
    text = " ".join(segment.text.strip() for segment in segments).strip()
    elapsed_ms = (time.perf_counter() - started) * 1000
    return Transcript(text=text, ms=elapsed_ms, backend="local")
