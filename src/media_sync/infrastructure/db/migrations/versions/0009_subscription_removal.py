"""Retain subscription history behind a reversible removal tombstone.

Revision ID: 0009_subscription_removal
Revises: 0008_playback_evidence
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_subscription_removal"
down_revision: str | None = "0008_playback_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("subscription_removal_downgrade_requires_online_audit")
    subscriptions = sa.table("subscriptions", sa.column("deleted_at", sa.DateTime(timezone=True)))
    removed = (
        op.get_bind()
        .execute(
            sa.select(sa.literal(1)).select_from(subscriptions).where(subscriptions.c.deleted_at.is_not(None)).limit(1)
        )
        .first()
    )
    if removed is not None:
        raise RuntimeError("removed_subscriptions_prevent_downgrade")
    op.drop_column("subscriptions", "deleted_at")
