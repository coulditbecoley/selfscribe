"""SS-10: the WAV corpus regression suite — no mic required.

Each case synthesizes a scripted clip (cached), runs the real pipeline
(Groq + vocab bias, as configured), and scores against ground truth. A
regression in transcription or vocab biasing fails the suite.
"""

import pytest

from selfscribe.audio import clip_from_wav_bytes
from selfscribe.config import load_config
from selfscribe.harness import ClipCase, normalize, score
from selfscribe.stt import get_transcriber

CORPUS = [
    ClipCase(
        id="basic",
        script="Testing one two three, the quick brown fox jumps over the lazy dog",
        expect=[
            ("one two three", "1 2 3", "123", "1-2-3"),
            "quick brown fox jumps over the lazy dog",
        ],
    ),
    ClipCase(
        id="claude_prompt",
        script="Please refactor the config loader and run the tests again",
        expect=["refactor the config loader", "run the tests again"],
    ),
    ClipCase(
        id="email_prose",
        script="Send an email to the team about the deadline on Friday",
        expect=["send an email to the team", "deadline", "friday"],
    ),
    ClipCase(
        id="numbers",
        script="The build takes forty five seconds and uses three hundred megabytes",
        expect=[("forty five", "45"), ("three hundred", "300"), "megabytes"],
    ),
    ClipCase(
        id="question",
        script="What time is the meeting tomorrow",
        expect=["what time is the meeting tomorrow"],
    ),
]


def test_normalize():
    assert normalize("Testing 1-2-3, The Quick Brown Fox!") == "testing 1 2 3 the quick brown fox"


def test_score_any_of_and_exact():
    case = ClipCase(id="x", script="", expect=[("one two", "12")], exact=["HitList"])
    assert score(case, "count 12 with HitList").passed
    result = score(case, "count twelve with hitlist")
    assert not result.passed
    assert result.missing == ["one two", "exact:HitList"]


@pytest.fixture(scope="session")
def pipeline():
    cfg = load_config()
    if not cfg.groq_api_key:
        pytest.skip("no groq key")
    return get_transcriber(cfg)


@pytest.mark.live
@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c.id)
def test_corpus_clip(case, pipeline, tts_wav):
    clip = clip_from_wav_bytes(tts_wav(case.script, f"corpus_{case.id}").read_bytes())
    result = score(case, pipeline(clip).text)
    print(f"\n{result}")
    assert result.passed, str(result)
