"""Configuration loading and validation."""

import pytest
from pydantic import ValidationError

from weather.core.config import Settings, get_settings


def test_defaults_are_usable_without_any_environment(monkeypatch):
    """The defaults must hold on a clean environment, so the ambient
    variables the test runner may have set are cleared first."""
    for var in ("APP_NAME", "ENVIRONMENT", "DEBUG"):
        monkeypatch.delenv(var, raising=False)
    settings = Settings()
    assert settings.app_name == "weather-service"
    assert settings.environment == "development"


def test_environment_variables_override_defaults(monkeypatch):
    monkeypatch.setenv("APP_NAME", "custom-name")
    monkeypatch.setenv("DEBUG", "true")
    settings = Settings()
    assert settings.app_name == "custom-name"
    assert settings.debug is True


def test_an_unknown_environment_is_rejected(monkeypatch):
    """Typos in configuration should fail loudly at startup, not turn
    into strange behaviour hours later."""
    monkeypatch.setenv("ENVIRONMENT", "staging")
    with pytest.raises(ValidationError):
        Settings()


def test_a_malformed_database_url_is_rejected(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "not-a-url")
    with pytest.raises(ValidationError):
        Settings()


def test_is_production_reflects_the_environment():
    assert Settings(environment="production").is_production
    assert not Settings(environment="development").is_production


def test_settings_are_cached():
    """The same object every time: FastAPI injects this per request, and
    re-reading the environment on each one would be wasteful."""
    assert get_settings() is get_settings()
