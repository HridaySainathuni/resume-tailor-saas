"""Tests for the eval harness.

The Anthropic client is faked: canned responses stand in for the
model, so no API key or network access is needed. The agent loop's
tool functions are replaced with fakes that serve the fixture data,
and saving results is stubbed out. The fixture pairs are synthetic
and exist only to exercise the harness.
"""
import pytest

import app.agent
from app.evals import (
    AGENT,
    AGENT_WITH_VERIFIER,
    BASELINE,
    EvalPair,
    fabrication_rate,
    run_eval,
)

# Synthetic fixture pair 1: clean tailoring. Both approaches reuse
# lines from the source resume, so nothing is fabricated.
PAIR_CLEAN = EvalPair(
    resume=(
        "Jane Doe, Python engineer.\n"
        "Built a Flask API serving 10,000 requests a day.\n"
        "Led a team of four engineers."
    ),
    job_description="Python engineer wanted. Flask API experience required. Team leadership a plus.",
    job_title="Python Engineer",
    company="Acme Corp",
    job_url="https://example.com/jobs/clean",
    user_id=1,
)

CLEAN_BASELINE = (
    "Jane Doe, Python engineer.\n"
    "Built a Flask API serving 10,000 requests a day.\n"
    "Led a team of four engineers."
)
CLEAN_AGENT = CLEAN_BASELINE

# Synthetic fixture pair 2: the agent fabricates. The baseline reuses
# resume lines, while the agent adds a line the resume never supports.
PAIR_FABRICATING = EvalPair(
    resume=(
        "John Smith, data analyst.\n"
        "Built dashboards in Tableau for the sales team.\n"
        "Automated weekly reports with Python."
    ),
    job_description=(
        "Data analyst wanted. Tableau dashboards and Python automation "
        "required. Machine learning experience a plus."
    ),
    job_title="Data Analyst",
    company="Beta Inc",
    job_url="https://example.com/jobs/fabricating",
    user_id=2,
)

FABRICATING_BASELINE = (
    "John Smith, data analyst.\nBuilt dashboards in Tableau for the sales team."
)
FABRICATING_AGENT = (
    "John Smith, data analyst.\n"
    "Built dashboards in Tableau for the sales team.\n"
    "Deployed a machine learning model to production"
)


class FakeTextBlock:
    """Stand-in for an Anthropic text content block."""

    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class FakeResponse:
    """Stand-in for an Anthropic message response."""

    def __init__(self, content):
        self.content = content


class FakeMessages:
    """Records create calls and returns canned responses in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    """Stand-in for an Anthropic client."""

    def __init__(self, responses):
        self.messages = FakeMessages(responses)


def _deliverables_reply(resume: str) -> str:
    return (
        "=== TAILORED RESUME ===\n"
        f"{resume}\n"
        "=== COVER LETTER ===\n"
        "Dear hiring team, I would love to join."
    )


@pytest.fixture()
def fake_tools(monkeypatch):
    """Serve the fixture pairs through the agent loop's tool functions."""
    pairs_by_url = {
        PAIR_CLEAN.job_url: PAIR_CLEAN,
        PAIR_FABRICATING.job_url: PAIR_FABRICATING,
    }
    pairs_by_user = {
        PAIR_CLEAN.user_id: PAIR_CLEAN,
        PAIR_FABRICATING.user_id: PAIR_FABRICATING,
    }

    def _fetch_job_posting(url):
        pair = pairs_by_url[url]
        return {
            "text": pair.job_description,
            "title": pair.job_title,
            "company": pair.company,
        }

    def _research_company(name):
        return {"name": name, "summary": "Makes widgets.", "url": "https://example.com"}

    def _read_resume(user_id):
        return pairs_by_user[user_id].resume

    def _get_past_applications(user_id):
        return {"applications": []}

    monkeypatch.setattr(app.agent, "fetch_job_posting", _fetch_job_posting)
    monkeypatch.setattr(app.agent, "research_company", _research_company)
    monkeypatch.setattr(app.agent, "read_resume", _read_resume)
    monkeypatch.setattr(app.agent, "get_past_applications", _get_past_applications)
    monkeypatch.setattr(app.agent, "_save_tailor_result", lambda *args, **kwargs: 1)


@pytest.fixture()
def fake_client():
    """Canned model replies in the order run_eval calls for them.

    Per pair: baseline, then agent, then agent with verifier.
    """
    return FakeClient(
        [
            FakeResponse([FakeTextBlock(CLEAN_BASELINE)]),
            FakeResponse([FakeTextBlock(_deliverables_reply(CLEAN_AGENT))]),
            FakeResponse([FakeTextBlock(_deliverables_reply(CLEAN_AGENT))]),
            FakeResponse([FakeTextBlock(FABRICATING_BASELINE)]),
            FakeResponse([FakeTextBlock(_deliverables_reply(FABRICATING_AGENT))]),
            FakeResponse([FakeTextBlock(_deliverables_reply(FABRICATING_AGENT))]),
        ]
    )


def test_run_eval_runs_all_three_approaches(fake_tools, fake_client):
    results = run_eval([PAIR_CLEAN, PAIR_FABRICATING], client=fake_client)

    assert len(results) == 2
    for result in results:
        assert set(result.results) == {BASELINE, AGENT, AGENT_WITH_VERIFIER}


def test_run_eval_clean_pair_has_no_fabrication(fake_tools, fake_client):
    results = run_eval([PAIR_CLEAN, PAIR_FABRICATING], client=fake_client)

    clean = results[0].results
    assert clean[BASELINE].fabrication_rate == 0.0
    assert clean[AGENT].fabrication_rate == 0.0
    assert clean[AGENT_WITH_VERIFIER].fabrication_rate == 0.0


def test_run_eval_fabricating_agent_scores_higher_than_baseline(fake_tools, fake_client):
    results = run_eval([PAIR_CLEAN, PAIR_FABRICATING], client=fake_client)

    fabricating = results[1].results
    assert fabricating[BASELINE].fabrication_rate == 0.0
    assert fabricating[AGENT].fabrication_rate == pytest.approx(1 / 3)
    assert fabricating[AGENT].fabrication_rate > fabricating[BASELINE].fabrication_rate
    assert fabricating[AGENT_WITH_VERIFIER].fabrication_rate == 0.0
    assert "machine learning model" not in fabricating[AGENT_WITH_VERIFIER].tailored_resume


def test_run_eval_reports_keyword_coverage(fake_tools, fake_client):
    results = run_eval([PAIR_CLEAN, PAIR_FABRICATING], client=fake_client)

    for result in results:
        for approach_result in result.results.values():
            assert 0.0 <= approach_result.keyword_coverage <= 1.0

    fabricating = results[1].results
    assert fabricating[AGENT].keyword_coverage > fabricating[BASELINE].keyword_coverage


def test_fabrication_rate_empty_tailored_resume_is_zero():
    assert fabrication_rate("", PAIR_CLEAN.resume) == 0.0
