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
    "SECRET_KEY": "test-secret-key-for-jwt-do-not-use-in-prod",
    "JWT_ALGORITHM": "HS256",
    "JWT_EXPIRE_HOURS": "24",
    "MLFLOW_TRACKING_URI": "http://localhost:5000",
    "APP_ENV": "testing",
    "APP_VERSION": "0.0.0-test",
    "CORS_ORIGINS": "http://localhost:3000",
    # No provider env vars: tests configure providers explicitly.
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
async def db_engine(tmp_path):
    """A fresh SQLite database file with the full schema.

    WHY: A file (WAL, real connection pool) like production, not one shared
    in-memory connection: concurrent sessions (eval runner workers) would interleave
    their transactions on a single connection and lose writes.
    """
    from llmwatch.db.engine import create_engine
    from llmwatch.db.models import Base

    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async with async_sessionmaker(db_engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
async def app_db(db_engine, monkeypatch):
    """Points the app's engine and sessionmaker at the in-memory test database."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import llmwatch.auth.jwt_handler as jwt_handler
    import llmwatch.db.engine as engine_module

    # WHY: Production uses 12 bcrypt rounds (asserted in test_jwt_handler.py); API
    # tests create many accounts, and 4 rounds keeps them fast.
    monkeypatch.setattr(jwt_handler, "BCRYPT_ROUNDS", 4)
    monkeypatch.setattr(engine_module, "_engine", db_engine)
    monkeypatch.setattr(
        engine_module,
        "_sessionmaker",
        async_sessionmaker(db_engine, expire_on_commit=False),
    )
    yield db_engine


@pytest.fixture
async def client(app_db):
    """An HTTP client for the app, on the test's event loop, from a public IP.

    WHY: httpx's ASGITransport runs the app in-process on the same loop as the test,
    so the in-memory database connection is never shared across event loops.
    Lifespan (migrations) doesn't run; app_db already has the schema.
    """
    import httpx

    from llmwatch.main import app
    from llmwatch.rate_limit import limiter

    limiter.reset()
    transport = httpx.ASGITransport(app=app, client=("203.0.113.10", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    limiter.reset()


class Account:
    """A registered user plus a valid session token."""

    def __init__(self, user, workspace, password: str, token: str):
        self.user = user
        self.workspace = workspace
        self.password = password
        self.token = token

    @property
    def user_id(self) -> str:
        return self.user.id

    @property
    def workspace_id(self) -> str:
        return self.workspace.id

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest.fixture
def make_account(app_db):
    """Factory: make_account(email=..., workspace=..., role=..., workspace_id=...)."""
    import itertools

    counter = itertools.count(1)

    async def _make(
        email: str | None = None,
        workspace: str = "Acme",
        password: str = "correct-horse-battery",
        role: str = "owner",
        workspace_id: str | None = None,
    ) -> Account:
        from llmwatch.auth.jwt_handler import create_access_token, get_password_hash
        from llmwatch.db.engine import get_sessionmaker
        from llmwatch.db.models import User, Workspace
        from llmwatch.services import accounts

        email = email or f"user{next(counter)}@example.com"
        async with get_sessionmaker()() as session:
            if workspace_id is None:
                ws, user = await accounts.register(session, email, password, workspace)
                if role != "owner":
                    user.role = role
                    await session.commit()
            else:
                ws = await session.get(Workspace, workspace_id)
                user = User(
                    workspace_id=workspace_id,
                    email=email,
                    password_hash=get_password_hash(password),
                    role=role,
                )
                session.add(user)
                await session.commit()
        token = create_access_token({"sub": user.id, "workspace_id": ws.id})
        return Account(user, ws, password, token)

    return _make


@pytest.fixture
def fake_llm(monkeypatch):
    """Every provider client talks to one fake OpenAI-compatible server.

    fake_llm.configs records the ProviderConfig each client was built with.
    """
    from llmwatch.llm import LLMClient
    from llmwatch.providers import service
    from tests.fake_llm import FakeProvider

    fake = FakeProvider(models=["fake-model"])
    fake.configs = []

    def make_client(config):
        fake.configs.append(config)
        return LLMClient(config, http_client=fake.http_client())

    monkeypatch.setattr(service, "make_client", make_client)
    return fake


@pytest.fixture
def add_model(app_db):
    """Factory: add_model(account, model_id=..., preset=..., ...) -> Model row."""

    async def _add(
        account,
        model_id: str = "fake-model",
        *,
        preset: str = "openai",
        provider_name: str = "Fake",
        input_price: float | None = 1.0,
        output_price: float | None = 2.0,
        supports_reasoning: bool = False,
        supports_tools: bool = True,
        is_default: bool = False,
    ):
        from sqlalchemy import select

        from llmwatch.db.engine import get_sessionmaker
        from llmwatch.db.models import Model, Provider

        async with get_sessionmaker()() as session:
            provider = (
                await session.execute(
                    select(Provider).where(
                        Provider.workspace_id == account.workspace_id,
                        Provider.name == provider_name,
                    )
                )
            ).scalar_one_or_none()
            if provider is None:
                provider = Provider(
                    workspace_id=account.workspace_id,
                    name=provider_name,
                    preset=preset,
                    base_url="http://fake.local/v1",
                )
                session.add(provider)
                await session.flush()
            model = Model(
                workspace_id=account.workspace_id,
                provider_id=provider.id,
                model_id=model_id,
                display_name=model_id,
                input_price_per_mtok=input_price,
                output_price_per_mtok=output_price,
                supports_reasoning=supports_reasoning,
                supports_tools=supports_tools,
                is_default=is_default,
            )
            session.add(model)
            await session.commit()
            return model

    return _add
