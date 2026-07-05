"""Structural dictation commands for the general dictate path.

Spoken phrases become document structure the cleanup LLM can't infer from
audio: line breaks, paragraph breaks, an undo, and fenced code blocks.
Deliberately structural-only — no "period"/"comma" word commands, which
collide constantly with ordinary speech.

Applied AFTER sanitize_for_injection and only on the dictate target, so the
only newlines that can reach the clipboard come from recognized command
phrases — never from raw transcript bytes. The Claude Code send path never
runs this (it stays raw and single-line).
"""

# Longest phrases first so "end code block" wins over "code block".
_COMMANDS: list[tuple[tuple[str, ...], str]] = [
    (("end", "code", "block"), "END_CODE"),
    (("new", "paragraph"), "PARAGRAPH"),
    (("new", "line"), "NEWLINE"),
    (("scratch", "that"), "SCRATCH"),
    (("code", "block"), "CODE"),
]
FENCE = "```"


def _tokenize(text: str) -> list[tuple[str, str]]:
    """(name, literal) events; commands greedily longest-matched. `literal`
    keeps the original words so an out-of-context command can render verbatim."""
    words = text.split()
    lower = [w.lower() for w in words]
    events: list[tuple[str, str]] = []
    i, n = 0, len(words)
    while i < n:
        for phrase, name in _COMMANDS:
            end = i + len(phrase)
            if tuple(lower[i:end]) == phrase:
                events.append((name, " ".join(words[i:end])))
                i = end
                break
        else:
            events.append(("WORD", words[i]))
            i += 1
    return events


def apply_commands(text: str, enabled: bool = True) -> str:
    if not enabled:
        return text

    out: list[str] = []
    current: list[str] = []
    pending = ""  # separator carried to the next normal line ("nl" | "para")
    in_code = False
    code_lines: list[str] = []
    code_current: list[str] = []

    def append_line(line: str) -> None:
        nonlocal pending
        if out and pending == "para":
            out.append("")  # blank line -> paragraph gap
        out.append(line)
        pending = ""

    def flush() -> None:
        if current:
            append_line(" ".join(current))
            current.clear()

    def flush_code_line() -> None:
        code_lines.append(" ".join(code_current))
        code_current.clear()

    def close_code() -> None:
        nonlocal in_code
        if code_current:
            flush_code_line()
        out.extend(code_lines)  # verbatim; no paragraph logic inside a block
        out.append(FENCE)
        code_lines.clear()
        in_code = False

    for name, literal in _tokenize(text):
        if in_code:
            if name == "END_CODE":
                close_code()
            elif name == "NEWLINE":
                flush_code_line()
            elif name == "PARAGRAPH":
                flush_code_line()
                code_lines.append("")
            elif name == "SCRATCH":
                code_current.clear()
            else:  # WORD or a nested CODE — keep the words as literal code
                code_current.extend(literal.split())
            continue
        if name == "WORD":
            current.append(literal)
        elif name == "NEWLINE":
            flush()
            pending = "nl"
        elif name == "PARAGRAPH":
            flush()
            pending = "para"
        elif name == "SCRATCH":
            current.clear()  # drop the current line back to its last break
        elif name == "CODE":
            flush()
            append_line(FENCE)
            in_code = True
        elif name == "END_CODE":
            current.extend(literal.split())  # no open block -> literal words

    if in_code:
        close_code()
    else:
        flush()
    return "\n".join(out)
