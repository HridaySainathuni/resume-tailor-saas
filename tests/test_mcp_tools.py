"""Tests for the fetch_job_posting MCP tool.

Network access is mocked: urllib.request.urlopen returns a fake
response holding canned HTML, so no real HTTP request is made.
"""
import asyncio
import urllib.request

import pytest

from mcp_server.server import create_server
from mcp_server.tools import fetch_job_posting

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
