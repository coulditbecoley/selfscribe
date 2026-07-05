import pytest

from selfscribe.commands import apply_commands


def test_no_commands_passes_through():
    assert apply_commands("just some normal dictated text") == "just some normal dictated text"


def test_new_line_and_new_paragraph():
    assert apply_commands("first line new line second line") == "first line\nsecond line"
    assert apply_commands("para one new paragraph para two") == "para one\n\npara two"


def test_commands_are_case_insensitive():
    assert apply_commands("hello NEW LINE world") == "hello\nworld"
    assert apply_commands("hello New Paragraph world") == "hello\n\nworld"


def test_leading_and_trailing_command():
    assert apply_commands("new line starts here") == "starts here"
    assert apply_commands("ends here new line") == "ends here"


def test_scratch_that_deletes_back_to_previous_boundary():
    assert apply_commands("send the report scratch that send the invoice") == "send the invoice"
    # scratch that at the very start is a no-op on an empty buffer
    assert apply_commands("scratch that hello") == "hello"
    # only the current segment is scratched, not text before a newline
    assert apply_commands("keep this new line drop this scratch that final") == "keep this\nfinal"


def test_code_block_wraps_fenced():
    assert apply_commands("code block print hello end code block") == "```\nprint hello\n```"


def test_code_block_unclosed_is_closed_at_end():
    assert apply_commands("here code block some code") == "here\n```\nsome code\n```"


def test_command_words_inside_larger_words_are_not_matched():
    # 'newline' as a single token is not the 'new line' command
    assert apply_commands("the newline character") == "the newline character"


def test_whitespace_is_normalized_around_commands():
    assert apply_commands("a   new line   b") == "a\nb"


def test_multiple_commands_in_sequence():
    out = apply_commands("title new paragraph body new line more")
    assert out == "title\n\nbody\nmore"


@pytest.mark.live
def test_live_new_line_command_through_real_pipeline(tts_wav):
    """Real Groq STT hears 'new line' as two tokens the command processor
    splits — end-to-end, not mocked."""
    from selfscribe.app import sanitize_for_injection
    from selfscribe.audio import clip_from_wav_bytes
    from selfscribe.config import load_config
    from selfscribe.stt import get_transcriber

    cfg = load_config()
    if not cfg.groq_api_key:
        pytest.skip("no groq key")
    clip = clip_from_wav_bytes(
        tts_wav("first line new line second line", "cmd_newline").read_bytes()
    )
    raw = get_transcriber(cfg)(clip).text
    result = apply_commands(sanitize_for_injection(raw))
    print(f"\nraw: {raw!r}\ncommanded: {result!r}")
    # the spoken "new line" became a real break splitting the two segments
    # (Whisper's own capitalization/trailing punctuation is not our concern)
    lines = result.split("\n")
    assert len(lines) == 2
    assert lines[0].lower().startswith("first line")
    assert lines[1].lower().startswith("second line")
    assert "new line" not in result.lower()
