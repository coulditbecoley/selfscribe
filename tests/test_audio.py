import numpy as np
import pytest

from selfscribe.audio import (
    FRAME_MS,
    MIN_CLIP_MS,
    PREROLL_MS,
    SAMPLE_RATE,
    Clip,
    Recorder,
    clip_from_wav_bytes,
    trim_silence,
)

FRAME_LEN = SAMPLE_RATE * FRAME_MS // 1000


def frames_of(n, value=0):
    return np.full(n * FRAME_LEN, value, dtype=np.int16)


def fake_vad(speech_ranges):
    """is_speech stub: flags frames by index."""
    counter = {"i": -1}

    def is_speech(frame_bytes, sr):
        counter["i"] += 1
        return any(lo <= counter["i"] < hi for lo, hi in speech_ranges)

    return is_speech


def test_trim_keeps_speech_with_padding():
    pcm = frames_of(40)  # 40 frames = 1.2 s
    out = trim_silence(pcm, SAMPLE_RATE, is_speech=fake_vad([(10, 20)]), pad_ms=FRAME_MS)
    # speech frames 10..19 plus one frame of padding each side
    assert out is not None
    assert len(out) == 12 * FRAME_LEN


def test_trim_all_silence_returns_none():
    pcm = frames_of(20)
    assert trim_silence(pcm, SAMPLE_RATE, is_speech=fake_vad([])) is None


def test_trim_speech_at_edges_no_overpad():
    pcm = frames_of(10)
    out = trim_silence(pcm, SAMPLE_RATE, is_speech=fake_vad([(0, 10)]), pad_ms=500)
    assert out is not None
    assert len(out) == len(pcm)  # padding clamps at the buffer bounds


def test_trim_too_short_buffer():
    assert trim_silence(np.zeros(10, dtype=np.int16), SAMPLE_RATE) is None


def test_clip_wav_roundtrip():
    pcm = (np.sin(np.linspace(0, 100, SAMPLE_RATE)) * 10000).astype(np.int16)
    clip = Clip(pcm=pcm)
    restored = clip_from_wav_bytes(clip.wav_bytes())
    assert restored.samplerate == SAMPLE_RATE
    assert np.array_equal(restored.pcm, pcm)
    assert abs(clip.duration_ms - 1000) < 1


def test_recorder_discards_empty_and_short():
    rec = Recorder()
    assert rec._finish([]) is None
    assert rec.discard_reason == "empty"
    short = [np.zeros((int(SAMPLE_RATE * (MIN_CLIP_MS - 100) / 1000), 1), dtype=np.int16)]
    assert rec._finish(short) is None
    assert rec.discard_reason == "too_short"


def test_recorder_discards_real_silence():
    rec = Recorder()
    silence = [np.zeros((SAMPLE_RATE, 1), dtype=np.int16)]  # 1 s of digital silence
    assert rec._finish(silence) is None  # real webrtcvad path
    assert rec.discard_reason == "silence"


def test_real_vad_trims_tts_speech(tts_wav):
    """Integration: webrtcvad finds real (synthesized) speech and trims padding."""
    clip = clip_from_wav_bytes(tts_wav("testing one two three", "vad_speech").read_bytes())
    padded = np.concatenate(
        [np.zeros(SAMPLE_RATE, dtype=np.int16), clip.pcm, np.zeros(SAMPLE_RATE, dtype=np.int16)]
    )
    out = trim_silence(padded, SAMPLE_RATE)
    assert out is not None
    # both full seconds of silence are mostly gone...
    assert len(out) <= len(clip.pcm) + int(0.5 * SAMPLE_RATE)
    # ...and the speech survived
    assert len(out) >= int(0.3 * SAMPLE_RATE)


def test_recorder_accepts_tts_speech_frames(tts_wav):
    """Recorder._finish on real speech yields a trimmed clip, not a discard."""
    clip = clip_from_wav_bytes(tts_wav("testing one two three", "vad_speech").read_bytes())
    rec = Recorder()
    out = rec._finish([clip.pcm.reshape(-1, 1)])
    assert out is not None
    assert rec.discard_reason is None
    assert out.duration_ms > 300


def test_recorder_live_mic_stream():
    """Open a real input stream if a mic exists; room silence discards softly."""
    import sounddevice as sd

    try:
        sd.check_input_settings(samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    except Exception:
        pytest.skip("no usable input device")
    import time

    rec = Recorder()
    rec.start()
    assert rec.recording
    time.sleep(0.6)
    out = rec.stop()
    assert not rec.recording
    # nobody is speaking: either discarded (normal) or ambient noise made a clip
    assert out is None or out.duration_ms > 0
    if out is None:
        assert rec.discard_reason in ("empty", "too_short", "silence")


class FakeStream:
    active = True
    latency = 0.0


def block(ms, value=0):
    return np.full((SAMPLE_RATE * ms // 1000, 1), value, dtype=np.int16)


def keep_open_recorder():
    rec = Recorder(keep_open=True)
    rec._stream = FakeStream()
    rec._last_block = 1e18  # never stale
    return rec


def test_preroll_is_prepended_and_bounded():
    rec = keep_open_recorder()
    for _ in range(20):  # 1 s of idle audio, only ~PREROLL_MS kept
        rec._on_block(block(50, 1), None, None, None)
    rec.start()
    rec._on_block(block(500, 2), None, None, None)
    frames = rec._frames
    preroll = np.concatenate(frames[:-1]).ravel()
    assert set(preroll) == {1}
    assert PREROLL_MS <= len(preroll) * 1000 / SAMPLE_RATE < PREROLL_MS + 50
    assert rec._preroll_samples == len(preroll)


def test_blip_guard_ignores_preroll(monkeypatch):
    """A 100 ms tap stays a 'too_short' discard even with pre-roll in front."""
    rec = keep_open_recorder()
    for _ in range(10):
        rec._on_block(block(50), None, None, None)
    rec.start()
    rec._on_block(block(100), None, None, None)
    assert rec.stop() is None
    assert rec.discard_reason == "too_short"
    assert rec._stream is not None  # keep_open: stream survives the stop


def test_dead_stream_is_reopened_on_start(monkeypatch):
    rec = keep_open_recorder()
    rec._stream.active = False
    opened = []
    monkeypatch.setattr(rec, "open", lambda: opened.append(1))
    rec.start()
    assert opened == [1]
    assert rec.recording
