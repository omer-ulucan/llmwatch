"""
Tests for the database layer: schema, SQLite pragmas, workspace scoping, migrations.
"""

import sqlite3
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from llmwatch.db.engine import create_engine
from llmwatch.db.models import (
    AgentTrace,
    ApiKey,
    Base,
    EvalCase,
    EvalResult,
    EvalRun,
    EvalSuite,
    EvalSuiteVersion,
    LLMLog,
    Model,
    Provider,
    ResponseCache,
    User,
    Workspace,
)
from llmwatch.db.repository import WorkspaceRepository


class ProviderRepo(WorkspaceRepository[Provider]):
    model = Provider


async def _workspace(session, name="acme") -> Workspace:
    ws = Workspace(name=name)
    session.add(ws)
    await session.flush()
    return ws


async def _populate(session, ws: Workspace) -> None:
    """One row in every tenant table, all owned by `ws`."""
    user = User(workspace_id=ws.id, email=f"{ws.name}@example.com", password_hash="x")
    provider = Provider(
        workspace_id=ws.id, name="local", preset="ollama", base_url="http://o/v1"
    )
    session.add_all([user, provider])
    await session.flush()
    model = Model(
        workspace_id=ws.id,
        provider_id=provider.id,
        model_id="llama3",
        display_name="Llama 3",
    )
    session.add_all(
        [
            model,
            ApiKey(
                workspace_id=ws.id,
                user_id=user.id,
                name="ci",
                key_hash=f"hash-{ws.name}",
                prefix="lw_x",
            ),
            LLMLog(workspace_id=ws.id, model_name="llama3", latency_ms=12.5),
            AgentTrace(workspace_id=ws.id, model_name="llama3", prompt="hi"),
            ResponseCache(workspace_id=ws.id, key="k" * 64, response={"content": "x"}),
        ]
    )
    suite = EvalSuite(workspace_id=ws.id, name="suite")
    session.add(suite)
    await session.flush()
    version = EvalSuiteVersion(
        workspace_id=ws.id, suite_id=suite.id, version=1, prompt_template="{{q}}"
    )
    session.add(version)
    await session.flush()
    case = EvalCase(
        workspace_id=ws.id,
        suite_version_id=version.id,
        position=0,
        case_key="c1",
        vars={"q": "2+2"},
    )
    run = EvalRun(workspace_id=ws.id, suite_id=suite.id, suite_version_id=version.id)
    session.add_all([case, run])
    await session.flush()
    session.add(
        EvalResult(workspace_id=ws.id, run_id=run.id, case_id=case.id, score=1.0)
    )
    suite.baseline_run_id = run.id
    await session.flush()


TENANT_TABLES = [
    User,
    ApiKey,
    Provider,
    Model,
    LLMLog,
    AgentTrace,
    EvalSuite,
    EvalSuiteVersion,
    EvalCase,
    EvalRun,
    EvalResult,
    ResponseCache,
]


async def _count(session, model, ws_id) -> int:
    stmt = select(func.count()).select_from(model).where(model.workspace_id == ws_id)
    return (await session.execute(stmt)).scalar_one()


# ── Schema and constraints ──────────────────────────────────


async def test_every_table_accepts_a_row(db_session):
    ws = await _workspace(db_session)
    await _populate(db_session, ws)
    await db_session.commit()
    for model in TENANT_TABLES:
        assert await _count(db_session, model, ws.id) == 1, model.__name__


async def test_foreign_keys_are_enforced(db_session):
    db_session.add(User(workspace_id="missing", email="a@b.c", password_hash="x"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_deleting_a_workspace_cascades_only_to_its_rows(db_session):
    acme = await _workspace(db_session, "acme")
    other = await _workspace(db_session, "other")
    await _populate(db_session, acme)
    await _populate(db_session, other)
    await db_session.commit()

    await db_session.execute(delete(Workspace).where(Workspace.id == acme.id))
    await db_session.commit()

    for model in TENANT_TABLES:
        assert await _count(db_session, model, acme.id) == 0, model.__name__
        assert await _count(db_session, model, other.id) == 1, model.__name__


async def test_only_one_default_model_per_workspace(db_session):
    acme = await _workspace(db_session, "acme")
    other = await _workspace(db_session, "other")
    providers = {}
    for ws in (acme, other):
        providers[ws.id] = Provider(
            workspace_id=ws.id, name="p", preset="openai", base_url="https://x/v1"
        )
        db_session.add(providers[ws.id])
    await db_session.flush()

    def default_model(ws, model_id):
        return Model(
            workspace_id=ws.id,
            provider_id=providers[ws.id].id,
            model_id=model_id,
            display_name=model_id,
            is_default=True,
        )

    db_session.add_all([default_model(acme, "a"), default_model(other, "b")])
    await db_session.flush()  # one default in each workspace is fine

    db_session.add(default_model(acme, "c"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_datetimes_round_trip_as_utc_aware(db_session):
    ws = await _workspace(db_session)
    stamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    log = LLMLog(workspace_id=ws.id, model_name="m", created_at=stamp)
    db_session.add(log)
    await db_session.commit()
    db_session.expunge_all()

    loaded = (await db_session.execute(select(LLMLog))).scalar_one()
    assert loaded.created_at == stamp
    assert loaded.created_at.tzinfo is not None


async def test_naive_datetimes_are_rejected(db_session):
    ws = await _workspace(db_session)
    db_session.add(
        LLMLog(workspace_id=ws.id, model_name="m", created_at=datetime(2026, 1, 1))
    )
    with pytest.raises(StatementError):
        await db_session.flush()


async def test_json_columns_round_trip(db_session):
    ws = await _workspace(db_session)
    steps = [{"event_type": "thinking", "latency_ms": 12.5, "nested": {"a": [1, 2]}}]
    db_session.add(
        AgentTrace(workspace_id=ws.id, model_name="m", prompt="p", steps=steps)
    )
    await db_session.commit()
    db_session.expunge_all()
    loaded = (await db_session.execute(select(AgentTrace))).scalar_one()
    assert loaded.steps == steps


# ── SQLite pragmas ──────────────────────────────────────────


async def test_file_database_uses_wal_and_foreign_keys(tmp_path):
    db_file = tmp_path / "nested" / "llmwatch.db"
    engine = create_engine(f"sqlite+aiosqlite:///{db_file}")
    try:
        async with engine.connect() as conn:
            journal = (await conn.execute(text("PRAGMA journal_mode"))).scalar()
            fks = (await conn.execute(text("PRAGMA foreign_keys"))).scalar()
            busy = (await conn.execute(text("PRAGMA busy_timeout"))).scalar()
    finally:
        await engine.dispose()
    assert db_file.parent.is_dir()  # created on demand
    assert journal == "wal"
    assert fks == 1
    assert busy == 5000


def test_importing_engine_module_does_not_create_an_engine():
    import llmwatch.db.engine as engine_module

    # Lazily created on first use, not at import.
    assert engine_module._engine is None or engine_module._engine.url.database in (
        None,
        ":memory:",
    )


# ── Workspace scoping ───────────────────────────────────────


async def test_repository_only_sees_its_own_workspace(db_session):
    acme = await _workspace(db_session, "acme")
    other = await _workspace(db_session, "other")
    theirs = Provider(
        workspace_id=other.id, name="theirs", preset="openai", base_url="https://x"
    )
    db_session.add(theirs)
    repo = ProviderRepo(db_session, acme.id)
    mine = repo.add(Provider(name="mine", preset="ollama", base_url="http://o"))
    await db_session.flush()

    assert mine.workspace_id == acme.id
    assert await repo.get(mine.id) is mine
    assert await repo.get(theirs.id) is None
    assert [p.name for p in await repo.list()] == ["mine"]
    assert await repo.count() == 1
    assert await ProviderRepo(db_session, other.id).count() == 1


async def test_repository_refuses_foreign_objects(db_session):
    acme = await _workspace(db_session, "acme")
    other = await _workspace(db_session, "other")
    theirs = Provider(
        workspace_id=other.id, name="theirs", preset="openai", base_url="https://x"
    )
    db_session.add(theirs)
    await db_session.flush()
    repo = ProviderRepo(db_session, acme.id)

    with pytest.raises(ValueError):
        repo.add(
            Provider(workspace_id=other.id, name="x", preset="o", base_url="http://x")
        )
    with pytest.raises(ValueError):
        await repo.delete(theirs)


async def test_repository_bulk_delete_is_scoped(db_session):
    acme = await _workspace(db_session, "acme")
    other = await _workspace(db_session, "other")
    for ws in (acme, other):
        db_session.add(
            Provider(workspace_id=ws.id, name="p", preset="o", base_url="http://x")
        )
    await db_session.flush()

    deleted = await ProviderRepo(db_session, acme.id).delete_where()

    assert deleted == 1
    assert await ProviderRepo(db_session, other.id).count() == 1


def test_repository_requires_a_workspace(db_session):
    with pytest.raises(ValueError):
        ProviderRepo(db_session, "")


# ── Migrations ──────────────────────────────────────────────
# Sync tests on purpose: Alembic's env runs its own event loop.


EXPECTED_TABLES = {table for table in Base.metadata.tables}


def _tables(db_file) -> set[str]:
    with sqlite3.connect(db_file) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {r[0] for r in rows} - {"sqlite_sequence"}


def test_migrations_upgrade_and_downgrade(tmp_path):
    from llmwatch.db.migrate import downgrade, upgrade

    db_file = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{db_file}"

    upgrade(url)
    assert _tables(db_file) == EXPECTED_TABLES | {"alembic_version"}

    downgrade(url, "base")
    assert _tables(db_file) == {"alembic_version"}

    upgrade(url)  # and back up again
    assert _tables(db_file) == EXPECTED_TABLES | {"alembic_version"}


def test_migrations_match_the_models(tmp_path):
    """Autogenerate against a migrated database must find nothing to change."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from llmwatch.db.migrate import upgrade

    db_file = tmp_path / "m.db"
    upgrade(f"sqlite+aiosqlite:///{db_file}")

    engine = create_sync_engine(f"sqlite:///{db_file}")
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, Base.metadata)
    engine.dispose()
    assert diff == []


def test_app_startup_migrates_a_file_database(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from llmwatch.config import settings
    from llmwatch.main import app

    db_file = tmp_path / "startup.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_file}")
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
    assert EXPECTED_TABLES <= _tables(db_file)


def test_app_startup_can_skip_migrations(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from llmwatch.config import settings
    from llmwatch.main import app

    db_file = tmp_path / "skip.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_file}")
    monkeypatch.setattr(settings, "auto_migrate", False)
    with TestClient(app):
        pass
    assert not db_file.exists()
