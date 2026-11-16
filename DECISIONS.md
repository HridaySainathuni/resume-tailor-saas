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
