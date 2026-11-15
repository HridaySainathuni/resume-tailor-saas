"""Tests for the agent loop.

The Anthropic client is faked: canned responses stand in for the
model, so no API key or network access is needed. The four tool
functions are replaced with fakes on the app.agent module.
"""
import pytest

import app.agent
from app.agent import MAX_TOOL_TURNS, gather_context, parse_deliverables, run_agent
from app.models import TailorResult


class FakeTextBlock:
    """Stand-in for an Anthropic text content block."""

    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class FakeToolUseBlock:
    """Stand-in for an Anthropic tool_use content block."""

    def __init__(self, block_id: str, name: str, arguments: dict):
        self.type = "tool_use"
        self.id = block_id
        self.name = name
        self.input = arguments


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


def _deliverables_reply(resume="Jane Doe, Python engineer. Tailored for Acme Corp.",
                        letter="Dear Acme team, I would love to join."):
    return f"=== TAILORED RESUME ===\n{resume}\n=== COVER LETTER ===\n{letter}"


@pytest.fixture()
def fake_tools(monkeypatch):
    """Replace the four tool functions with fakes that record calls."""
    calls = {}

    def _fetch_job_posting(url):
        calls["fetch_job_posting"] = url
        return {"text": "Python engineer wanted.", "title": "Engineer", "company": "Acme Corp"}

    def _research_company(name):
        calls["research_company"] = name
        return {"name": "Acme Corp", "summary": "Makes widgets.", "url": "https://example.com/acme"}

    def _read_resume(user_id):
        calls["read_resume"] = user_id
        return "Jane Doe, Python engineer."

    def _get_past_applications(user_id):
        calls["get_past_applications"] = user_id
        return {"applications": []}

    monkeypatch.setattr(app.agent, "fetch_job_posting", _fetch_job_posting)
    monkeypatch.setattr(app.agent, "research_company", _research_company)
    monkeypatch.setattr(app.agent, "read_resume", _read_resume)
    monkeypatch.setattr(app.agent, "get_past_applications", _get_past_applications)
    return calls


def test_gather_context_calls_all_four_tools(fake_tools):
    context = gather_context("https://example.com/jobs/1", 7)

    assert fake_tools["fetch_job_posting"] == "https://example.com/jobs/1"
    assert fake_tools["research_company"] == "Acme Corp"
    assert fake_tools["read_resume"] == 7
    assert fake_tools["get_past_applications"] == 7
    assert context["job_posting"]["title"] == "Engineer"
    assert context["resume"] == "Jane Doe, Python engineer."


def test_run_agent_calls_tool_and_returns_deliverables(app, user, fake_tools):
    client = FakeClient(
        [
            FakeResponse(
                [
                    FakeToolUseBlock(
                        "toolu_1", "research_company", {"name": "Acme Corp"}
                    )
                ]
            ),
            FakeResponse([FakeTextBlock(_deliverables_reply())]),
        ]
    )

    result = run_agent("https://example.com/jobs/1", user.id, client=client)

    assert result["tailored_resume"] == "Jane Doe, Python engineer. Tailored for Acme Corp."
    assert result["cover_letter"] == "Dear Acme team, I would love to join."
    assert result["job_title"] == "Engineer"
    assert result["company"] == "Acme Corp"
    assert fake_tools["research_company"] == "Acme Corp"
    second_call = client.messages.calls[1]
    tool_result = second_call["messages"][2]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "toolu_1"
    assert "Acme Corp" in tool_result["content"]
    assert second_call["tools"][0]["name"] == "fetch_job_posting"


def test_run_agent_full_run_saves_tailor_result(app, user, fake_tools):
    client = FakeClient([FakeResponse([FakeTextBlock(_deliverables_reply())])])

    result = run_agent("https://example.com/jobs/1", user.id, client=client)

    assert result["ats_score"]["score"] >= 0
    assert result["ats_score"]["grade"] in {"Excellent", "Good", "Fair", "Needs Work"}
    saved = TailorResult.query.filter_by(user_id=user.id).first()
    assert saved is not None
    assert saved.id == result["result_id"]
    assert saved.tailored_resume == result["tailored_resume"]
    assert saved.cover_letter == result["cover_letter"]
    assert saved.original_resume == "Jane Doe, Python engineer."
    assert saved.job_description == "Python engineer wanted."
    assert saved.job_title == "Engineer"
    assert saved.company == "Acme Corp"


def test_run_agent_job_fetch_failure_saves_nothing(app, user, fake_tools, monkeypatch):
    monkeypatch.setattr(
        "app.agent.fetch_job_posting", lambda url: {"error": "Could not fetch URL."}
    )
    client = FakeClient([FakeResponse([FakeTextBlock(_deliverables_reply())])])

    with pytest.raises(ValueError, match="Could not fetch job posting"):
        run_agent("https://example.com/jobs/1", user.id, client=client)

    assert TailorResult.query.count() == 0
    assert len(client.messages.calls) == 0


def test_run_agent_missing_resume_saves_nothing(app, user, fake_tools, monkeypatch):
    monkeypatch.setattr(
        "app.agent.read_resume", lambda user_id: {"error": "No resume found"}
    )
    client = FakeClient([FakeResponse([FakeTextBlock(_deliverables_reply())])])

    with pytest.raises(ValueError, match="Could not read resume"):
        run_agent("https://example.com/jobs/1", user.id, client=client)

    assert TailorResult.query.count() == 0
    assert len(client.messages.calls) == 0


def test_run_agent_raises_when_reply_has_no_deliverables(app, user, fake_tools):
    client = FakeClient([FakeResponse([FakeTextBlock("Direct answer.")])])

    with pytest.raises(ValueError, match="tailored resume and a cover letter"):
        run_agent("https://example.com/jobs/1", user.id, client=client)

    assert TailorResult.query.count() == 0


def test_run_agent_raises_when_tool_turns_run_out(fake_tools):
    responses = [
        FakeResponse([FakeToolUseBlock(f"toolu_{i}", "research_company", {"name": "Acme"})])
        for i in range(MAX_TOOL_TURNS + 1)
    ]
    client = FakeClient(responses)

    with pytest.raises(RuntimeError, match="did not finish"):
        run_agent("https://example.com/jobs/1", 7, client=client)
    assert len(client.messages.calls) == MAX_TOOL_TURNS


def test_parse_deliverables_splits_resume_and_letter():
    resume, letter = parse_deliverables(_deliverables_reply("My resume.", "My letter."))

    assert resume == "My resume."
    assert letter == "My letter."


def test_parse_deliverables_raises_without_markers():
    with pytest.raises(ValueError, match="tailored resume and a cover letter"):
        parse_deliverables("Just some text.")


def test_parse_deliverables_raises_when_section_is_empty():
    with pytest.raises(ValueError, match="tailored resume and a cover letter"):
        parse_deliverables("=== TAILORED RESUME ===\n=== COVER LETTER ===\nMy letter.")
