"""MCP tool functions for Resume Tailor.

Each function here is a plain Python function (not MCP-specific) so
the agent loop in Milestone 3 can call them in-process. The server in
server.py registers them as MCP tools.
"""
from app.services.job_import import fetch_job_posting as _fetch_job_posting


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
