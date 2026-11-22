"""Tests for OpenTelemetry tracing of the agent loop.

Spans are captured with an in-memory exporter configured once for
this module; each test clears it before and after it runs. The
Anthropic client is faked the same way as in test_agent, so no API
key or network access is needed.
"""
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import app.agent
import app.agent as agent_module
from app.agent import run_agent
from app.tracing import configure_tracing
from tests.test_agent import (
    FakeClient,
    FakeResponse,
    FakeTextBlock,
    FakeToolUseBlock,
    _deliverables_reply,
)

_exporter = InMemorySpanExporter()
configure_tracing(exporter=_exporter)


@pytest.fixture()
def spans():
    _exporter.clear()
    yield _exporter
    _exporter.clear()


@pytest.fixture()
def fake_tools(monkeypatch):
    """Replace the four tool functions with fakes that return canned data."""

    def _fetch_job_posting(url):
        return {"text": "Python engineer wanted.", "title": "Engineer", "company": "Acme Corp"}

    def _research_company(name):
        return {"name": "Acme Corp", "summary": "Makes widgets.", "url": "https://example.com/acme"}

    def _read_resume(user_id):
        return "Jane Doe, Python engineer."

    def _get_past_applications(user_id):
        return {"applications": []}

    monkeypatch.setattr(app.agent, "fetch_job_posting", _fetch_job_posting)
    monkeypatch.setattr(app.agent, "research_company", _research_company)
    monkeypatch.setattr(app.agent, "read_resume", _read_resume)
    monkeypatch.setattr(app.agent, "get_past_applications", _get_past_applications)


def _by_name(exporter, name):
    return [span for span in exporter.get_finished_spans() if span.name == name]


def test_run_agent_emits_parent_and_child_spans(app, user, fake_tools, spans):
    client = FakeClient(
        [
            FakeResponse(
                [FakeToolUseBlock("toolu_1", "research_company", {"name": "Acme Corp"})]
            ),
            FakeResponse([FakeTextBlock(_deliverables_reply())]),
        ]
    )

    run_agent("https://example.com/jobs/1", user.id, client=client)

    parents = _by_name(spans, "agent.run")
    assert len(parents) == 1
    children = _by_name(spans, "tool.research_company")
    assert len(children) == 1
    child = children[0]
    assert child.parent is not None
    assert child.parent.span_id == parents[0].context.span_id
    assert child.attributes["tool.name"] == "research_company"
    assert child.attributes["tool.success"] is True


def test_failed_tool_call_still_emits_span(app, user, fake_tools, spans, monkeypatch):
    calls = {"research_company": 0}

    def _research_company_fails_second_time(name):
        calls["research_company"] += 1
        if calls["research_company"] == 1:
            return {"name": "Acme Corp", "summary": "Makes widgets.", "url": "https://example.com/acme"}
        raise RuntimeError("Wikipedia is down")

    monkeypatch.setattr(agent_module, "research_company", _research_company_fails_second_time)
    client = FakeClient(
        [
            FakeResponse(
                [FakeToolUseBlock("toolu_1", "research_company", {"name": "Acme Corp"})]
            ),
            FakeResponse([FakeTextBlock(_deliverables_reply())]),
        ]
    )

    with pytest.raises(RuntimeError, match="Wikipedia is down"):
        run_agent("https://example.com/jobs/1", user.id, client=client)

    children = _by_name(spans, "tool.research_company")
    assert len(children) == 1
    child = children[0]
    assert child.attributes["tool.name"] == "research_company"
    assert child.attributes["tool.success"] is False
    assert any(event.name == "exception" for event in child.events)
    assert len(_by_name(spans, "agent.run")) == 1
