"""Add durable subscription scheduling identities and lane state.

Revision ID: 0004_scheduler_control_plane
Revises: 0003_media_download_emby
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_scheduler_control_plane"
down_revision: str | None = "0003_media_download_emby"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE_SYNC_STATUSES = (
    "claimed",
    "failed_retryable",
    "queued",
    "retry_wait",
    "running",
    "waiting_auth",
    "waiting_user",
)
_ACTIVE_SYNC_PREDICATE = (
    "job_type = 'sync.subscription' AND subscription_id IS NOT NULL AND status IN ("
    + ", ".join(f"'{status}'" for status in _ACTIVE_SYNC_STATUSES)
    + ")"
)
_PLATFORM_CHECK = "platform IN ('bili', 'dy', 'ks', 'tieba', 'wb', 'xhs', 'zhihu')"


def _asset_download_links(connection: sa.engine.Connection) -> tuple[tuple[str, str], ...]:
    """Capture external Job FKs that SQLite batch table replacement nulls."""

    rows = connection.execute(
        sa.text(
            "SELECT assets.id AS asset_id, assets.download_job_id AS job_id "
            "FROM assets JOIN jobs ON jobs.id = assets.download_job_id "
            "WHERE assets.download_job_id IS NOT NULL ORDER BY assets.id"
        )
    ).mappings()
    return tuple((str(row["asset_id"]), str(row["job_id"])) for row in rows)


def _restore_asset_download_links(
    connection: sa.engine.Connection,
    links: tuple[tuple[str, str], ...],
) -> None:
    if not links:
        return
    connection.execute(
        sa.text("UPDATE assets SET download_job_id = :job_id WHERE id = :asset_id"),
        [{"asset_id": asset_id, "job_id": job_id} for asset_id, job_id in links],
    )


def upgrade() -> None:
    with op.batch_alter_table("subscriptions") as batch_op:
        batch_op.add_column(sa.Column("schedule_revision", sa.Integer(), server_default="0", nullable=False))
        batch_op.create_check_constraint(
            op.f("ck_subscriptions_schedule_revision_nonnegative"),
            "schedule_revision >= 0",
        )

    connection = op.get_bind()
    asset_download_links = _asset_download_links(connection)
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("subscription_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("account_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("platform", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_check_constraint(
            op.f("ck_jobs_platform"),
            f"platform IS NULL OR {_PLATFORM_CHECK}",
        )
        batch_op.create_foreign_key(
            op.f("fk_jobs_subscription_id_subscriptions"),
            "subscriptions",
            ["subscription_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            op.f("fk_jobs_account_id_accounts"),
            "accounts",
            ["account_id"],
            ["id"],
            ondelete="CASCADE",
        )
    _restore_asset_download_links(connection, asset_download_links)

    op.create_index(
        "ix_jobs_scheduler_claim",
        "jobs",
        ["job_type", "status", "available_at", "priority", "scheduled_for"],
        unique=False,
    )
    op.create_index(
        "ix_jobs_subscription_scope",
        "jobs",
        ["subscription_id", "job_type", "status", "scheduled_for"],
        unique=False,
    )
    op.create_index(
        "ix_jobs_account_scope",
        "jobs",
        ["account_id", "job_type", "status", "lease_expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_jobs_platform_scope",
        "jobs",
        ["platform", "job_type", "status", "lease_expires_at"],
        unique=False,
    )
    op.create_index(
        "uq_jobs_active_sync_subscription",
        "jobs",
        ["subscription_id"],
        unique=True,
        sqlite_where=sa.text(_ACTIVE_SYNC_PREDICATE),
        postgresql_where=sa.text(_ACTIVE_SYNC_PREDICATE),
    )

    op.create_table(
        "scheduler_lanes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=True),
        sa.Column("max_concurrency", sa.Integer(), server_default="1", nullable=False),
        sa.Column("min_start_interval_seconds", sa.Integer(), server_default="5", nullable=False),
        sa.Column("failure_threshold", sa.Integer(), server_default="3", nullable=False),
        sa.Column("cooldown_seconds", sa.Integer(), server_default="900", nullable=False),
        sa.Column("next_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("circuit_state", sa.String(length=32), server_default="closed", nullable=False),
        sa.Column("circuit_open_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("half_open_job_id", sa.String(length=36), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "scope_type IN ('account', 'platform')",
            name=op.f("ck_scheduler_lanes_scope_type"),
        ),
        sa.CheckConstraint(
            "(scope_type = 'platform' AND account_id IS NULL) OR (scope_type = 'account' AND account_id IS NOT NULL)",
            name=op.f("ck_scheduler_lanes_scope_shape"),
        ),
        sa.CheckConstraint(_PLATFORM_CHECK, name=op.f("ck_scheduler_lanes_platform")),
        sa.CheckConstraint("max_concurrency >= 1", name=op.f("ck_scheduler_lanes_max_concurrency_positive")),
        sa.CheckConstraint(
            "min_start_interval_seconds >= 0",
            name=op.f("ck_scheduler_lanes_min_start_interval_seconds_nonnegative"),
        ),
        sa.CheckConstraint("failure_threshold >= 1", name=op.f("ck_scheduler_lanes_failure_threshold_positive")),
        sa.CheckConstraint("cooldown_seconds >= 1", name=op.f("ck_scheduler_lanes_cooldown_seconds_positive")),
        sa.CheckConstraint(
            "consecutive_failures >= 0",
            name=op.f("ck_scheduler_lanes_consecutive_failures_nonnegative"),
        ),
        sa.CheckConstraint(
            "circuit_state IN ('closed', 'half_open', 'open')",
            name=op.f("ck_scheduler_lanes_circuit_state"),
        ),
        sa.CheckConstraint("revision >= 0", name=op.f("ck_scheduler_lanes_revision_nonnegative")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_scheduler_lanes_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["half_open_job_id"],
            ["jobs.id"],
            name=op.f("fk_scheduler_lanes_half_open_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scheduler_lanes")),
    )
    op.create_index(
        "uq_scheduler_lanes_platform",
        "scheduler_lanes",
        ["platform"],
        unique=True,
        sqlite_where=sa.text("scope_type = 'platform'"),
        postgresql_where=sa.text("scope_type = 'platform'"),
    )
    op.create_index(
        "uq_scheduler_lanes_account",
        "scheduler_lanes",
        ["account_id"],
        unique=True,
        sqlite_where=sa.text("scope_type = 'account'"),
        postgresql_where=sa.text("scope_type = 'account'"),
    )
    op.create_index("ix_scheduler_lanes_account_id", "scheduler_lanes", ["account_id"], unique=False)
    op.create_index("ix_scheduler_lanes_half_open_job_id", "scheduler_lanes", ["half_open_job_id"], unique=False)


def downgrade() -> None:
    connection = op.get_bind()

    # Revision 0003 cannot express lane ownership or scheduled-cycle identity.
    # Remove both before dropping their columns so a later upgrade cannot reuse
    # an active/terminal natural key detached from its schedule revision.
    connection.execute(sa.text("DELETE FROM scheduler_lanes"))
    connection.execute(sa.text("DELETE FROM jobs WHERE job_type = 'sync.subscription'"))
    asset_download_links = _asset_download_links(connection)

    op.drop_index("ix_scheduler_lanes_half_open_job_id", table_name="scheduler_lanes")
    op.drop_index("ix_scheduler_lanes_account_id", table_name="scheduler_lanes")
    op.drop_index("uq_scheduler_lanes_account", table_name="scheduler_lanes")
    op.drop_index("uq_scheduler_lanes_platform", table_name="scheduler_lanes")
    op.drop_table("scheduler_lanes")

    op.drop_index("uq_jobs_active_sync_subscription", table_name="jobs")
    op.drop_index("ix_jobs_platform_scope", table_name="jobs")
    op.drop_index("ix_jobs_account_scope", table_name="jobs")
    op.drop_index("ix_jobs_subscription_scope", table_name="jobs")
    op.drop_index("ix_jobs_scheduler_claim", table_name="jobs")
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_constraint(op.f("fk_jobs_account_id_accounts"), type_="foreignkey")
        batch_op.drop_constraint(op.f("fk_jobs_subscription_id_subscriptions"), type_="foreignkey")
        batch_op.drop_constraint(op.f("ck_jobs_platform"), type_="check")
        batch_op.drop_column("scheduled_for")
        batch_op.drop_column("platform")
        batch_op.drop_column("account_id")
        batch_op.drop_column("subscription_id")
    _restore_asset_download_links(connection, asset_download_links)

    with op.batch_alter_table("subscriptions") as batch_op:
        batch_op.drop_constraint(op.f("ck_subscriptions_schedule_revision_nonnegative"), type_="check")
        batch_op.drop_column("schedule_revision")
