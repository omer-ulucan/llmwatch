"""Add providers.api_key_hint (last characters of the key, for display).

Revision ID: 0002_provider_key_hint
Revises: 40b305ba3362
Create Date: 2026-10-25 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_provider_key_hint"
down_revision: str | None = "40b305ba3362"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("api_key_hint", sa.String(length=8), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.drop_column("api_key_hint")
