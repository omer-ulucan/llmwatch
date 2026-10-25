"""Initial schema: workspaces, auth, providers/models, logs, traces, evals.

Revision ID: 40b305ba3362
Revises:
Create Date: 2026-10-25 13:43:17.196399
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

import llmwatch.db.models

revision: str = "40b305ba3362"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
    )
    op.create_table(
        "eval_suites",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("latest_version", sa.Integer(), nullable=False),
        sa.Column("baseline_run_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_eval_suites_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_suites")),
        sa.UniqueConstraint(
            "workspace_id", "name", name=op.f("uq_eval_suites_workspace_id")
        ),
    )
    with op.batch_alter_table("eval_suites", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_eval_suites_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "providers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("preset", sa.String(length=40), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("managed_by_env", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_providers_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_providers")),
        sa.UniqueConstraint(
            "workspace_id", "name", name=op.f("uq_providers_workspace_id")
        ),
    )
    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_providers_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "response_cache",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column(
            "response",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_response_cache_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("workspace_id", "key", name=op.f("pk_response_cache")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_users_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_users_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column(
            "last_used_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_api_keys_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_api_keys_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_keys")),
        sa.UniqueConstraint("key_hash", name=op.f("uq_api_keys_key_hash")),
    )
    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_api_keys_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "eval_suite_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("suite_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column(
            "default_assertions",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["suite_id"],
            ["eval_suites.id"],
            name=op.f("fk_eval_suite_versions_suite_id_eval_suites"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_eval_suite_versions_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_suite_versions")),
        sa.UniqueConstraint(
            "suite_id", "version", name=op.f("uq_eval_suite_versions_suite_id")
        ),
    )
    with op.batch_alter_table("eval_suite_versions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_eval_suite_versions_workspace_id"),
            ["workspace_id"],
            unique=False,
        )

    op.create_table(
        "models",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("provider_id", sa.String(length=36), nullable=False),
        sa.Column("model_id", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("supports_tools", sa.Boolean(), nullable=False),
        sa.Column("supports_vision", sa.Boolean(), nullable=False),
        sa.Column("supports_reasoning", sa.Boolean(), nullable=False),
        sa.Column("supports_json", sa.Boolean(), nullable=False),
        sa.Column("input_price_per_mtok", sa.Float(), nullable=True),
        sa.Column("output_price_per_mtok", sa.Float(), nullable=True),
        sa.Column("open_weights", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "updated_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["providers.id"],
            name=op.f("fk_models_provider_id_providers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_models_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_models")),
        sa.UniqueConstraint(
            "provider_id", "model_id", name=op.f("uq_models_provider_id")
        ),
    )
    with op.batch_alter_table("models", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_models_workspace_id"), ["workspace_id"], unique=False
        )
        batch_op.create_index(
            "uq_models_workspace_default",
            ["workspace_id"],
            unique=True,
            sqlite_where=sa.text("is_default = 1"),
            postgresql_where=sa.text("is_default"),
        )

    op.create_table(
        "agent_traces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "finished_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=True
        ),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("model_ref_id", sa.String(length=36), nullable=True),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column(
            "tools_enabled",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column(
            "tools_used",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("total_steps", sa.Integer(), nullable=False),
        sa.Column("total_latency_ms", sa.Float(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("total_cost_usd", sa.Float(), nullable=False),
        sa.Column("final_answer", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "steps",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_ref_id"],
            ["models.id"],
            name=op.f("fk_agent_traces_model_ref_id_models"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_agent_traces_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_traces")),
    )
    with op.batch_alter_table("agent_traces", schema=None) as batch_op:
        batch_op.create_index(
            "ix_agent_traces_workspace_created",
            ["workspace_id", "created_at"],
            unique=False,
        )

    op.create_table(
        "eval_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("suite_version_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("case_key", sa.String(length=200), nullable=False),
        sa.Column(
            "vars",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("expected", sa.Text(), nullable=True),
        sa.Column(
            "assertions",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column(
            "tags",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["suite_version_id"],
            ["eval_suite_versions.id"],
            name=op.f("fk_eval_cases_suite_version_id_eval_suite_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_eval_cases_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_cases")),
    )
    with op.batch_alter_table("eval_cases", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_eval_cases_suite_version_id"),
            ["suite_version_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_eval_cases_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("suite_id", sa.String(length=36), nullable=False),
        sa.Column("suite_version_id", sa.String(length=36), nullable=False),
        sa.Column("group_id", sa.String(length=36), nullable=True),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("model_ref_id", sa.String(length=36), nullable=True),
        sa.Column(
            "variant",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("repeats", sa.Integer(), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column(
            "pricing_snapshot",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("completed_items", sa.Integer(), nullable=False),
        sa.Column("failed_items", sa.Integer(), nullable=False),
        sa.Column("mean_score", sa.Float(), nullable=True),
        sa.Column("pass_rate", sa.Float(), nullable=True),
        sa.Column("total_cost_usd", sa.Float(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "started_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "finished_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["model_ref_id"],
            ["models.id"],
            name=op.f("fk_eval_runs_model_ref_id_models"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["suite_id"],
            ["eval_suites.id"],
            name=op.f("fk_eval_runs_suite_id_eval_suites"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["suite_version_id"],
            ["eval_suite_versions.id"],
            name=op.f("fk_eval_runs_suite_version_id_eval_suite_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_eval_runs_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_runs")),
    )
    with op.batch_alter_table("eval_runs", schema=None) as batch_op:
        batch_op.create_index(
            "ix_eval_runs_suite_created", ["suite_id", "created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_eval_runs_workspace_id"), ["workspace_id"], unique=False
        )

    # eval_suites.baseline_run_id -> eval_runs is added after both tables exist
    # (the two tables reference each other).
    with op.batch_alter_table("eval_suites", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_eval_suites_baseline_run_id_eval_runs",
            "eval_runs",
            ["baseline_run_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "llm_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=False
        ),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("api_key_id", sa.String(length=36), nullable=True),
        sa.Column("model_ref_id", sa.String(length=36), nullable=True),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=True),
        sa.Column("prompt_preview", sa.Text(), nullable=False),
        sa.Column("response_preview", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("thinking_mode", sa.Boolean(), nullable=False),
        sa.Column("trace_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["model_ref_id"],
            ["models.id"],
            name=op.f("fk_llm_logs_model_ref_id_models"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_llm_logs_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_logs")),
    )
    with op.batch_alter_table("llm_logs", schema=None) as batch_op:
        batch_op.create_index(
            "ix_llm_logs_workspace_created",
            ["workspace_id", "created_at"],
            unique=False,
        )

    op.create_table(
        "eval_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("repeat_index", sa.Integer(), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("cached", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column(
            "evaluator_results",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at", llmwatch.db.models.UTCDateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["eval_cases.id"],
            name=op.f("fk_eval_results_case_id_eval_cases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["eval_runs.id"],
            name=op.f("fk_eval_results_run_id_eval_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_eval_results_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_results")),
        sa.UniqueConstraint(
            "run_id", "case_id", "repeat_index", name=op.f("uq_eval_results_run_id")
        ),
    )
    with op.batch_alter_table("eval_results", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_eval_results_workspace_id"), ["workspace_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("eval_suites", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_eval_suites_baseline_run_id_eval_runs", type_="foreignkey"
        )

    with op.batch_alter_table("eval_results", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_eval_results_workspace_id"))

    op.drop_table("eval_results")
    with op.batch_alter_table("llm_logs", schema=None) as batch_op:
        batch_op.drop_index("ix_llm_logs_workspace_created")

    op.drop_table("llm_logs")
    with op.batch_alter_table("eval_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_eval_runs_workspace_id"))
        batch_op.drop_index("ix_eval_runs_suite_created")

    op.drop_table("eval_runs")
    with op.batch_alter_table("eval_cases", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_eval_cases_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_eval_cases_suite_version_id"))

    op.drop_table("eval_cases")
    with op.batch_alter_table("agent_traces", schema=None) as batch_op:
        batch_op.drop_index("ix_agent_traces_workspace_created")

    op.drop_table("agent_traces")
    with op.batch_alter_table("models", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_models_workspace_default",
            sqlite_where=sa.text("is_default = 1"),
            postgresql_where=sa.text("is_default"),
        )
        batch_op.drop_index(batch_op.f("ix_models_workspace_id"))

    op.drop_table("models")
    with op.batch_alter_table("eval_suite_versions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_eval_suite_versions_workspace_id"))

    op.drop_table("eval_suite_versions")
    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_api_keys_workspace_id"))

    op.drop_table("api_keys")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_workspace_id"))

    op.drop_table("users")
    op.drop_table("response_cache")
    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_providers_workspace_id"))

    op.drop_table("providers")
    with op.batch_alter_table("eval_suites", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_eval_suites_workspace_id"))

    op.drop_table("eval_suites")
    op.drop_table("workspaces")
