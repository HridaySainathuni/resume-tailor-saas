"""Agent loop for Resume Tailor.

Runs a plain Anthropic tool-calling loop over the four tool
functions from mcp_server.tools. The loop gathers context up front,
then lets the model call tools and write the finished deliverables:
a tailored resume and a cover letter. The deliverables are scored
against the job description with the keyword helper and saved as
a TailorResult row.
"""
import json
import os

from flask import has_app_context

from app import create_app, db
from app.models import TailorResult
from app.services.keywords import score_resume
from app.services.llm import TAILOR_MODEL, create_anthropic_client
from mcp_server.tools import (
    fetch_job_posting,
    get_past_applications,
    read_resume,
    research_company,
)

AGENT_MAX_TOKENS = 4000
MAX_TOOL_TURNS = 10

RESUME_MARKER = "=== TAILORED RESUME ==="
COVER_LETTER_MARKER = "=== COVER LETTER ==="

AGENT_SYSTEM_PROMPT = """You are a resume tailoring assistant. You have tools to fetch a job posting, research a company, read the user's resume, and list past applications. Use them when you need more detail.

When you have what you need, write the finished deliverables and reply with exactly this format, nothing else:

=== TAILORED RESUME ===
<the full tailored resume text>

=== COVER LETTER ===
<the full cover letter text>

Rules for the tailored resume:
1. Keep ALL truthful experience — never fabricate or exaggerate
2. Reorder bullet points to prioritize relevant experience
3. Mirror keywords and phrases from the job description naturally
4. Quantify achievements where possible
5. Adjust the professional summary to target this specific role
6. Remove or de-emphasize irrelevant details
7. Keep formatting clean and ATS-friendly

Rules for the cover letter:
1. Use the resume to draw out relevant achievements — never fabricate
2. Open with a strong hook specific to the company and role
3. Show genuine enthusiasm and knowledge of the company when possible
4. Keep it concise — 3-4 paragraphs, under 400 words
5. End with a confident call-to-action
6. Do NOT include placeholder brackets like [Your Name] — write it ready to send"""

TOOL_DEFINITIONS = [
    {
        "name": "fetch_job_posting",
        "description": "Fetch a job posting and return its text, title, and company.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL of the job posting to fetch."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "research_company",
        "description": "Research a company from its Wikipedia summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The company name to look up."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "read_resume",
        "description": "Return the user's most recent resume text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "description": "The id of the user."},
            },
            "required": ["user_id"],
        },
    },
    {
        "name": "get_past_applications",
        "description": "Return the user's past applications, newest first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "description": "The id of the user."},
            },
            "required": ["user_id"],
        },
    },
]


def gather_context(job_url: str, user_id: int) -> dict:
    """Gather the context the agent loop starts from.

    Calls all four tool functions up front: the posting, company
    research for the posting's company, the user's resume, and
    their past applications.

    Args:
        job_url: The URL of the job posting to tailor for.
        user_id: The id of the user whose resume to tailor.

    Returns:
        A dict with "job_posting", "company", "resume", and
        "past_applications".
    """
    job_posting = fetch_job_posting(job_url)
    company_name = job_posting.get("company") if isinstance(job_posting, dict) else None
    company = research_company(company_name) if company_name else {"error": "No company in posting."}
    return {
        "job_posting": job_posting,
        "company": company,
        "resume": read_resume(user_id),
        "past_applications": get_past_applications(user_id),
    }


def build_agent_prompt(context: dict) -> str:
    """Render the gathered context into the loop's first user message."""
    return f"""Here is the context for a job application:

Job posting:
---
{json.dumps(context["job_posting"], indent=2)}
---

Company research:
---
{json.dumps(context["company"], indent=2)}
---

Resume:
---
{context["resume"] if isinstance(context["resume"], str) else json.dumps(context["resume"], indent=2)}
---

Past applications:
---
{json.dumps(context["past_applications"], indent=2)}
---

Use the tools if you need more detail, then write the tailored resume and cover letter in the format from your instructions."""


def parse_deliverables(text: str) -> tuple:
    """Split a loop reply into the tailored resume and cover letter.

    The reply must carry both markers from the system prompt, with
    the resume between them and the cover letter after the second.

    Args:
        text: The model's final text reply.

    Returns:
        A (tailored_resume, cover_letter) tuple, both stripped.

    Raises:
        ValueError: When a marker is missing or a section is empty.
    """
    if RESUME_MARKER not in text or COVER_LETTER_MARKER not in text:
        raise ValueError(
            "Agent reply did not include both a tailored resume and a cover letter."
        )
    resume = text.split(RESUME_MARKER, 1)[1].split(COVER_LETTER_MARKER, 1)[0].strip()
    cover_letter = text.split(COVER_LETTER_MARKER, 1)[1].strip()
    if not resume or not cover_letter:
        raise ValueError(
            "Agent reply did not include both a tailored resume and a cover letter."
        )
    return resume, cover_letter


def _call_tool(name: str, arguments: dict):
    """Call one of the four tool functions by name.

    Looks the function up here (rather than in a fixed table) so
    tests can replace a tool on this module.
    """
    if name == "fetch_job_posting":
        return fetch_job_posting(**arguments)
    if name == "research_company":
        return research_company(**arguments)
    if name == "read_resume":
        return read_resume(**arguments)
    if name == "get_past_applications":
        return get_past_applications(**arguments)
    return {"error": f"Unknown tool: {name}"}


def _content_to_dicts(content) -> list:
    """Convert a response's content blocks to plain dicts for the next turn."""
    blocks = []
    for block in content:
        if block.type == "text":
            blocks.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            blocks.append(
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )
    return blocks


def _run_loop(client, messages: list) -> str:
    """Drive the Anthropic tool-calling loop until the model replies with text.

    Tool_use turns call the plain tool functions and their results
    are fed back as tool_result turns.

    Args:
        client: An Anthropic client.
        messages: The conversation so far, starting with the user
            message built from the gathered context.

    Returns:
        The model's final text reply.

    Raises:
        RuntimeError: When the loop does not finish within
            MAX_TOOL_TURNS tool turns.
    """
    for _ in range(MAX_TOOL_TURNS):
        response = client.messages.create(
            model=TAILOR_MODEL,
            max_tokens=AGENT_MAX_TOKENS,
            system=AGENT_SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )
        tool_uses = [block for block in response.content if block.type == "tool_use"]
        if not tool_uses:
            return "".join(block.text for block in response.content if block.type == "text")

        messages.append({"role": "assistant", "content": _content_to_dicts(response.content)})
        tool_results = []
        for block in tool_uses:
            result = _call_tool(block.name, block.input or {})
            content = result if isinstance(result, str) else json.dumps(result)
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": content}
            )
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError(f"Agent loop did not finish within {MAX_TOOL_TURNS} tool turns.")


def _save_tailor_result(user_id, job_title, company, original_resume, job_description,
                        tailored_resume, cover_letter) -> int:
    """Save the finished deliverables as a TailorResult row and return its id.

    Uses the active Flask app context when there is one, otherwise
    builds an app like the tool functions in mcp_server.tools do.
    """
    result = TailorResult(
        user_id=user_id,
        job_title=job_title,
        company=company,
        original_resume=original_resume,
        job_description=job_description,
        tailored_resume=tailored_resume,
        cover_letter=cover_letter,
    )
    if has_app_context():
        db.session.add(result)
        db.session.commit()
        return result.id
    app = create_app()
    with app.app_context():
        db.session.add(result)
        db.session.commit()
        return result.id


def run_agent(job_url: str, user_id: int, client=None) -> dict:
    """Run the agent loop for one job application and save the deliverables.

    Gathers context, then drives the Anthropic tool-calling loop
    until the model writes the tailored resume and cover letter.
    The tailored resume is scored against the job description with
    the keyword helper, and both deliverables are saved as a
    TailorResult row.

    Args:
        job_url: The URL of the job posting to tailor for.
        user_id: The id of the user whose resume to tailor.
        client: An Anthropic client. When omitted, one is built
            from the ANTHROPIC_API_KEY environment variable.

    Returns:
        A dict with "tailored_resume", "cover_letter", "ats_score",
        "result_id", "job_title", and "company".

    Raises:
        ValueError: When the job posting cannot be fetched, the
            resume cannot be read, or the model's reply has no
            usable deliverables. Nothing is saved in those cases.
    """
    if client is None:
        client = create_anthropic_client(os.environ.get("ANTHROPIC_API_KEY", ""))

    context = gather_context(job_url, user_id)
    job_posting = context["job_posting"]
    if isinstance(job_posting, dict) and job_posting.get("error"):
        raise ValueError(f"Could not fetch job posting: {job_posting['error']}")
    resume = context["resume"]
    if isinstance(resume, dict) and resume.get("error"):
        raise ValueError(f"Could not read resume: {resume['error']}")

    messages = [{"role": "user", "content": build_agent_prompt(context)}]
    final_text = _run_loop(client, messages)
    tailored_resume, cover_letter = parse_deliverables(final_text)

    job_description = job_posting.get("text") or ""
    job_title = job_posting.get("title") or ""
    company = job_posting.get("company") or ""
    ats_score = score_resume(tailored_resume, job_description)
    result_id = _save_tailor_result(
        user_id, job_title, company, resume, job_description, tailored_resume, cover_letter
    )
    return {
        "tailored_resume": tailored_resume,
        "cover_letter": cover_letter,
        "ats_score": ats_score,
        "result_id": result_id,
        "job_title": job_title,
        "company": company,
    }
