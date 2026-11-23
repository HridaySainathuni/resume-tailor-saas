"""Live demo: run the agent loop end to end and print what it traced.

The demo runs run_agent on a small sample job posting and a sample
resume, then prints the tailored resume, the grounding report, and
the trace spans the run emitted. The job posting and company
research are canned, so the demo never fetches a URL or Wikipedia.

Run it with a fake model client (no API key, no network):

    python scripts/demo.py --fake

Or with the real Anthropic client (needs ANTHROPIC_API_KEY set):

    python scripts/demo.py

The fake client can also be selected with the DEMO_FAKE_CLIENT
environment variable set to 1.
"""
import argparse
import os
import sys

# The demo runs from the repo root, but also works when invoked from
# elsewhere: put the repo root on the path so `app` imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import app.agent
from app import create_app, db
from app.agent import run_agent
from app.config import TestingConfig
from app.models import TailorResult, User
from app.services.llm import create_anthropic_client
from app.tracing import attach_exporter

SAMPLE_JOB_URL = "https://example.com/jobs/software-engineer"

SAMPLE_JOB_POSTING = {
    "text": (
        "Software Engineer at Acme Corp. Build Python services and APIs. "
        "Experience with Flask, PostgreSQL, and automated tests required."
    ),
    "title": "Software Engineer",
    "company": "Acme Corp",
}

SAMPLE_COMPANY = {
    "name": "Acme Corp",
    "summary": "Acme Corp builds widgets for customers around the world.",
    "url": "https://example.com/acme",
}

SAMPLE_RESUME = """Jane Doe
Software Engineer

- Built Python services and APIs with Flask for a customer facing product
- Wrote automated tests with pytest and kept the suite green in CI
- Stored application data in PostgreSQL and tuned slow queries"""


class _FakeTextBlock:
    """Stand-in for an Anthropic text content block."""

    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeToolUseBlock:
    """Stand-in for an Anthropic tool_use content block."""

    def __init__(self, block_id, name, arguments):
        self.type = "tool_use"
        self.id = block_id
        self.name = name
        self.input = arguments


class _FakeResponse:
    """Stand-in for an Anthropic message response."""

    def __init__(self, content):
        self.content = content


class _FakeMessages:
    """Returns canned responses in order."""

    def __init__(self, responses):
        self._responses = list(responses)

    def create(self, **kwargs):
        return self._responses.pop(0)


class _FakeClient:
    """Stand-in for an Anthropic client.

    The first reply calls research_company, the second writes the
    deliverables, using the sample resume as the tailored resume.
    """

    def __init__(self):
        reply = (
            "=== TAILORED RESUME ===\n"
            f"{SAMPLE_RESUME}\n"
            "=== COVER LETTER ===\n"
            "Dear Acme team, I would love to join."
        )
        self.messages = _FakeMessages(
            [
                _FakeResponse(
                    [
                        _FakeToolUseBlock(
                            "toolu_1", "research_company", {"name": "Acme Corp"}
                        )
                    ]
                ),
                _FakeResponse([_FakeTextBlock(reply)]),
            ]
        )


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the resume tailor agent loop on sample data."
    )
    parser.add_argument(
        "--fake",
        action="store_true",
        help="Use a fake model client instead of the Anthropic API "
        "(no key or network needed).",
    )
    return parser.parse_args(argv)


def _build_client(use_fake):
    """Return the model client: fake when asked, real otherwise."""
    if use_fake or os.environ.get("DEMO_FAKE_CLIENT") == "1":
        return _FakeClient()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set. Run with --fake or set "
            "DEMO_FAKE_CLIENT=1 to use the fake client instead."
        )
    return create_anthropic_client(api_key)


def _seed_demo_user(app):
    """Create a demo user whose stored resume is the sample resume.

    read_resume returns the original_resume of the user's newest
    tailor result, so the demo seeds one row holding the sample.
    """
    with app.app_context():
        db.create_all()
        user = User(email="demo@example.com")
        user.set_password("demo-password")
        db.session.add(user)
        db.session.commit()
        db.session.add(
            TailorResult(
                user_id=user.id,
                job_title="",
                company="",
                original_resume=SAMPLE_RESUME,
                job_description="",
                tailored_resume="",
                cover_letter="",
            )
        )
        db.session.commit()
        return user.id


def _print_result(result, exporter):
    print("=== TAILORED RESUME ===")
    print(result["tailored_resume"])
    print()
    print("=== GROUNDING REPORT ===")
    report = result["grounding_report"]
    print(f"Grounding rate: {report.grounding_rate:.2f}")
    for line in report.lines:
        print(f"[{line.verdict} / {line.match or 'none'}] {line.line}")
    print()
    print("=== TRACE SPANS ===")
    for span in exporter.get_finished_spans():
        print(span.name)
        for key, value in span.attributes.items():
            print(f"  {key}: {value}")


def main(argv=None):
    """Run the demo and print its output. Returns the exit code."""
    args = _parse_args(argv)
    client = _build_client(args.fake)

    exporter = InMemorySpanExporter()
    attach_exporter(exporter)

    flask_app = create_app(TestingConfig)
    user_id = _seed_demo_user(flask_app)

    # The demo uses canned tool data so it never hits the network
    # for the posting or the company research.
    original_fetch = app.agent.fetch_job_posting
    original_research = app.agent.research_company
    app.agent.fetch_job_posting = lambda url: SAMPLE_JOB_POSTING
    app.agent.research_company = lambda name: SAMPLE_COMPANY
    try:
        with flask_app.app_context():
            result = run_agent(SAMPLE_JOB_URL, user_id, client=client)
    finally:
        app.agent.fetch_job_posting = original_fetch
        app.agent.research_company = original_research

    _print_result(result, exporter)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
