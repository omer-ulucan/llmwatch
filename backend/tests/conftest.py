"""
Shared pytest fixtures for the LLMWatch backend test suite.

WHY: Centralizing fixtures ensures consistent test setup and avoids
importing real Settings (which requires .env) — we monkeypatch config
before any application module is loaded.
"""

import os
import sys
import pytest

# ---------------------------------------------------------------------------
# 1. Ensure the backend package root is on sys.path so bare imports
#    like `from config import settings` work in tests just as they do
#    when running the application from the backend/ directory.
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# ---------------------------------------------------------------------------
# 2. Inject minimal env vars BEFORE any application module touches
#    pydantic-settings.  This avoids "field required" validation errors
#    when `config.Settings()` is instantiated at import time.
# ---------------------------------------------------------------------------
_TEST_ENV = {
    "AWS_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "DYNAMODB_TABLE_LOGS": "test-logs",
    "DYNAMODB_TABLE_USERS": "test-users",
    "DYNAMODB_TABLE_TRACES": "test-traces",
    "JWT_SECRET_KEY": "test-secret-key-for-jwt-do-not-use-in-prod",
    "JWT_ALGORITHM": "HS256",
    "JWT_EXPIRE_HOURS": "24",
    "GOOGLE_API_KEY": "fake-google-key",
    "QWEN_BASE_URL": "http://localhost:8000/v1",
    "QWEN_API_KEY": "fake-qwen-key",
    "MLFLOW_TRACKING_URI": "http://localhost:5000",
    "APP_ENV": "testing",
    "APP_VERSION": "0.0.0-test",
    "CORS_ORIGINS": "http://localhost:3000",
}

for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def jwt_secret():
    """Return the JWT secret used in tests."""
    return _TEST_ENV["JWT_SECRET_KEY"]


@pytest.fixture
def jwt_algorithm():
    """Return the JWT algorithm used in tests."""
    return _TEST_ENV["JWT_ALGORITHM"]
