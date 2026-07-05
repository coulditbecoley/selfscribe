"""Accuracy harness: score pipeline output against scripted ground truth.

Used by the regression suite (tests/test_harness.py) on TTS-synthesized
clips, and by SS-16 on real-voice recordings. Loose requirements match on
normalized text (case/punctuation-insensitive, with any-of alternatives for
things Whisper legitimately renders differently, e.g. "one two three" vs
"123"). Exact requirements are case- and spacing-sensitive — that's where
custom-vocabulary correctness is measured.
"""

import re
from dataclasses import dataclass, field

Requirement = str | tuple[str, ...]


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


@dataclass
class ClipCase:
    id: str
    script: str  # what the synthetic/real voice says
    expect: list[Requirement] = field(default_factory=list)  # loose
    exact: list[str] = field(default_factory=list)  # vocab-term form-sensitive


@dataclass
class ClipResult:
    case_id: str
    text: str
    missing: list[str]

    @property
    def passed(self) -> bool:
        return not self.missing

    def __str__(self) -> str:
        status = "PASS" if self.passed else f"MISS {self.missing}"
        return f"{self.case_id}: {status} -> {self.text!r}"


def score(case: ClipCase, text: str) -> ClipResult:
    norm = normalize(text)
    missing: list[str] = []
    for req in case.expect:
        alternatives = (req,) if isinstance(req, str) else req
        if not any(normalize(alt) in norm for alt in alternatives):
            missing.append(alternatives[0])
    for term in case.exact:
        if term not in text:
            missing.append(f"exact:{term}")
    return ClipResult(case_id=case.id, text=text, missing=missing)
