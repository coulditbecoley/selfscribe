import json

from selfscribe.telemetry import ALLOWED_KEYS, record_utterance


def test_telemetry_records_latency_but_never_content(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    record_utterance("groq", 684.2, chars=34, target="send", path=path)
    record_utterance("local", 1200.0, chars=10, target="dictate", path=path)
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(lines) == 2
    assert lines[0]["backend"] == "groq"
    assert lines[0]["ms"] == 684.2
    assert lines[0]["chars"] == 34
    for entry in lines:
        assert set(entry) <= ALLOWED_KEYS  # no text, no audio, ever


def test_telemetry_failure_is_silent(tmp_path):
    bad = tmp_path / "not-a-dir"
    bad.write_text("file, not dir")
    record_utterance("groq", 1.0, 1, "send", path=bad / "x.jsonl")  # must not raise
