"""
Module: models.py
Purpose: SQLAlchemy ORM models for every LLMWatch table.
WHY: One relational schema for SQLite and Postgres replaces the DynamoDB tables.
Every tenant-owned table carries workspace_id (even where it could be derived through
a parent) so each query can be scoped with a single WHERE clause, and deleting a
workspace cascades to everything it owns.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# WHY: Deterministic constraint names keep Alembic migrations stable and let SQLite
# batch migrations find constraints by name.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UTCDateTime(TypeDecorator[datetime]):
    """Stores UTC and always returns timezone-aware datetimes.

    WHY: SQLite has no timezone type and returns naive datetimes, which then compare
    wrongly with aware ones. Normalising here keeps both backends identical.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime; use datetime.now(UTC)")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


JSONType = JSON().with_variant(JSONB(), "postgresql")


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {datetime: UTCDateTime(), dict[str, Any]: JSONType}


def _id_column() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=new_id)


def _workspace_fk() -> Mapped[str]:
    return mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(default=utcnow, nullable=False)


# ── Tenancy and auth ──────────────────────────────────────


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = _id_column()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = _created_at()


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = _id_column()
    workspace_id: Mapped[str] = _workspace_fk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="owner", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = _id_column()
    workspace_id: Mapped[str] = _workspace_fk()
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # SHA-256 hex of the raw key; the raw key is never stored.
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = _created_at()


# ── Providers and models ──────────────────────────────────


class Provider(Base):
    __tablename__ = "providers"
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)

    id: Mapped[str] = _id_column()
    workspace_id: Mapped[str] = _workspace_fk()
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Preset type, e.g. "openai", "gemini", "ollama", "custom".
    preset: Mapped[str] = mapped_column(String(40), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    # Fernet token; never returned by the API.
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # True for providers seeded from environment variables at startup.
    managed_by_env: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow, onupdate=utcnow, nullable=False
    )


class Model(Base):
    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_id"),
        # At most one default model per workspace.
        Index(
            "uq_models_workspace_default",
            "workspace_id",
            unique=True,
            sqlite_where=text("is_default = 1"),
            postgresql_where=text("is_default"),
        ),
    )

    id: Mapped[str] = _id_column()
    workspace_id: Mapped[str] = _workspace_fk()
    provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )
    # The provider's own identifier, sent as `model` in API calls.
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supports_tools: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_vision: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    supports_reasoning: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    supports_json: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # USD per 1M tokens; NULL means unknown (cost is then reported as 0 and flagged).
    input_price_per_mtok: Mapped[float | None] = mapped_column(Float, nullable=True)
    output_price_per_mtok: Mapped[float | None] = mapped_column(Float, nullable=True)
    open_weights: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow, onupdate=utcnow, nullable=False
    )


# ── Observability ─────────────────────────────────────────


class LLMLog(Base):
    __tablename__ = "llm_logs"
    __table_args__ = (
        Index("ix_llm_logs_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = _id_column()
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = _created_at()
    # "chat", "agent" or "eval"
    source: Mapped[str] = mapped_column(String(20), default="chat", nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    api_key_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    model_ref_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )
    # Snapshots, so logs stay readable after a model or provider is deleted.
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_preview: Mapped[str] = mapped_column(Text, default="", nullable=False)
    response_preview: Mapped[str] = mapped_column(Text, default="", nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thinking_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class AgentTrace(Base):
    __tablename__ = "agent_traces"
    __table_args__ = (
        Index("ix_agent_traces_workspace_created", "workspace_id", "created_at"),
    )

    # The agent run id (also streamed to the client as run_id).
    id: Mapped[str] = _id_column()
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = _created_at()
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    model_ref_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    tools_enabled: Mapped[list[str]] = mapped_column(JSONType, default=list)
    tools_used: Mapped[list[str]] = mapped_column(JSONType, default=list)
    # "running", "success", "error" or "cancelled"
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    total_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    final_answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Ordered list of step events (same shape as the SSE events).
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)

    @property
    def success(self) -> bool:
        return self.status == "success"


# ── Evaluations ───────────────────────────────────────────


class EvalSuite(Base):
    __tablename__ = "eval_suites"
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)

    id: Mapped[str] = _id_column()
    workspace_id: Mapped[str] = _workspace_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    latest_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # use_alter: eval_runs references eval_suites too (dependency cycle).
    baseline_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "eval_runs.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_eval_suites_baseline_run_id_eval_runs",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow, onupdate=utcnow, nullable=False
    )


class EvalSuiteVersion(Base):
    """An immutable snapshot of a suite's prompt and cases; runs pin one."""

    __tablename__ = "eval_suite_versions"
    __table_args__ = (UniqueConstraint("suite_id", "version"),)

    id: Mapped[str] = _id_column()
    workspace_id: Mapped[str] = _workspace_fk()
    suite_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_suites.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Assertions applied to every case in addition to its own.
    default_assertions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONType, default=list
    )
    created_at: Mapped[datetime] = _created_at()


class EvalCase(Base):
    __tablename__ = "eval_cases"

    id: Mapped[str] = _id_column()
    workspace_id: Mapped[str] = _workspace_fk()
    suite_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("eval_suite_versions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # Stable identifier across versions, used to pair cases between runs.
    case_key: Mapped[str] = mapped_column(String(200), nullable=False)
    vars: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    assertions: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    tags: Mapped[list[str]] = mapped_column(JSONType, default=list)


class EvalRun(Base):
    __tablename__ = "eval_runs"
    __table_args__ = (Index("ix_eval_runs_suite_created", "suite_id", "created_at"),)

    id: Mapped[str] = _id_column()
    workspace_id: Mapped[str] = _workspace_fk()
    suite_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_suites.id", ondelete="CASCADE"), nullable=False
    )
    suite_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("eval_suite_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Runs launched together (one per variant) share a group id.
    group_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    label: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    # "pending", "running", "completed", "failed" or "cancelled"
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    model_ref_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )
    # {"model": ..., "provider": ..., "params": {...}} as resolved at launch.
    variant: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    repeats: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    concurrency: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    # Prices used to compute costs, frozen at launch for reproducibility.
    pricing_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mean_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pass_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class EvalResult(Base):
    __tablename__ = "eval_results"
    # One row per (case, repeat) per run: lets an interrupted run resume.
    __table_args__ = (UniqueConstraint("run_id", "case_id", "repeat_index"),)

    id: Mapped[str] = _id_column()
    workspace_id: Mapped[str] = _workspace_fk()
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_cases.id", ondelete="CASCADE"), nullable=False
    )
    repeat_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # [{"name", "type", "score", "passed", "reason"}, ...]
    evaluator_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONType, default=list
    )
    created_at: Mapped[datetime] = _created_at()


class ResponseCache(Base):
    """Content-addressed LLM responses, so re-running an eval is free.

    WHY: Scoped per workspace; a cross-tenant cache would let one workspace learn
    what another sent (cache hits are observable through latency and cost).
    """

    __tablename__ = "response_cache"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # sha256 of the canonical (model, params, messages) request.
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    response: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    hits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = _created_at()


TENANT_MODELS = (
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
)
