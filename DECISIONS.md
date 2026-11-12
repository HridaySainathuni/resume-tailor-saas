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
