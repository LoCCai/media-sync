"""Add scoped creator observations, subscription aliases and auth fencing.

Revision ID: 0010_creator_profiles
Revises: 0009_subscription_removal
"""

from collections.abc import Sequence
from importlib import import_module

import sqlalchemy as sa
from alembic import op

revision: str = "0010_creator_profiles"
down_revision: str | None = "0009_subscription_removal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_KINDS = (
    "account-login",
    "asset-download",
    "emby-export",
    "media-server-probe",
    "media-server-scan",
    "pipeline-run",
    "scheduler-run",
)


def _kind_check(kinds: tuple[str, ...]) -> None:
    # Reuse the immutable migration's audited SQLite FK-preserving table copy.
    migration = import_module("media_sync.infrastructure.db.migrations.versions.0007_media_server_operations")
    migration._replace_kind_check(kinds)


def upgrade() -> None:
    _kind_check((*_LEGACY_KINDS, "creator-profile"))
    op.add_column(
        "accounts",
        sa.Column(
            "auth_revision",
            sa.BigInteger(),
            sa.CheckConstraint("auth_revision >= 0", name=op.f("ck_accounts_auth_revision_nonnegative")),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column("subscriptions", sa.Column("local_alias", sa.String(512), nullable=True))
    op.execute(
        sa.text(
            "UPDATE subscriptions SET local_alias = (SELECT authors.display_name FROM authors "
            "WHERE authors.id = subscriptions.author_id)"
        )
    )
    op.create_table(
        "creator_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("creator_remote_id", sa.String(255), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("latest_operation_id", sa.String(36), sa.ForeignKey("operations.id", ondelete="RESTRICT")),
        sa.Column("latest_frontend_generation", sa.String(36)),
        sa.Column("credential_snapshot_digest", sa.String(64)),
        sa.Column("nickname", sa.String(512)),
        sa.Column("canonical_homepage", sa.String(1024)),
        sa.Column("upstream_commit", sa.String(40)),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_success_operation_id", sa.String(36), sa.ForeignKey("operations.id", ondelete="RESTRICT")),
        sa.Column("avatar_png", sa.LargeBinary()),
        sa.Column("avatar_revision", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("avatar_profile_revision", sa.BigInteger()),
        sa.Column("avatar_observed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.UniqueConstraint("account_id", "platform", "creator_remote_id"),
        sa.CheckConstraint("platform IN ('bili', 'dy', 'ks', 'tieba', 'wb', 'xhs', 'zhihu')", name="platform"),
        sa.CheckConstraint("generation >= 0 AND revision >= 0 AND avatar_revision >= 0", name="revisions_nonnegative"),
        sa.CheckConstraint("avatar_png IS NULL OR length(avatar_png) <= 2097152", name="avatar_size"),
    )
    op.create_table(
        "creator_profile_lookups",
        sa.Column("operation_id", sa.String(36), sa.ForeignKey("operations.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column(
            "profile_id", sa.String(36), sa.ForeignKey("creator_profiles.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("frontend_generation", sa.String(36), nullable=False),
        sa.Column("credential_snapshot_digest", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("result_revision", sa.BigInteger()),
        sa.Column("error_code", sa.String(128)),
        sa.UniqueConstraint("profile_id", "generation"),
        sa.CheckConstraint("generation > 0", name="generation_positive"),
        sa.CheckConstraint("state IN ('pending', 'succeeded', 'failed')", name="state"),
    )


def downgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("creator_profiles_downgrade_requires_online_audit")
    connection = op.get_bind()
    for table in ("creator_profile_lookups", "creator_profiles"):
        if connection.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first() is not None:
            raise RuntimeError("creator_profile_history_prevents_downgrade")
    if connection.execute(sa.text("SELECT 1 FROM operations WHERE kind = 'creator-profile' LIMIT 1")).first():
        raise RuntimeError("creator_profile_history_prevents_downgrade")
    if connection.execute(
        sa.text(
            "SELECT 1 FROM subscriptions s JOIN authors a ON a.id = s.author_id "
            "WHERE s.local_alias IS NOT NULL AND s.local_alias <> a.display_name LIMIT 1"
        )
    ).first():
        raise RuntimeError("creator_profile_alias_prevents_downgrade")
    op.drop_table("creator_profile_lookups")
    op.drop_table("creator_profiles")
    op.drop_column("subscriptions", "local_alias")
    op.drop_column("accounts", "auth_revision")
    _kind_check(_LEGACY_KINDS)
