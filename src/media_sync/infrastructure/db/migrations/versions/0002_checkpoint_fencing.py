"""Add optimistic subscription checkpoint fencing.

Revision ID: 0002_checkpoint
Revises: 0001_core
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_checkpoint"
down_revision: str | None = "0001_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("subscriptions") as batch_op:
        batch_op.add_column(sa.Column("checkpoint_revision", sa.Integer(), server_default="0", nullable=False))
        batch_op.create_check_constraint(
            op.f("ck_subscriptions_checkpoint_revision_nonnegative"),
            "checkpoint_revision >= 0",
        )

    with op.batch_alter_table("sync_runs") as batch_op:
        batch_op.add_column(sa.Column("checkpoint_revision_before", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("checkpoint_revision_after", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            op.f("ck_sync_runs_checkpoint_revision_before_nonnegative"),
            "checkpoint_revision_before IS NULL OR checkpoint_revision_before >= 0",
        )
        batch_op.create_check_constraint(
            op.f("ck_sync_runs_checkpoint_revision_after_nonnegative"),
            "checkpoint_revision_after IS NULL OR checkpoint_revision_after >= 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("sync_runs") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_sync_runs_checkpoint_revision_after_nonnegative"),
            type_="check",
        )
        batch_op.drop_constraint(
            op.f("ck_sync_runs_checkpoint_revision_before_nonnegative"),
            type_="check",
        )
        batch_op.drop_column("checkpoint_revision_after")
        batch_op.drop_column("checkpoint_revision_before")

    with op.batch_alter_table("subscriptions") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_subscriptions_checkpoint_revision_nonnegative"),
            type_="check",
        )
        batch_op.drop_column("checkpoint_revision")
