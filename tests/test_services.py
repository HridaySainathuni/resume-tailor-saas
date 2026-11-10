"""Tests for the service layer: LLM prompts, job import, exports."""
from app.services.exports import build_docx, cover_letter_text_to_html, resume_text_to_html
from app.services.job_import import extract_text_from_html, extract_title_from_html
from app.services.llm import (
    COVER_LETTER_PROMPT,
    SYSTEM_PROMPT,
    build_cover_letter_prompt,
    build_tailor_prompt,
)


class FakeMessage:
    def __init__(self, text):
        self.content = [type("Block", (), {"text": text})()]


class FakeMessages:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeMessage(self.text)


class FakeClient:
    def __init__(self, text="TAILORED"):
        self.messages = FakeMessages(text)


def test_tailor_prompt_includes_inputs_and_no_fabrication_rule():
    prompt = build_tailor_prompt("my resume", "the job", "Engineer", "Acme")
    assert "my resume" in prompt
    assert "the job" in prompt
    assert "Engineer" in prompt
    assert "Acme" in prompt
    assert "never fabricate" in SYSTEM_PROMPT


def test_cover_letter_prompt_and_rules():
    prompt = build_cover_letter_prompt("my resume", "the job", "Engineer", "Acme")
    assert "my resume" in prompt
    assert "Acme" in prompt
    assert "never fabricate" in COVER_LETTER_PROMPT


def test_llm_service_uses_configured_model_and_tokens():
    from app.services.llm import generate_cover_letter_text, tailor_resume_text

    client = FakeClient("DONE")
    assert tailor_resume_text(client, "r", "j", "t", "c") == "DONE"
    assert client.messages.calls[0]["model"] == "claude-sonnet-4-20250514"
    assert client.messages.calls[0]["max_tokens"] == 4000
    assert generate_cover_letter_text(client, "r", "j", "t", "c") == "DONE"
    assert client.messages.calls[1]["max_tokens"] == 2000


def test_extract_text_strips_script_style_and_tags():
    html = "<html><head><style>.x{}</style><script>var x=1;</script></head><body><h1>Job</h1><p>Python developer</p></body></html>"
    text = extract_text_from_html(html)
    assert "Python developer" in text
    assert "var x" not in text
    assert ".x" not in text
    assert "<p>" not in text


def test_extract_title():
    assert extract_title_from_html("<title>  Senior Engineer </title>") == "Senior Engineer"
    assert extract_title_from_html("<p>no title</p>") == ""


def test_resume_text_to_html_escapes_input():
    html = resume_text_to_html("SKILLS\n- Python\n<script>alert(1)</script>")
    assert "<h2>SKILLS</h2>" in html
    assert "<li>Python</li>" in html
    assert "<script>" not in html


def test_cover_letter_text_to_html():
    html = cover_letter_text_to_html("Dear team,\n\nThank you.")
    assert "<p>Dear team,</p>" in html


def test_build_docx_returns_valid_docx_bytes():
    buf = build_docx("SKILLS\n- Python\nPlain line", "Engineer", "Acme")
    data = buf.read()
    assert data[:2] == b"PK"
    assert len(data) > 1000
