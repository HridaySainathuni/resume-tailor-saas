"""Eval harness for Resume Tailor.

Runs the three tailoring approaches (single-call baseline, agent loop,
agent loop with the grounding verifier) over resume/job fixture pairs
and reports fabrication rate and keyword coverage per pair. The
fixtures used with this harness are synthetic and exist only to
exercise it; the real eval dataset is a later slice.
"""
import os
from dataclasses import dataclass, field

from app.agent import run_agent
from app.services.keywords import score_resume
from app.services.llm import create_anthropic_client, tailor_resume_text
from app.verifier import verify_grounding

BASELINE = "baseline"
AGENT = "agent"
AGENT_WITH_VERIFIER = "agent_with_verifier"

APPROACHES = (BASELINE, AGENT, AGENT_WITH_VERIFIER)

DEFAULT_JOB_URL = "https://example.com/jobs/eval"


@dataclass
class EvalPair:
    """One resume/job pair to evaluate, plus the agent's inputs for it.

    The agent loop fetches its job posting by URL and reads the resume
    by user id, so a pair carries those alongside the raw texts.
    """

    resume: str
    job_description: str
    job_title: str = ""
    company: str = ""
    job_url: str = DEFAULT_JOB_URL
    user_id: int = 1


@dataclass
class ApproachResult:
    """One approach's tailored resume and its scores for a pair."""

    approach: str
    tailored_resume: str
    fabrication_rate: float
    keyword_coverage: float


@dataclass
class PairResult:
    """All three approaches' results for one fixture pair."""

    pair: EvalPair
    results: dict[str, ApproachResult] = field(default_factory=dict)


def fabrication_rate(tailored_resume: str, source_resume: str) -> float:
    """Share of tailored lines unsupported by the source resume.

    Unsupported lines over total lines, from the verifier. An empty
    tailored resume has no lines to be unsupported, so it scores 0.0.
    """
    report = verify_grounding(tailored_resume, source_resume)
    if not report.lines:
        return 0.0
    return 1.0 - report.grounding_rate


def keyword_coverage(tailored_resume: str, job_description: str) -> float:
    """Share of the job description's top keywords in the tailored resume."""
    score = score_resume(tailored_resume, job_description)
    total = score["total_jd_keywords"]
    if total == 0:
        return 0.0
    return score["matched_count"] / total


def _run_baseline(pair: EvalPair, client) -> str:
    """Tailor with the old single-call path."""
    return tailor_resume_text(
        client, pair.resume, pair.job_description, pair.job_title, pair.company
    )


def _run_agent(pair: EvalPair, client) -> str:
    """Tailor with the agent loop and return its tailored resume."""
    result = run_agent(pair.job_url, pair.user_id, client=client)
    return result["tailored_resume"]


def _run_agent_with_verifier(pair: EvalPair, client) -> str:
    """Tailor with the agent loop, then drop lines the verifier rejects.

    The verifier checks each tailored line against the source resume,
    so only grounded lines survive.
    """
    tailored = _run_agent(pair, client)
    report = verify_grounding(tailored, pair.resume)
    grounded = [line.line for line in report.lines if line.verdict == "grounded"]
    return "\n".join(grounded)


def _score(approach: str, tailored_resume: str, pair: EvalPair) -> ApproachResult:
    """Score one tailored resume for fabrication and keyword coverage."""
    return ApproachResult(
        approach=approach,
        tailored_resume=tailored_resume,
        fabrication_rate=fabrication_rate(tailored_resume, pair.resume),
        keyword_coverage=keyword_coverage(tailored_resume, pair.job_description),
    )


def run_eval(pairs: list[EvalPair], client=None) -> list[PairResult]:
    """Run all three approaches on each pair and score the results.

    Args:
        pairs: The resume/job fixture pairs to evaluate.
        client: An Anthropic client. When omitted, one is built from
            the ANTHROPIC_API_KEY environment variable.

    Returns:
        One PairResult per pair, each holding an ApproachResult for
        the baseline, the agent, and the agent with the verifier.
    """
    if client is None:
        client = create_anthropic_client(os.environ.get("ANTHROPIC_API_KEY", ""))

    runners = {
        BASELINE: _run_baseline,
        AGENT: _run_agent,
        AGENT_WITH_VERIFIER: _run_agent_with_verifier,
    }
    results = []
    for pair in pairs:
        pair_result = PairResult(pair=pair)
        for approach in APPROACHES:
            tailored = runners[approach](pair, client)
            pair_result.results[approach] = _score(approach, tailored, pair)
        results.append(pair_result)
    return results
