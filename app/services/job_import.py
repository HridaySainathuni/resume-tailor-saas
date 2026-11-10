"""Import a job description from a URL by extracting its text.

Network access stays in one function so tests can call the pure
HTML parsing without fetching anything.
"""
import re
import urllib.request
from html import unescape

MAX_TEXT_LENGTH = 10000
MAX_TITLE_LENGTH = 200


def extract_text_from_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = unescape(text)
    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def extract_title_from_html(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return unescape(match.group(1).strip())


def fetch_job_posting(url: str) -> dict:
    """Fetch a posting URL and return its text and title."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("Invalid URL")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ResumeTailor/1.0)"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    text = extract_text_from_html(html)
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]
    title = extract_title_from_html(html)
    return {"text": text, "title": title[:MAX_TITLE_LENGTH] if title else "", "company": ""}
