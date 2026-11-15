"""Agent loop for Resume Tailor.

Runs a plain Anthropic tool-calling loop over the four tool
functions from mcp_server.tools. The loop gathers context up front,
then lets the model call tools and returns the final text. The full
tailor and cover letter flow lands in the next slice.
"""
import json
import os

from app.services.llm import TAILOR_MODEL, create_anthropic_client
from mcp_server.tools import (
    fetch_job_posting,
    get_past_applications,
    read_resume,
    research_company,
)

AGENT_MAX_TOKENS = 4000
MAX_TOOL_TURNS = 10

AGENT_SYSTEM_PROMPT = """You are a resume tailoring assistant. You have tools to fetch a job posting, research a company, read the user's resume, and list past applications. Use them when you need more detail, then reply with a short summary of how the resume fits the role."""

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

Use the tools if you need more detail, then reply with a short summary of how the resume fits the role."""


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


def run_agent(job_url: str, user_id: int, client=None) -> str:
    """Run the agent loop for one job application and return the final text.

    Gathers context, then drives the Anthropic tool-calling loop:
    tool_use turns call the plain tool functions and their results
    are fed back as tool_result turns, until the model replies
    with text.

    Args:
        job_url: The URL of the job posting to tailor for.
        user_id: The id of the user whose resume to tailor.
        client: An Anthropic client. When omitted, one is built
            from the ANTHROPIC_API_KEY environment variable.

    Returns:
        The model's final text reply.
    """
    if client is None:
        client = create_anthropic_client(os.environ.get("ANTHROPIC_API_KEY", ""))

    context = gather_context(job_url, user_id)
    messages = [{"role": "user", "content": build_agent_prompt(context)}]

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
