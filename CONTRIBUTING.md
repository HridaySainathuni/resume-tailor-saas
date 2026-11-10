# Contributing

## How to work on this repo

1. Open an issue first. Describe the goal, the scope, and the acceptance criteria. State what is out of scope.
2. Work on a branch named after the milestone or fix, for example milestone-1-cleanup.
3. Open one pull request per milestone or fix. Keep it small enough to review in one sitting.
4. Do not merge your own pull request without a review.

## Running the app

Copy the example environment file and fill in your keys:

    cp .env.example .env

Install dependencies and start the app:

    pip install -r requirements.txt
    python run.py

The app runs at http://localhost:5000.

## Running tests

Install the dev dependencies, then run pytest and ruff:

    pip install -r requirements-dev.txt
    python -m pytest -q
    python -m ruff check .

Tests use an in-memory SQLite database and mocked Anthropic calls. They never call a live API.

## Code standards

- Keep routes thin. Put logic in app/services and keep it testable without a request.
- Add a test for new behaviour before or with the change.
- Pin new dependencies in requirements.txt.
- Never commit secrets. Use .env.example for placeholders only.
- Write commit messages that say what changed and why.
