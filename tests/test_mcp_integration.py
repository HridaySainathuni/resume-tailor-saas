"""Integration tests for the MCP server.

The tests exercise the tools through the server's call_tool, the
same path an agent host uses. Network access is mocked: urlopen
returns canned HTML for job postings and canned JSON for Wikipedia
summaries, so no real HTTP request is made. The tools that read
from the database run against a test app whose in-memory database
is shared across threads, because the MCP server runs sync tools
in a worker thread.
"""
import asyncio
import json
import urllib.request
from datetime import datetime, timezone

import pytest
from sqlalchemy.pool import StaticPool

import mcp_server.tools as tools_module
from app import create_app, db
from app.config import TestingConfig
from app.models import TailorResult, User
from mcp_server.server import create_server

FAKE_HTML = """<html>
<head><title>Software Engineer - Acme Corp</title></head>
<body>
<h1>Software Engineer</h1>
<p>We are hiring a Python engineer to build internal tools.</p>
</body>
</html>"""

FAKE_WIKIPEDIA_JSON = """{
  "title": "Acme Corporation",
  "extract": "Acme Corporation is a fictional company that makes everything.",
  "content_urls": {
    "desktop": {"page": "https://en.wikipedia.org/wiki/Acme_Corporation"}
  }
}"""


class FakeResponse:
    """Minimal stand-in for the object urlopen returns."""

    def __init__(self, payload: str):
        self._payload = payload.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._payload


@pytest.fixture()
def fake_urlopen(monkeypatch):
    """Make urlopen return canned HTML or Wikipedia JSON by URL."""

    def _fake_urlopen(request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if "wikipedia.org" in url:
            return FakeResponse(FAKE_WIKIPEDIA_JSON)
        return FakeResponse(FAKE_HTML)

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)


@pytest.fixture()
def test_app(monkeypatch):
    """A test app whose in-memory database is shared across threads.

    The MCP server runs sync tools in a worker thread, so the
    database connection must be the same in every thread. A static
    pool with check_same_thread off gives one shared connection.
    The tools build their app with create_app when no app context
    is active, so point that call at this test app instead of a
    fresh default-config app.
    """
    app = create_app(
        TestingConfig,
        config_overrides={
            "SQLALCHEMY_ENGINE_OPTIONS": {
                "poolclass": StaticPool,
                "connect_args": {"check_same_thread": False},
            }
        },
    )
    monkeypatch.setattr(tools_module, "create_app", lambda *args, **kwargs: app)
    with app.app_context():
        user = User(email="integration@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        db.session.expunge(user)
        yield app, user_id
        db.session.remove()
        db.drop_all()


def _seed_result(user_id, resume_text, job_title=None, company=None, created_at=None):
    db.session.add(
        TailorResult(
            user_id=user_id,
            original_resume=resume_text,
            job_description="Example job description.",
            tailored_resume="Tailored resume text.",
            job_title=job_title,
            company=company,
            created_at=created_at,
        )
    )
    db.session.commit()


def _payload(result):
    """Pull the tool's return value out of a CallToolResult."""
    assert not result.is_error
    text = result.content[0].text
    try:
        return json.loads(text)
    except ValueError:
        return text


def test_server_lists_all_four_tools():
    server = create_server()
    tools = asyncio.run(server.list_tools())

    assert [tool.name for tool in tools] == [
        "fetch_job_posting",
        "research_company",
        "read_resume",
        "get_past_applications",
    ]


def test_call_fetch_job_posting_through_server(fake_urlopen):
    server = create_server()
    result = asyncio.run(
        server.call_tool(
            "fetch_job_posting", {"url": "https://example.com/jobs/1"}
        )
    )

    payload = _payload(result)
    assert payload["title"] == "Software Engineer - Acme Corp"
    assert "Python engineer" in payload["text"]


def test_call_research_company_through_server(fake_urlopen):
    server = create_server()
    result = asyncio.run(
        server.call_tool("research_company", {"name": "Acme Corporation"})
    )

    payload = _payload(result)
    assert payload["name"] == "Acme Corporation"
    assert "fictional company" in payload["summary"]
    assert payload["url"] == "https://en.wikipedia.org/wiki/Acme_Corporation"


def test_call_read_resume_through_server(test_app):
    app, user_id = test_app
    with app.app_context():
        _seed_result(user_id, "Old resume text.")
        _seed_result(user_id, "Latest resume text.")

    server = create_server()
    result = asyncio.run(server.call_tool("read_resume", {"user_id": user_id}))

    assert _payload(result) == "Latest resume text."


def test_call_read_resume_unknown_user_through_server(test_app):
    server = create_server()
    result = asyncio.run(server.call_tool("read_resume", {"user_id": 999999}))

    assert _payload(result) == {"error": "No resume found"}


def test_call_get_past_applications_through_server(test_app):
    app, user_id = test_app
    with app.app_context():
        _seed_result(
            user_id,
            "Resume text.",
            job_title="Junior Engineer",
            company="Old Corp",
            created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        )
        _seed_result(
            user_id,
            "Resume text.",
            job_title="Software Engineer",
            company="Acme Corp",
            created_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        )
        _seed_result(
            user_id,
            "Resume text.",
            job_title="Senior Engineer",
            company="New Corp",
            created_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
        )

    server = create_server()
    result = asyncio.run(
        server.call_tool("get_past_applications", {"user_id": user_id})
    )

    payload = _payload(result)
    assert [entry["job_title"] for entry in payload["applications"]] == [
        "Senior Engineer",
        "Software Engineer",
        "Junior Engineer",
    ]
    assert payload["applications"][0]["company"] == "New Corp"


def test_call_get_past_applications_empty_through_server(test_app):
    _, user_id = test_app

    server = create_server()
    result = asyncio.run(
        server.call_tool("get_past_applications", {"user_id": user_id})
    )

    assert _payload(result) == {"applications": []}
