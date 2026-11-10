"""Tests for config loading and the production secret-key check."""
import pytest

from app.config import Config, TestingConfig, _database_url


def test_testing_config_is_safe():
    assert TestingConfig.SECRET_KEY == "test-secret-key"
    assert TestingConfig.TESTING is True


def test_production_requires_a_real_secret_key(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "dev-only-change-me-in-production")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        Config.validate()


def test_production_accepts_a_real_secret_key(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "a-real-random-secret")
    Config.validate()


def test_postgres_url_is_normalised():
    assert _database_url("postgres://user:pass@host/db").startswith("postgresql://")
    assert _database_url("sqlite:///resume_tailor.db") == "sqlite:///resume_tailor.db"
