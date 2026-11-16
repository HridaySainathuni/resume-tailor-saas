"""Tests for the grounding verifier."""
from app.verifier import GroundingReport, verify_grounding

RESUME_TEXT = """Hriday Sainathuni
Machine Learning Engineer Intern, Workday
Built a LangGraph planning agent with cross-session memory
Python, PyTorch, Postgres, Docker, Kubernetes
B.S. Computer Science, University of Virginia, May 2027
"""


def test_line_copied_from_resume_is_grounded():
    report = verify_grounding(
        "Built a LangGraph planning agent with cross-session memory",
        RESUME_TEXT,
    )
    assert len(report.lines) == 1
    assert report.lines[0].verdict == "grounded"
    assert report.lines[0].match == "exact"


def test_fabricated_line_is_unsupported():
    report = verify_grounding(
        "Led a team of 40 engineers at Google for five years",
        RESUME_TEXT,
    )
    assert len(report.lines) == 1
    assert report.lines[0].verdict == "unsupported"
    assert report.lines[0].match is None


def test_empty_tailored_text_returns_no_lines():
    report = verify_grounding("", RESUME_TEXT)
    assert report.lines == []
    assert report.grounding_rate == 0.0


def test_reworded_line_is_grounded_by_fuzzy_match():
    report = verify_grounding(
        "Built a LangGraph planning agent using cross-session memory",
        RESUME_TEXT,
    )
    assert len(report.lines) == 1
    assert report.lines[0].verdict == "grounded"
    assert report.lines[0].match == "fuzzy"


def test_grounding_rate_counts_grounded_lines():
    report = verify_grounding(
        "Built a LangGraph planning agent with cross-session memory\n"
        "Won a Nobel Prize in Physics",
        RESUME_TEXT,
    )
    assert isinstance(report, GroundingReport)
    assert report.grounding_rate == 0.5
