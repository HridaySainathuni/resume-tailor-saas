# Decisions

This file records the significant choices in this repo, the alternatives considered, and why each choice won. Read it before changing a decision.

## Update the existing repo instead of starting a new one

Choice: turn resume-tailor-saas into the grounded agent, in place.
Alternative: create a fresh repo for the agent and leave the old app alone.
Why: the existing repo holds the real history and the deployed app. Keeping it shows the change from a single-call app to an agent, and it avoids two repos that do the same job.

## Tests first, then refactor

Choice: write tests for the keyword scorer, models, services, and routes before splitting tailor.py.
Alternative: refactor first and add tests after.
Why: the refactor moves code between files. Tests written first prove the behaviour stays the same while the code moves.

## One service layer, thin routes

Choice: put prompts and Anthropic calls in app/services/llm.py, keyword scoring in app/services/keywords.py, DOCX and PDF work in app/services/exports.py, and URL fetching in app/services/job_import.py. Routes in app/api/tailor.py only validate input, call a service, and return a response.
Alternative: keep the logic in the route file, or split by feature into more blueprints.
Why: the old tailor.py mixed five jobs in about 560 lines. Services can be tested without a request, and the next milestone can reuse them from an agent loop.

## Config lives in app/config.py

Choice: one Config class reads the environment, with a TestingConfig for tests. The factory reads Config and nothing else reads environment variables for settings.
Alternative: keep the wiring inline in the app factory.
Why: inline wiring hid which settings exist and made production checks hard to test. A single config module makes the settings list obvious and testable.

## Fail fast on a bad secret key in production

Choice: in production, the app refuses to start unless SECRET_KEY is set to a real random value.
Alternative: keep the dev default and rely on the deploy config to set it.
Why: a known default secret is a real risk. Failing at startup is louder and safer than running with it.

## Debug off unless FLASK_DEBUG=1

Choice: run.py starts with debug off by default.
Alternative: keep debug on, or read the Flask debug flag from the app config.
Why: debug mode was on unconditionally. A debug server in production leaks information. One explicit flag controls it.

## Do not log password reset links

Choice: generate the reset token, store only its hash, and send nothing to the log. The link goes out by email when an email service is added.
Alternative: keep logging the link for local testing.
Why: a reset link in a log is as good as a password to anyone who can read the log. The old code also flashed a message saying a link was sent when no email was sent, which was misleading.

## Timezone aware datetimes, stored as UTC

Choice: code works with timezone aware datetimes. A small UTCDateTime type in app/models.py stores them as naive UTC in the database and reattaches UTC on read.
Alternative: keep datetime.utcnow, or use DateTime(timezone=True) columns directly.
Why: utcnow is deprecated and naive datetimes cause comparison bugs. Plain timezone aware columns do not round trip on SQLite, which drops the timezone, so the custom type keeps the behaviour correct on SQLite and Postgres.

## Pin dependencies

Choice: requirements.txt pins every direct dependency to a version verified to install together.
Alternative: keep the old greater than ranges.
Why: unpinned ranges let a fresh install pull a new major version without warning. Flask-Limiter moved from 3 to 4 during this work, which is exactly the kind of change a pin catches.

## No migrations yet

Choice: keep db.create_all on startup for this milestone. Add Flask-Migrate and Alembic in a later milestone.
Alternative: add migrations now.
Why: migrations change the deploy story and need a careful first migration for the existing production database. This milestone is about structure and tests, so the migration work stays separate and reviewable.

## Delete the Procfile

Choice: remove Procfile.
Alternative: keep it.
Why: Render runs the Docker image, and the Dockerfile already defines the Gunicorn command. The Procfile was a Heroku leftover that duplicated that command and could drift from it.

## Dockerfile runs as a non-root user

Choice: create an app user and run Gunicorn as that user.
Alternative: keep running as root.
Why: a container that runs as root gives a break out more power than it needs. A dedicated user costs little and is standard practice.

## Generic error messages from the LLM calls

Choice: when an Anthropic call fails, the API returns a generic AI service error instead of the exception text.
Alternative: keep returning the exception text.
Why: exception text can leak upstream details. The caller does not need it, and the server log is the right place for the detail.

## MIT license

Choice: MIT.
Alternative: no license, or a copyleft license.
Why: MIT keeps the code usable by others with minimal friction, which fits a portfolio project.

## No FastAPI migration in this milestone

Choice: stay on Flask.
Alternative: migrate to FastAPI now.
Why: a framework migration is a large change on its own. It would hide the cleanup work in this milestone and delay the agent work that matters more. Revisit it after the agent, verifier, and evals land.

## MCP Python SDK v2 (MCPServer)

Choice: use the MCP Python SDK v2, with the MCPServer class, pinned as mcp==2.3.0.
Alternative: use SDK v1 with FastMCP, or build the protocol by hand over JSON-RPC.
Why: FastMCP was renamed to MCPServer in v2, so the v1 name is already outdated. The SDK handles the protocol, tool registration, and transport, which is less code to maintain than a hand built server. Pinning the version keeps a future SDK change from breaking the server silently.

## stdio transport for the MCP server

Choice: run the MCP server over stdio, started as a subprocess by the agent host.
Alternative: run it over HTTP with server-sent events, or as a long lived service.
Why: stdio is the standard transport for a local MCP server and needs no port, no auth, and no deploy step. The server only runs while the agent needs it. An HTTP transport adds a service to host and secure for no benefit at this stage. If a remote host needs the tools later, the transport can change without touching the tool functions.

## MCP tools as thin wrappers over the service layer

Choice: each MCP tool calls the existing function in app/services and returns its result, adding only input validation and error shaping.
Alternative: duplicate the service logic inside the tool, or call the Flask routes over HTTP.
Why: the service layer already holds the tested logic, and Milestone 1 split it out so it could be reused without a request. Duplicating it would mean two copies to keep in sync. Calling the routes over HTTP would need a running server and a logged in user for tools that do not need either.

## Tool functions kept as plain functions

Choice: the functions in mcp_server/tools.py are plain Python functions. server.py registers them as MCP tools, but the functions themselves know nothing about MCP.
Alternative: write the tools with MCP decorators and types throughout, or put the logic in the server file.
Why: Milestone 3 adds an agent loop that calls these tools in-process. Plain functions let the loop import and call them directly, with no MCP server running and no protocol overhead. Keeping them separate from server.py also keeps the transport and the tool logic independent, so either can change on its own.

## research_company uses the Wikipedia summary API

Choice: research_company fetches the company summary from the Wikipedia REST summary API (en.wikipedia.org/api/rest_v1/page/summary/{name}) with a plain urllib request and a User-Agent header. No API key, account, or paid plan.
Alternative: a paid company data API such as Crunchbase or Clearbit, scraping the company's own website, the Wikipedia action API, or a general web search API.
Why: the summary API needs no key, so there is no secret to store and no quota or billing to manage. It returns a short factual extract plus the canonical page URL, which is all the agent needs for background context on a company. Scraping company sites is fragile because every site is structured differently, and paid APIs add cost and credentials for information that is public. The summary is background context only, not a source for claims in the tailored resume, so a short encyclopedia extract is enough. The trade off is coverage: a company with no Wikipedia page returns an error, and the agent works around that instead of getting a summary.

## Database tools run inside a Flask app context

Choice: read_resume and get_past_applications check has_app_context first. When a context is active they reuse it; otherwise they build an app with the factory and push a context around the query.
Alternative: require the caller to pass in an app or a context, open a raw SQLAlchemy session outside Flask, or create one global app at import time.
Why: the MCP server runs standalone over stdio with no request, so there is no app context unless the tool makes one. Reusing an active context keeps tests on the test database and lets the Milestone 3 agent loop call the functions in-process inside its own context. A global app at import time would bind the server to one config and make tests leak state. A raw session would bypass the Flask-SQLAlchemy session and the app's configuration. Building the app through the factory keeps one way of making an app, in tests and in production.

## Resume text comes from TailorResult.original_resume

Choice: read_resume returns the original_resume column of the user's newest TailorResult row.
Alternative: add a dedicated resumes table, read the uploaded resume file, or return the tailored_resume column.
Why: the tailor results table is where the app already stores each resume a user submits, so there is no separate resume store and no new table or migration is needed for this milestone. original_resume holds the user's own words, while tailored_resume is generated output and must not be treated as the source resume. The agent grounds its claims in the resume the user wrote, so the tool returns that column from the newest result. When the user has never tailored a resume, nothing is stored and the tool returns an error instead of inventing a resume.

## Plain Anthropic tool-calling loop instead of LangGraph

Choice: the agent loop in app/agent.py is a plain Python loop that calls the Anthropic messages API directly, with the four tool functions passed as tool definitions. The loop runs until the model replies with text or hits the turn limit.
Alternative: build the loop on LangGraph, or use a LangChain agent executor.
Why: this loop has one job, a fixed sequence of context gathering followed by model turns that can call tools. A graph framework adds nodes, edges, state objects, and a dependency for behaviour a short loop already expresses clearly. The plain loop is easy to read, easy to test with a mocked client, and has no framework version to track. If the flow later needs branching, retries, or parallel tool calls, a framework becomes worth revisiting.

## Gather context up front, then let the loop write

Choice: gather_context calls all four tools before the first model turn, so the loop starts with the job posting, the company research, the user's resume, and their past applications. The model can still call tools during the loop if it needs more detail.
Alternative: let the model call the tools one by one from an empty start, or put everything in the prompt and give the model no tools at all.
Why: starting empty forces the model to spend turns rediscovering what the app already knows how to fetch, and a wrong first tool call can send the loop off track. Gathering up front guarantees the model has the full picture before it writes anything, and it keeps the tool calls available for follow up detail, such as re-fetching a posting. Prompt only with no tools would lose that follow up ability.

## Marked sections for the deliverables

Choice: the system prompt tells the model to reply with the tailored resume under "=== TAILORED RESUME ===" and the cover letter under "=== COVER LETTER ===", and parse_deliverables splits the reply on those markers. A missing marker or an empty section raises ValueError.
Alternative: ask for JSON output, make two separate model calls (one per deliverable), or parse free-form text.
Why: markers are simple to produce and simple to split on, with no escaping rules to get wrong. JSON output risks a malformed object when the model writes long text with quotes and line breaks. Two calls double the cost and the latency for work one reply already does. Free-form text has no reliable boundary between the two documents. Raising on a bad reply is better than saving a half parsed document.

## Score the loop output with the keyword helper

Choice: run_agent scores the tailored resume against the job description with the existing score_resume helper and returns the score with the result.
Alternative: skip scoring in the loop, or score only in the single-call route.
Why: the single-call path already returns an ATS score, so the loop should carry the same quality signal. Reusing the helper keeps one scoring implementation. The score is returned to the caller rather than stored, because the TailorResult model has no score column and adding one is a separate migration decision.

## A failed fetch or resume read raises and saves nothing

Choice: when the job posting cannot be fetched or the resume cannot be read, run_agent raises ValueError before any model call, and nothing is saved. A model reply without usable deliverables also raises before saving.
Alternative: save a partial TailorResult with what was gathered, retry the fetch silently, or return empty deliverables.
Why: a saved row is history the user can revisit. A row with no real posting or no resume would be misleading, and a row with empty deliverables is worse than no row. Raising surfaces the failure to the caller, which can report it honestly, instead of hiding it behind a saved record. Retrying silently would mask a bad URL or a missing resume that the user needs to fix.

## Verifier checks exact match first, then a normalized fuzzy match

Choice: verify_grounding in app/verifier.py checks each line of the tailored resume against the source resume in two steps. First it normalizes both lines (lowercase, punctuation stripped, whitespace collapsed) and checks for equality. If that fails, it compares the normalized lines with difflib SequenceMatcher and counts the line grounded when the similarity ratio is at least 0.8. A line that passes neither step is unsupported.
Alternative: exact string match only, a single similarity score with no exact step, or an LLM based check that asks a model whether each line is supported.
Why: exact match alone would flag every reworded line, and tailoring rewrites lines on purpose. A fuzzy check alone would spend a similarity comparison on lines that are copied verbatim, and the exact step makes the common case cheap and unambiguous. The normalized comparison ignores case, punctuation, and spacing, so formatting changes do not count as new content. An LLM based check would cost a model call per resume and could itself invent a judgement; a deterministic text comparison is fast, free, and reproducible. The 0.8 threshold is a starting point: high enough that a line with a changed fact usually falls below it, low enough that ordinary rewording passes.

## Grounding rate as the summary measure

Choice: GroundingReport exposes a grounding_rate property: the share of checked lines with a grounded verdict, 0.0 for an empty report. The report itself keeps every per-line verdict.
Alternative: report only a pass or fail for the whole resume, report a count of unsupported lines with no rate, or store the rate as a field set at check time.
Why: a single rate is easy to compare across runs and to show in a summary, and it stays meaningful as resumes grow or shrink, where a raw count does not. The per-line verdicts stay in the report because a rate alone does not say which lines to fix. A property computed from the verdicts keeps the rate and the lines in agreement by construction, instead of storing two values that could drift apart.

## Verifier wired into run_agent without changing what the loop writes or saves

Choice: run_agent calls verify_grounding on the tailored resume against the source resume after the loop finishes, and returns the GroundingReport in its result dict under "grounding_report". The TailorResult row it saves is unchanged: same columns, same values, no new column for the report.
Alternative: save the report or the rate on the TailorResult row, have the verifier run before saving and block the save on a low rate, or run the check in a separate route instead of the loop.
Why: the verifier is a report, not a gate. Blocking the save on a low rate would discard a resume the user may still want to see and fix, and a rate threshold is a product decision this milestone does not make. Adding a column would need a migration for a value the caller can already compute from the saved texts. Returning the report from run_agent gives the caller the full detail without changing the saved history, and keeping the write path untouched means the existing save behaviour and its tests stay valid.

## Three-way comparison in the eval suite

Choice: the eval harness in app/evals.py runs three approaches on every fixture pair: the old single-call baseline, the agent loop, and the agent loop with the grounding verifier, then scores each one the same way.
Alternative: compare only the agent against the baseline, compare the agent with and without the verifier only, or add a fourth approach that runs the verifier as a rewrite step.
Why: each approach answers a different question. The baseline shows what the original app already did, so any gain has a starting point. The agent shows what the loop adds over the single call. The agent with the verifier shows what dropping unsupported lines costs and buys: fabrication should fall, but keyword coverage may fall with it if grounded lines that carried keywords get dropped. Comparing all three on the same pairs keeps those trade-offs visible in one table instead of three separate runs. A verifier-as-rewrite approach is a real fourth option, but it is a different design decision, so it stays out of this comparison until the three-way numbers say whether dropping lines is enough.

## Wilson interval for aggregated eval rates

Choice: aggregate_results reports each approach's mean fabrication rate, mean keyword coverage, and share of relevant pairs with a Wilson score interval at 95 percent confidence, using the number of pairs as the sample size.
Alternative: report the mean with a normal approximation interval (mean plus or minus 1.96 standard errors), report the mean with no interval, or bootstrap the interval from the pair values.
Why: the eval runs on a small number of pairs, and the rates sit near 0 or 1, which is exactly where the normal approximation breaks: it can produce intervals that run past 0 or 1 and it undercovers when the true rate is near an edge. The Wilson interval stays inside [0, 1] by construction and behaves sensibly with few pairs or extreme rates. No interval at all would hide how little a handful of pairs can prove. Bootstrapping the same few pairs adds resampling machinery without adding information, since the pairs are the whole sample.

## Judge relevance as a third eval measure

Choice: the eval suite scores each tailored resume for relevance with a small LLM judge in app/evals.py. judge_relevance asks the model one question, whether the tailored resume fits the job description, and accepts a single-word verdict, RELEVANT or NOT_RELEVANT. A verdict the parser cannot read counts as not relevant. run_eval records the verdict per pair, and aggregate_results reports the share of relevant pairs per approach.
Alternative: judge relevance by keyword overlap alone, use a graded rubric with a 1 to 5 score, or skip relevance and rely on fabrication rate and keyword coverage.
Why: fabrication rate and keyword coverage are grounded, deterministic checks, but neither says whether the resume actually fits the job. A tailored resume can reuse only true lines and hit every keyword while still being a poor match for the role, and keyword coverage alone cannot tell that apart from a good one. An LLM verdict catches fit in a way a word count cannot. A graded rubric would give more detail, but a binary verdict keeps the judge small, the parsing unambiguous, and the aggregation a simple share. Treating an unparsable verdict as not relevant keeps a confused judge reply from inflating the score.

## Console exporter by default, in-memory exporter for tests

Choice: configure_tracing sets up a console exporter by default, and takes an optional exporter so tests can pass an InMemorySpanExporter and inspect the spans a run emitted. attach_exporter adds an exporter to the provider after setup, so a script can capture spans even when tracing was already configured.
Alternative: export spans to an OTLP collector, write them to a file, or keep one global exporter with no way to add another.
Why: this milestone has no collector to send spans to, and a console exporter shows the trace on every run with no setup. Tests cannot read console output reliably, so they pass an in-memory exporter and assert on the finished spans. attach_exporter exists because configure_tracing is first call wins: a test module configures tracing at import, and the demo script needs its own exporter on top of that instead of silently getting none. An OTLP collector adds a service to run and configure for a trace that is only read locally right now; it can replace the console exporter later without changing the instrumented code.

## Demo as a script instead of a UI page

Choice: the live demo is scripts/demo.py, a command line script that runs run_agent on sample data and prints the tailored resume, the grounding report, and the trace spans.
Alternative: add a demo page to the Flask app, or a notebook.
Why: the demo shows the agent loop and its trace, which are backend behaviour. A UI page would need a route, a template, and a logged in user with a stored resume, all for a run whose output is text. A script runs the same code path with a fake model client and canned tool data, so it needs no API key, no network, and no account, and its output is plain text that a test can assert on. A notebook would add a dependency and a format that is harder to run in CI. The script stays runnable from the command line and from the test suite.
