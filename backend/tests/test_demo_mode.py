"""
Regression tests: demo mode must be opt-in and impossible in production.

WHY: Demo mode accepts a shared, publicly documented login. It used to default to
true, so any deployment that forgot DEMO_MODE=false was open to anyone.
"""

import pytest
from pydantic import ValidationError

# Imported at module load, under conftest's valid env: importing config later,
# after monkeypatching a bad env, would fail in the module-level settings object.
from config import Settings


def test_demo_mode_is_off_by_default(monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert Settings().demo_mode is False


def test_demo_mode_refused_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEMO_MODE", "true")
    with pytest.raises(ValidationError, match="DEMO_MODE"):
        Settings()


@pytest.mark.parametrize("env", ["development", "testing"])
def test_demo_mode_allowed_outside_production(monkeypatch, env):
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv("DEMO_MODE", "true")
    assert Settings().demo_mode is True


def test_production_without_demo_mode_is_fine(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DEMO_MODE", raising=False)
    settings = Settings()
    assert settings.app_env == "production"
    assert settings.demo_mode is False
