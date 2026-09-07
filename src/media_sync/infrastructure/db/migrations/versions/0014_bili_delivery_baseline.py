"""Add delivery-qualified Bili baseline state and exact Run contents.

Revision ID: 0014_bili_delivery_baseline
Revises: 0013_exact_subscription_delivery
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_bili_delivery_baseline"
down_revision: str | None = "0013_exact_subscription_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
_SQLITE_MAINTENANCE_ARGUMENT = "exclusive-maintenance"
_COUNTERS = (
    "checkpoint_revision",
    "schedule_revision",
    "batch_count",
    "content_observation_count",
    "backfill_batch_count",
    "reconciliation_batch_count",
    "incremental_batch_count",
    "partial_batch_count",
    "failed_content_count",
)


def _lower_hex(column: str) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression}, '{character}', '')"
    return f"{expression} = ''"


def _uuid(column: str) -> str:
    compact = f"replace({column}, '-', '')"
    return (
        f"length({column}) = 36 AND lower({column}) = {column} "
        f"AND substr({column}, 9, 1) = '-' AND substr({column}, 14, 1) = '-' "
        f"AND substr({column}, 19, 1) = '-' AND substr({column}, 24, 1) = '-' "
        f"AND length({compact}) = 32 AND {_lower_hex(compact)}"
    )


def _sha256(column: str) -> str:
    return f"length({column}) = 64 AND lower({column}) = {column} AND {_lower_hex(column)}"


def _sqlite_exclusive_maintenance_requested() -> bool:
    context = op.get_context().environment_context
    if context is None:
        return False
    values = [
        value
        for argument in context.get_x_argument()
        for key, _, value in (argument.partition("="),)
        if key == _SQLITE_MAINTENANCE_ARGUMENT
    ]
    return values == ["true"]


def upgrade() -> None:
    op.create_table(
        "sync_run_contents",
        sa.Column("run_id", sa.String(36), sa.ForeignKey("sync_runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("content_id", sa.String(36), sa.ForeignKey("contents.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column(
            "subscription_id",
            sa.String(36),
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("asset_count", sa.Integer(), nullable=False),
        sa.Column(
            "observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.UniqueConstraint("run_id", "position"),
        sa.CheckConstraint("position >= 0 AND position < 30", name="position_range"),
        sa.CheckConstraint("asset_count >= 0 AND asset_count <= 1000", name="asset_count_range"),
    )
    op.create_index(
        "ix_sync_run_contents_subscription_content",
        "sync_run_contents",
        ["subscription_id", "content_id"],
    )
    op.create_table(
        "bili_subscription_progress",
        sa.Column(
            "subscription_id",
            sa.String(36),
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("phase", sa.String(32), nullable=False, server_default="backfill"),
        sa.Column("generation_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("auth_revision", sa.BigInteger(), nullable=False),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("authors.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("author_fingerprint_sha256", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False, server_default="uploads"),
        sa.Column("policy_fingerprint_sha256", sa.String(64), nullable=False),
        sa.Column("upstream_sha", sa.String(40), nullable=False),
        sa.Column("checkpoint_revision", sa.BigInteger(), nullable=False),
        sa.Column("schedule_revision", sa.BigInteger(), nullable=False),
        *(sa.Column(column, sa.BigInteger(), nullable=False, server_default="0") for column in _COUNTERS[2:]),
        sa.Column("last_lane", sa.String(16)),
        sa.Column("last_stop_reason", sa.String(32)),
        sa.Column("last_sync_job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="RESTRICT")),
        sa.Column("last_run_id", sa.String(36), sa.ForeignKey("sync_runs.id", ondelete="RESTRICT")),
        sa.Column("last_pipeline_job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="RESTRICT")),
        sa.Column("last_delivery_at", sa.DateTime(timezone=True)),
        sa.Column("source_end_observed_at", sa.DateTime(timezone=True)),
        sa.Column("source_end_run_id", sa.String(36), sa.ForeignKey("sync_runs.id", ondelete="RESTRICT")),
        sa.Column("source_end_boundary_sha256", sa.String(64)),
        sa.Column("reconciled_at", sa.DateTime(timezone=True)),
        sa.Column("reconciliation_run_id", sa.String(36), sa.ForeignKey("sync_runs.id", ondelete="RESTRICT")),
        sa.Column("baseline_snapshot_at", sa.DateTime(timezone=True)),
        sa.Column("next_eligible_at", sa.DateTime(timezone=True)),
        sa.Column("blocked_code", sa.String(128)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.CheckConstraint("schema_version = 1", name="schema_version"),
        sa.CheckConstraint("phase IN ('backfill', 'blocked', 'incremental', 'reconciling')", name="phase"),
        sa.CheckConstraint(_uuid("generation_id"), name="generation_id"),
        sa.CheckConstraint("auth_revision >= 0", name="auth_revision_nonnegative"),
        sa.CheckConstraint("scope = 'uploads'", name="scope"),
        sa.CheckConstraint(_sha256("author_fingerprint_sha256"), name="author_fingerprint"),
        sa.CheckConstraint(_sha256("policy_fingerprint_sha256"), name="policy_fingerprint"),
        sa.CheckConstraint(f"length(upstream_sha) = 40 AND {_lower_hex('upstream_sha')}", name="upstream_sha"),
        sa.CheckConstraint(
            f"source_end_boundary_sha256 IS NULL OR {_sha256('source_end_boundary_sha256')}",
            name="source_end_boundary",
        ),
        *(
            sa.CheckConstraint(f"{column} >= 0 AND {column} <= 9007199254740991", name=f"{column}_range")
            for column in _COUNTERS
        ),
        sa.CheckConstraint(
            "backfill_batch_count + reconciliation_batch_count + incremental_batch_count = batch_count",
            name="phase_batch_counts",
        ),
        sa.CheckConstraint("partial_batch_count <= batch_count", name="partial_batch_count"),
        sa.CheckConstraint("last_lane IS NULL OR last_lane IN ('head', 'history')", name="last_lane"),
        sa.CheckConstraint(
            "last_stop_reason IS NULL OR last_stop_reason IN "
            "('head_boundary', 'item_limit', 'list_limit', 'page_end', 'restarted', 'snapshot_saved', 'source_end')",
            name="last_stop_reason",
        ),
        sa.CheckConstraint(
            "(last_sync_job_id IS NULL AND last_run_id IS NULL AND last_pipeline_job_id IS NULL "
            "AND last_delivery_at IS NULL) OR "
            "(last_sync_job_id IS NOT NULL AND last_run_id IS NOT NULL AND last_pipeline_job_id IS NOT NULL "
            "AND last_delivery_at IS NOT NULL)",
            name="last_delivery_evidence",
        ),
        sa.CheckConstraint(
            "(source_end_observed_at IS NULL AND source_end_run_id IS NULL "
            "AND source_end_boundary_sha256 IS NULL) OR "
            "(source_end_observed_at IS NOT NULL AND source_end_run_id IS NOT NULL "
            "AND source_end_boundary_sha256 IS NOT NULL)",
            name="source_end_evidence",
        ),
        sa.CheckConstraint(
            "(reconciled_at IS NULL AND reconciliation_run_id IS NULL AND baseline_snapshot_at IS NULL) OR "
            "(reconciled_at IS NOT NULL AND reconciliation_run_id IS NOT NULL "
            "AND baseline_snapshot_at IS NOT NULL)",
            name="reconciliation_evidence",
        ),
        sa.CheckConstraint(
            "phase != 'incremental' OR baseline_snapshot_at IS NOT NULL",
            name="incremental_requires_snapshot",
        ),
        sa.CheckConstraint(
            "(phase = 'blocked' AND blocked_code IS NOT NULL) OR (phase != 'blocked' AND blocked_code IS NULL)",
            name="blocked_code",
        ),
    )


def downgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("bili_delivery_downgrade_requires_online_audit")
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("LOCK TABLE bili_subscription_progress, sync_run_contents IN ACCESS EXCLUSIVE MODE"))
    elif connection.dialect.name == "sqlite" and not _sqlite_exclusive_maintenance_requested():
        raise RuntimeError("bili_delivery_sqlite_downgrade_requires_exclusive_maintenance")
    for table in ("bili_subscription_progress", "sync_run_contents"):
        if connection.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError("bili_delivery_history_prevents_downgrade")
    op.drop_table("bili_subscription_progress")
    op.drop_index("ix_sync_run_contents_subscription_content", table_name="sync_run_contents")
    op.drop_table("sync_run_contents")
