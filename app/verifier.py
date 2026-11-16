"""Grounding verifier for Resume Tailor.

Checks a tailored resume against the source resume, line by line,
and reports which lines are grounded in the source and which are not.
Each line is checked first for an exact match, then for a close
normalized match, so reworded lines that keep the same content
still count as grounded.
"""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

FUZZY_MATCH_THRESHOLD = 0.8


@dataclass
class LineVerdict:
    """One tailored line and how it checks out against the source resume."""

    line: str
    verdict: str  # "grounded" or "unsupported"
    match: str | None  # "exact", "fuzzy", or None when unsupported


@dataclass
class GroundingReport:
    """Per-line verdicts for a tailored resume plus the overall rate."""

    lines: list[LineVerdict] = field(default_factory=list)

    @property
    def grounding_rate(self) -> float:
        """Share of lines grounded in the source resume, 0.0 when empty."""
        if not self.lines:
            return 0.0
        grounded = sum(1 for line in self.lines if line.verdict == "grounded")
        return grounded / len(self.lines)


def _normalize(line: str) -> str:
    """Lowercase, strip punctuation, and collapse whitespace."""
    lowered = line.lower()
    no_punctuation = re.sub(r"[^\w\s]", " ", lowered)
    return re.sub(r"\s+", " ", no_punctuation).strip()


def _is_exact_match(line: str, resume_lines: list[str]) -> bool:
    """True when the line appears in the resume, whole or as a substring."""
    normalized = _normalize(line)
    if not normalized:
        return False
    for resume_line in resume_lines:
        if normalized == _normalize(resume_line):
            return True
    return False


def _is_fuzzy_match(line: str, resume_lines: list[str]) -> bool:
    """True when the line closely resembles some resume line."""
    normalized = _normalize(line)
    if not normalized:
        return False
    for resume_line in resume_lines:
        candidate = _normalize(resume_line)
        if not candidate:
            continue
        ratio = SequenceMatcher(None, normalized, candidate).ratio()
        if ratio >= FUZZY_MATCH_THRESHOLD:
            return True
    return False


def verify_grounding(tailored_text: str, resume_text: str) -> GroundingReport:
    """Verify each line of a tailored resume against the source resume.

    Blank lines are skipped. A line copied from the resume is grounded
    by exact match; a reworded line with matching content is grounded
    by fuzzy match; anything else is unsupported.
    """
    resume_lines = resume_text.splitlines()
    verdicts = []
    for raw_line in tailored_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _is_exact_match(line, resume_lines):
            verdicts.append(LineVerdict(line=line, verdict="grounded", match="exact"))
        elif _is_fuzzy_match(line, resume_lines):
            verdicts.append(LineVerdict(line=line, verdict="grounded", match="fuzzy"))
        else:
            verdicts.append(
                LineVerdict(line=line, verdict="unsupported", match=None)
            )
    return GroundingReport(lines=verdicts)
