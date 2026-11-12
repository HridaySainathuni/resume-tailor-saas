"""MCP tool functions for Resume Tailor.

Each function here is a plain Python function (not MCP-specific) so
the agent loop in Milestone 3 can call them in-process. The server in
server.py registers them as MCP tools.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from flask import has_app_context

from app import create_app
from app.models import TailorResult
from app.services.job_import import fetch_job_posting as _fetch_job_posting

WIKIPEDIA_SUMMARY_URL = (
    "https://en.wikipedia.org/api/rest_v1/page/summary/{name}"
)


def fetch_job_posting(url: str) -> dict:
    """Fetch a job posting and return its text, title, and company.

    Args:
        url: The URL of the job posting to fetch.

    Returns:
        A dict with "text", "title", and "company" on success, or
        {"error": ...} when the URL is invalid.
    """
    try:
        return _fetch_job_posting(url)
    except ValueError as exc:
        return {"error": str(exc)}


def research_company(name: str) -> dict:
    """Research a company from its Wikipedia summary.

    Args:
        name: The company name to look up.

    Returns:
        A dict with "name", "summary", and "url" on success, or
        {"error": ...} when the company is not found or the
        fetch fails.
    """
    if not name or not name.strip():
        return {"error": "Company name is required."}

    encoded = urllib.parse.quote(name.strip())
    url = WIKIPEDIA_SUMMARY_URL.format(name=encoded)
    request = urllib.request.Request(url, headers={"User-Agent": "ResumeTailor/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"error": f"No Wikipedia page found for '{name.strip()}'."}
        return {"error": f"Wikipedia request failed with status {exc.code}."}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"error": f"Could not research '{name.strip()}': {exc}"}

    if data.get("type") == "disambiguation" or not data.get("extract"):
        return {"error": f"No Wikipedia summary found for '{name.strip()}'."}

    page_url = data.get("content_urls", {}).get("desktop", {}).get("page")
    return {
        "name": data.get("title", name.strip()),
        "summary": data["extract"],
        "url": page_url or url,
    }


def read_resume(user_id: int):
    """Return the user's most recent resume text.

    The resume text is the original_resume of the user's latest
    tailor result. Runs inside a Flask app context: reuses the
    active one when there is one (for example in tests), otherwise
    builds an app with the factory so the MCP server can call it
    without a request.

    Args:
        user_id: The id of the user whose resume to read.

    Returns:
        The resume text on success, or {"error": "No resume found"}
        when nothing is stored for that user.
    """
    if has_app_context():
        return _read_resume_from_db(user_id)
    app = create_app()
    with app.app_context():
        return _read_resume_from_db(user_id)


def _read_resume_from_db(user_id: int):
    """Look up the latest stored resume for a user in this context."""
    latest = (
        TailorResult.query.filter_by(user_id=user_id)
        .order_by(TailorResult.created_at.desc(), TailorResult.id.desc())
        .first()
    )
    if latest is None or not latest.original_resume:
        return {"error": "No resume found"}
    return latest.original_resume
