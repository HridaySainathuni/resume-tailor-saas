"""Application configuration, loaded from the environment.

One place owns every setting. The app factory reads this module and
nothing else reads environment variables directly for config.
"""
import os

DEFAULT_SECRET_KEY = "dev-only-change-me-in-production"


def _is_production() -> bool:
    return os.getenv("FLASK_ENV") == "production" or os.getenv("ENV") == "production"


def _database_url(default: str) -> str:
    url = os.getenv("DATABASE_URL", default)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    """Base config. Safe defaults for local development only."""

    SECRET_KEY = os.getenv("SECRET_KEY", DEFAULT_SECRET_KEY)
    SQLALCHEMY_DATABASE_URI = _database_url("sqlite:///resume_tailor.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

    @classmethod
    def validate(cls) -> None:
        """Fail fast in production instead of running with a known secret."""
        if _is_production():
            secret = os.getenv("SECRET_KEY", "")
            if not secret or secret == DEFAULT_SECRET_KEY:
                raise RuntimeError(
                    "SECRET_KEY must be set to a random value in production"
                )


class TestingConfig(Config):
    """Config for tests. Never used in production."""

    TESTING = True
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    ANTHROPIC_API_KEY = ""
    STRIPE_SECRET_KEY = ""
    STRIPE_WEBHOOK_SECRET = ""
