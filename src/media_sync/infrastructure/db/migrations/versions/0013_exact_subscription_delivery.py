"""Add exact delivery operations and non-completeness scan observations.

Revision ID: 0013_exact_subscription_delivery
Revises: 0012_library_output_policy
"""

from collections.abc import Sequence
from importlib import import_module

import sqlalchemy as sa
from alembic import op

revision: str = "0013_exact_subscription_delivery"
down_revision: str | None = "0012_library_output_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
_PREVIOUS_KINDS = (
    "account-login",
    "account-cookie-login",
    "asset-download",
    "creator-profile",
    "emby-export",
    "media-server-probe",
    "media-server-scan",
    "pipeline-run",
    "scheduler-run",
)
_SQLITE_MAINTENANCE_ARGUMENT = "exclusive-maintenance"


def _lower_hex(column: str) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression}, '{character}', '')"
    return f"{expression} = ''"


def _replace(kinds: tuple[str, ...]) -> None:
    migration = import_module("media_sync.infrastructure.db.migrations.versions.0007_media_server_operations")
    migration._replace_kind_check(kinds)


def _sqlite_exclusive_maintenance_requested() -> bool:
    migration_context = op.get_context()
    environment_context = migration_context.environment_context
    if environment_context is None:
        return False
    values = [
        value
        for argument in environment_context.get_x_argument()
        for key, _, value in (argument.partition("="),)
        if key == _SQLITE_MAINTENANCE_ARGUMENT
    ]
    return values == ["true"]


def upgrade() -> None:
    _replace((*_PREVIOUS_KINDS, "subscription-delivery"))
    compact_generation = "replace(generation_id, '-', '')"
    op.create_table(
        "subscription_scan_progress",
        sa.Column(
            "subscription_id", sa.String(36), sa.ForeignKey("subscriptions.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("feed", sa.String(16), primary_key=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("upstream_sha", sa.String(40), nullable=False),
        sa.Column("generation_id", sa.String(36), nullable=False),
        sa.Column("checkpoint_revision", sa.BigInteger(), nullable=False),
        *(
            sa.Column(name, sa.BigInteger(), nullable=False, server_default="0")
            for name in ("unit_count", "item_count", "history_unit_count", "history_item_count")
        ),
        sa.Column("last_lane", sa.String(16), nullable=False),
        sa.Column("last_stop_reason", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_end_observed_at", sa.DateTime(timezone=True)),
        sa.Column("source_end_run_id", sa.String(36), sa.ForeignKey("sync_runs.id", ondelete="RESTRICT")),
        *(
            sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))
            for name in ("created_at", "updated_at")
        ),
        sa.CheckConstraint("feed IN ('answers', 'dynamics', 'notes', 'posts', 'threads', 'uploads')", name="feed"),
        sa.CheckConstraint("state IN ('scanning', 'source_end_observed', 'unproven')", name="state"),
        sa.CheckConstraint("contract_version IN (1, 2)", name="contract_version"),
        sa.CheckConstraint(f"length(upstream_sha) = 40 AND {_lower_hex('upstream_sha')}", name="upstream_sha"),
        sa.CheckConstraint(
            "length(generation_id) = 36 AND lower(generation_id) = generation_id "
            "AND substr(generation_id, 9, 1) = '-' AND substr(generation_id, 14, 1) = '-' "
            "AND substr(generation_id, 19, 1) = '-' AND substr(generation_id, 24, 1) = '-' "
            f"AND length({compact_generation}) = 32 AND {_lower_hex(compact_generation)}",
            name="generation_id",
        ),
        sa.CheckConstraint("last_lane IN ('head', 'history')", name="last_lane"),
        sa.CheckConstraint(
            "last_stop_reason IN ('head_boundary', 'item_limit', 'list_limit', 'page_end', "
            "'restarted', 'snapshot_saved', 'source_end')",
            name="stop_reason",
        ),
        *(
            sa.CheckConstraint(f"{name} >= 0 AND {name} <= 9007199254740991", name=f"{name}_range")
            for name in ("checkpoint_revision", "unit_count", "item_count", "history_unit_count", "history_item_count")
        ),
        sa.CheckConstraint(
            "history_unit_count <= unit_count AND history_item_count <= item_count", name="history_counts"
        ),
        sa.CheckConstraint(
            "(source_end_observed_at IS NULL AND source_end_run_id IS NULL) OR "
            "(source_end_observed_at IS NOT NULL AND source_end_run_id IS NOT NULL)",
            name="source_end_pair",
        ),
        sa.CheckConstraint("state != 'source_end_observed' OR source_end_run_id IS NOT NULL", name="source_end_state"),
    )


def downgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("exact_delivery_downgrade_requires_online_audit")
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("LOCK TABLE operations, subscription_scan_progress IN ACCESS EXCLUSIVE MODE"))
    elif connection.dialect.name == "sqlite":
        # SQLite's operations constraint replacement crosses autocommit
        # boundaries.  The flag is an operator attestation that every writer
        # has been stopped; it is deliberately not treated as a database lock.
        if not _sqlite_exclusive_maintenance_requested():
            raise RuntimeError("exact_delivery_sqlite_downgrade_requires_exclusive_maintenance")
    else:
        raise RuntimeError("exact_delivery_downgrade_dialect_unsupported")
    if connection.execute(sa.text("SELECT 1 FROM operations WHERE kind='subscription-delivery' LIMIT 1")).first():
        raise RuntimeError("exact_delivery_history_prevents_downgrade")
    if connection.execute(sa.text("SELECT 1 FROM subscription_scan_progress LIMIT 1")).first():
        raise RuntimeError("scan_progress_history_prevents_downgrade")
    _replace(_PREVIOUS_KINDS)
    op.drop_table("subscription_scan_progress")
