"""Tests for the MCP tools.

Network access is mocked: urllib.request.urlopen returns a fake
response holding canned HTML, so no real HTTP request is made.
"""
import asyncio
import urllib.error
import urllib.request
from datetime import datetime, timezone

import pytest

from app import db
from app.models import TailorResult
from mcp_server.server import create_server
from mcp_server.tools import (
    fetch_job_posting,
    get_past_applications,
    read_resume,
    research_company,
)

FAKE_HTML = """<html>
<head><title>Software Engineer - Acme Corp</title></head>
<body>
<h1>Software Engineer</h1>
<p>We are hiring a Python engineer to build internal tools.</p>
</body>
</html>"""


class FakeResponse:
    """Minimal stand-in for the object urlopen returns."""

    def __init__(self, html: str):
        self._html = html.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._html


@pytest.fixture()
def fake_urlopen(monkeypatch):
    """Make urlopen return the canned posting HTML."""

    def _fake_urlopen(request, timeout=None):
        return FakeResponse(FAKE_HTML)

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)


def test_fetch_job_posting_returns_text_title_and_company(fake_urlopen):
    result = fetch_job_posting("https://example.com/jobs/1")

    assert set(result) == {"text", "title", "company"}
    assert result["title"] == "Software Engineer - Acme Corp"
    assert "Python engineer" in result["text"]
    assert "company" in result


def test_fetch_job_posting_invalid_url_returns_error():
    result = fetch_job_posting("not-a-url")

    assert "error" in result
    assert result["error"]


def test_server_exposes_fetch_job_posting():
    server = create_server()
    tools = asyncio.run(server.list_tools())

    assert "fetch_job_posting" in [tool.name for tool in tools]


FAKE_WIKIPEDIA_JSON = """{
  "title": "Acme Corporation",
  "extract": "Acme Corporation is a fictional company that makes everything.",
  "content_urls": {
    "desktop": {"page": "https://en.wikipedia.org/wiki/Acme_Corporation"}
  }
}"""


class FakeJsonResponse:
    """Minimal stand-in for the object urlopen returns for JSON."""

    def __init__(self, payload: str):
        self._payload = payload.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._payload


@pytest.fixture()
def fake_wikipedia(monkeypatch):
    """Make urlopen return the canned Wikipedia summary."""

    def _fake_urlopen(request, timeout=None):
        return FakeJsonResponse(FAKE_WIKIPEDIA_JSON)

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)


def test_research_company_returns_name_summary_and_url(fake_wikipedia):
    result = research_company("Acme Corporation")

    assert set(result) == {"name", "summary", "url"}
    assert result["name"] == "Acme Corporation"
    assert "fictional company" in result["summary"]
    assert result["url"] == "https://en.wikipedia.org/wiki/Acme_Corporation"


def test_research_company_unknown_returns_error(monkeypatch):
    def _fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 404, "Not Found", hdrs=None, fp=None
        )

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    result = research_company("No Such Company XYZ")

    assert "error" in result
    assert result["error"]


def test_research_company_empty_name_returns_error():
    result = research_company("")

    assert "error" in result
    assert result["error"]


def test_server_exposes_research_company():
    server = create_server()
    tools = asyncio.run(server.list_tools())

    assert "research_company" in [tool.name for tool in tools]


def _seed_tailor_result(user_id, resume_text):
    db.session.add(
        TailorResult(
            user_id=user_id,
            original_resume=resume_text,
            job_description="Example job description.",
            tailored_resume="Tailored resume text.",
        )
    )
    db.session.commit()


def test_read_resume_returns_most_recent_text(app, user):
    with app.app_context():
        _seed_tailor_result(user.id, "Old resume text.")
        _seed_tailor_result(user.id, "Latest resume text.")

        assert read_resume(user.id) == "Latest resume text."


def test_read_resume_unknown_user_returns_error(app):
    with app.app_context():
        result = read_resume(999999)

    assert result == {"error": "No resume found"}


def test_server_exposes_read_resume():
    server = create_server()
    tools = asyncio.run(server.list_tools())

    assert "read_resume" in [tool.name for tool in tools]


def _seed_application(user_id, job_title, company, created_at):
    db.session.add(
        TailorResult(
            user_id=user_id,
            job_title=job_title,
            company=company,
            original_resume="Resume text.",
            job_description="Example job description.",
            tailored_resume="Tailored resume text.",
            created_at=created_at,
        )
    )
    db.session.commit()


def test_get_past_applications_returns_newest_first(app, user):
    with app.app_context():
        _seed_application(
            user.id, "Junior Engineer", "Old Corp",
            datetime(2026, 10, 1, tzinfo=timezone.utc),
        )
        _seed_application(
            user.id, "Software Engineer", "Acme Corp",
            datetime(2026, 11, 1, tzinfo=timezone.utc),
        )
        _seed_application(
            user.id, "Senior Engineer", "New Corp",
            datetime(2026, 11, 10, tzinfo=timezone.utc),
        )

        result = get_past_applications(user.id)

    assert [entry["job_title"] for entry in result["applications"]] == [
        "Senior Engineer",
        "Software Engineer",
        "Junior Engineer",
    ]
    newest = result["applications"][0]
    assert newest["company"] == "New Corp"
    assert newest["created_at"] == "2026-11-10T00:00:00+00:00"
    assert set(newest) == {"id", "job_title", "company", "created_at"}


def test_get_past_applications_empty_for_new_user(app, user):
    with app.app_context():
        result = get_past_applications(user.id)

    assert result == {"applications": []}


def test_get_past_applications_invalid_user_id_returns_error():
    result = get_past_applications(None)

    assert "error" in result
    assert result["error"]


def test_server_exposes_get_past_applications():
    server = create_server()
    tools = asyncio.run(server.list_tools())

    assert "get_past_applications" in [tool.name for tool in tools]
