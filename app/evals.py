"""Eval harness for Resume Tailor.

Runs the three tailoring approaches (single-call baseline, agent loop,
agent loop with the grounding verifier) over resume/job fixture pairs
and reports fabrication rate, keyword coverage, and judge relevance
per pair. The fixtures used with this harness are synthetic and exist
only to exercise it; the real eval dataset is a later slice.
"""
import math
import os
from dataclasses import dataclass, field

from app.agent import run_agent
from app.services.keywords import score_resume
from app.services.llm import (
    TAILOR_MODEL,
    create_anthropic_client,
    tailor_resume_text,
)
from app.verifier import verify_grounding

BASELINE = "baseline"
AGENT = "agent"
AGENT_WITH_VERIFIER = "agent_with_verifier"

APPROACHES = (BASELINE, AGENT, AGENT_WITH_VERIFIER)

DEFAULT_JOB_URL = "https://example.com/jobs/eval"

JUDGE_MAX_TOKENS = 20

JUDGE_SYSTEM_PROMPT = """You are a hiring screener judging whether a tailored resume is relevant to a job description. Reply with exactly one word: RELEVANT if the resume's experience matches the role, NOT_RELEVANT if it does not. Reply with the single word only, no explanation."""


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
    relevant: bool = False


@dataclass
class PairResult:
    """All three approaches' results for one fixture pair."""

    pair: EvalPair
    results: dict[str, ApproachResult] = field(default_factory=dict)


def build_judge_prompt(tailored_resume: str, job_description: str) -> str:
    return f"""Here is the tailored resume:

---
{tailored_resume}
---

Here is the job description:

---
{job_description}
---

Is this resume relevant to this job? Reply with exactly one word: RELEVANT or NOT_RELEVANT."""


def judge_relevance(client, tailored_resume: str, job_description: str) -> bool:
    """Ask the model whether a tailored resume fits the job.

    Returns True when the model's verdict is RELEVANT. Any other
    verdict, including NOT_RELEVANT and anything unparsable, counts
    as not relevant, so a confusing reply never inflates the score.
    """
    message = client.messages.create(
        model=TAILOR_MODEL,
        max_tokens=JUDGE_MAX_TOKENS,
        system=JUDGE_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": build_judge_prompt(tailored_resume, job_description)}
        ],
    )
    verdict = message.content[0].text.strip().upper().replace(" ", "").replace("_", "")
    if verdict.startswith("NOTRELEVANT"):
        return False
    return verdict.startswith("RELEVANT")


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


def _score(approach: str, tailored_resume: str, pair: EvalPair, client) -> ApproachResult:
    """Score one tailored resume for fabrication, coverage, and relevance."""
    return ApproachResult(
        approach=approach,
        tailored_resume=tailored_resume,
        fabrication_rate=fabrication_rate(tailored_resume, pair.resume),
        keyword_coverage=keyword_coverage(tailored_resume, pair.job_description),
        relevant=judge_relevance(client, tailored_resume, pair.job_description),
    )


@dataclass
class MetricSummary:
    """One metric's mean across pairs with its Wilson interval."""

    mean: float
    low: float
    high: float


@dataclass
class ApproachSummary:
    """One approach's aggregated fabrication, coverage, and relevance summaries."""

    approach: str
    fabrication_rate: MetricSummary
    keyword_coverage: MetricSummary
    relevance_share: MetricSummary


Z_95 = 1.96


def wilson_interval(proportion: float, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a proportion at the given confidence.

    Args:
        proportion: The observed proportion, between 0 and 1.
        n: The number of observations behind the proportion.
        z: The normal quantile for the confidence level (1.96 for 95%).

    Returns:
        A (low, high) pair clipped to [0, 1].
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0.0 <= proportion <= 1.0:
        raise ValueError("proportion must be between 0 and 1")
    z_squared = z * z
    denominator = 1 + z_squared / n
    center = (proportion + z_squared / (2 * n)) / denominator
    half_width = (
        z * math.sqrt(proportion * (1 - proportion) / n + z_squared / (4 * n * n))
    ) / denominator
    return (max(0.0, center - half_width), min(1.0, center + half_width))


def _summarize(values: list[float]) -> MetricSummary:
    """Mean of per-pair values with a Wilson interval over the pairs."""
    mean = sum(values) / len(values)
    low, high = wilson_interval(mean, len(values))
    return MetricSummary(mean=mean, low=low, high=high)


def aggregate_results(pair_results: list[PairResult]) -> dict[str, ApproachSummary]:
    """Aggregate per-pair results into a summary per approach.

    For each of the three approaches, returns the mean fabrication rate,
    mean keyword coverage, and share of pairs judged relevant across
    the pairs, each with a Wilson score interval at 95 percent
    confidence. The interval treats the number of pairs as the sample
    size, so it tightens as more pairs agree.

    Args:
        pair_results: The per-pair results from run_eval.

    Returns:
        One ApproachSummary per approach, keyed by approach name.
    """
    if not pair_results:
        raise ValueError("at least one pair result is required")
    summaries = {}
    for approach in APPROACHES:
        fabrication = [r.results[approach].fabrication_rate for r in pair_results]
        coverage = [r.results[approach].keyword_coverage for r in pair_results]
        relevance = [
            1.0 if r.results[approach].relevant else 0.0 for r in pair_results
        ]
        summaries[approach] = ApproachSummary(
            approach=approach,
            fabrication_rate=_summarize(fabrication),
            keyword_coverage=_summarize(coverage),
            relevance_share=_summarize(relevance),
        )
    return summaries


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
            pair_result.results[approach] = _score(approach, tailored, pair, client)
        results.append(pair_result)
    return results
