"""
Shared pytest fixtures for the LLMWatch backend test suite.

WHY: Centralizing fixtures ensures consistent test setup and avoids
importing real Settings (which requires .env) — we monkeypatch config
before any application module is loaded.
"""

import os

import pytest

# ---------------------------------------------------------------------------
# Inject minimal env vars BEFORE any application module touches
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
    "DYNAMODB_TABLE_API_KEYS": "test-api-keys",
    "SECRET_KEY": "test-secret-key-for-jwt-do-not-use-in-prod",
    "JWT_ALGORITHM": "HS256",
    "JWT_EXPIRE_HOURS": "24",
    "GOOGLE_API_KEY": "fake-google-key",
    "QWEN_BASE_URL": "http://localhost:8000/v1",
    "QWEN_API_KEY": "fake-qwen-key",
    "MLFLOW_TRACKING_URI": "http://localhost:5000",
    "APP_ENV": "testing",
    "APP_VERSION": "0.0.0-test",
    "CORS_ORIGINS": "http://localhost:3000",
    # Never touch a real database file from tests.
    "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
}

for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def jwt_secret():
    """Return the JWT secret used in tests."""
    return _TEST_ENV["SECRET_KEY"]


@pytest.fixture
def jwt_algorithm():
    """Return the JWT algorithm used in tests."""
    return _TEST_ENV["JWT_ALGORITHM"]


@pytest.fixture
async def db_engine():
    """A fresh in-memory SQLite database with the full schema."""
    from llmwatch.db.engine import create_engine
    from llmwatch.db.models import Base

    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async with async_sessionmaker(db_engine, expire_on_commit=False)() as session:
        yield session
