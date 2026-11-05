"""run estimated spend

Revision ID: a7d41e9c3b52
Revises: 5c005589f6f7
Create Date: 2026-11-05 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7d41e9c3b52"
down_revision: str | Sequence[str] | None = "5c005589f6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("evaluation_runs") as batch_op:
        batch_op.add_column(sa.Column("estimated_spend_usd", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("evaluation_runs") as batch_op:
        batch_op.drop_column("estimated_spend_usd")
