"""Create the core persistence schema.

Revision ID: 0001_core
Revises:
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_core"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM_CHECK = "platform IN ('bili', 'dy', 'ks', 'tieba', 'wb', 'xhs', 'zhihu')"


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
    )


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("adapter", sa.String(length=128), server_default="native", nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("login_method", sa.String(length=32), nullable=True),
        sa.Column("credential_ref", sa.String(length=512), nullable=True),
        sa.Column("profile_path", sa.Text(), nullable=True),
        sa.Column("auth_status", sa.String(length=32), server_default="unknown", nullable=False),
        sa.Column("auth_updated_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "auth_status IN ('authenticated', 'authenticating', 'expired', 'failed', 'required', 'unknown')",
            name=op.f("ck_accounts_auth_status"),
        ),
        sa.CheckConstraint(
            "login_method IS NULL OR login_method IN ('cookie', 'phone', 'qr', 'saved_session')",
            name=op.f("ck_accounts_login_method"),
        ),
        sa.CheckConstraint(PLATFORM_CHECK, name=op.f("ck_accounts_platform")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
        sa.UniqueConstraint("platform", "display_name", name=op.f("uq_accounts_platform_display_name")),
    )
    op.create_index("ix_accounts_platform_auth_status", "accounts", ["platform", "auth_status"], unique=False)

    op.create_table(
        "authors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("remote_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=512), nullable=False),
        sa.Column("handle", sa.String(length=255), nullable=True),
        sa.Column("profile_url", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("raw", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(PLATFORM_CHECK, name=op.f("ck_authors_platform")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_authors")),
        sa.UniqueConstraint("platform", "remote_id", name=op.f("uq_authors_platform_remote_id")),
    )
    op.create_index("ix_authors_platform_handle", "authors", ["platform", "handle"], unique=False)

    op.create_table(
        "login_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("challenge_kind", sa.String(length=64), nullable=True),
        sa.Column("public_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "method IN ('cookie', 'phone', 'qr', 'saved_session')",
            name=op.f("ck_login_sessions_method"),
        ),
        sa.CheckConstraint(
            "status IN ('cancelled', 'expired', 'failed', 'pending', 'succeeded', 'waiting_user')",
            name=op.f("ck_login_sessions_status"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_login_sessions_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_sessions")),
    )
    op.create_index("ix_login_sessions_account_status", "login_sessions", ["account_id", "status"], unique=False)
    op.create_index("ix_login_sessions_expires_at", "login_sessions", ["expires_at"], unique=False)

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("author_id", sa.String(length=36), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), server_default="21600", nullable=False),
        sa.Column("max_items", sa.Integer(), server_default="30", nullable=False),
        sa.Column("cursor", sa.JSON(), nullable=True),
        sa.Column("cursor_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("backfill_cursor", sa.JSON(), nullable=True),
        sa.Column("policy", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("watermarked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("watermark_remote_ids", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("consecutive_failures >= 0", name=op.f("ck_subscriptions_consecutive_failures_nonnegative")),
        sa.CheckConstraint("interval_seconds >= 60", name=op.f("ck_subscriptions_interval_seconds_minimum")),
        sa.CheckConstraint("max_items >= 1", name=op.f("ck_subscriptions_max_items_positive")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_subscriptions_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["authors.id"],
            name=op.f("fk_subscriptions_author_id_authors"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriptions")),
        sa.UniqueConstraint("account_id", "author_id", name=op.f("uq_subscriptions_account_id_author_id")),
    )
    op.create_index("ix_subscriptions_due", "subscriptions", ["enabled", "next_run_at"], unique=False)

    op.create_table(
        "contents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("author_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("remote_type", sa.String(length=64), server_default="content", nullable=False),
        sa.Column("remote_id", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remote_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metrics", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("raw", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("metadata_hash", sa.String(length=64), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tombstoned_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "kind IN ('article', 'audio', 'dynamic', 'gallery', 'image', 'mixed', 'text', 'video')",
            name=op.f("ck_contents_kind"),
        ),
        sa.CheckConstraint(PLATFORM_CHECK, name=op.f("ck_contents_platform")),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["authors.id"],
            name=op.f("fk_contents_author_id_authors"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contents")),
        sa.UniqueConstraint(
            "platform",
            "remote_type",
            "remote_id",
            name=op.f("uq_contents_platform_remote_type_remote_id"),
        ),
    )
    op.create_index("ix_contents_author_published_at", "contents", ["author_id", "published_at"], unique=False)
    op.create_index("ix_contents_last_seen_at", "contents", ["last_seen_at"], unique=False)
    op.create_index("ix_contents_platform_kind", "contents", ["platform", "kind"], unique=False)

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subscription_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cursor_before", sa.JSON(), nullable=True),
        sa.Column("cursor_after", sa.JSON(), nullable=True),
        sa.Column("manifest", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("discovered_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("asset_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("event_sequence", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("asset_count >= 0", name=op.f("ck_sync_runs_asset_count_nonnegative")),
        sa.CheckConstraint("attempt >= 0", name=op.f("ck_sync_runs_attempt_nonnegative")),
        sa.CheckConstraint("discovered_count >= 0", name=op.f("ck_sync_runs_discovered_count_nonnegative")),
        sa.CheckConstraint("event_sequence >= 0", name=op.f("ck_sync_runs_event_sequence_nonnegative")),
        sa.CheckConstraint(
            "status IN ('awaiting_auth', 'cancelled', 'claimed', 'failed_retryable', 'failed_terminal', "
            "'ingesting', 'queued', 'running', 'succeeded')",
            name=op.f("ck_sync_runs_status"),
        ),
        sa.CheckConstraint("updated_count >= 0", name=op.f("ck_sync_runs_updated_count_nonnegative")),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            name=op.f("fk_sync_runs_subscription_id_subscriptions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_runs")),
    )
    op.create_index("ix_sync_runs_created_at", "sync_runs", ["created_at"], unique=False)
    op.create_index(
        "ix_sync_runs_subscription_status",
        "sync_runs",
        ["subscription_id", "status"],
        unique=False,
    )

    op.create_table(
        "assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("content_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("remote_id", sa.String(length=512), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("locator", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("local_path", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="discovered", nullable=False),
        sa.Column("raw", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "kind IN ('attachment', 'audio', 'avatar', 'cover', 'image', 'subtitle', 'video')",
            name=op.f("ck_assets_kind"),
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_assets_position_nonnegative")),
        sa.CheckConstraint(PLATFORM_CHECK, name=op.f("ck_assets_platform")),
        sa.CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name=op.f("ck_assets_size_bytes_nonnegative")),
        sa.CheckConstraint(
            "status IN ('discovered', 'downloaded', 'downloading', 'exported', 'failed_retryable', "
            "'failed_terminal', 'queued', 'verified')",
            name=op.f("ck_assets_status"),
        ),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["contents.id"],
            name=op.f("fk_assets_content_id_contents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assets")),
        sa.UniqueConstraint("content_id", "kind", "position", name=op.f("uq_assets_content_id_kind_position")),
    )
    op.create_index("ix_assets_checksum_sha256", "assets", ["checksum_sha256"], unique=False)
    op.create_index("ix_assets_status", "assets", ["status"], unique=False)

    op.create_table(
        "run_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["sync_runs.id"],
            name=op.f("fk_run_events_run_id_sync_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_events")),
        sa.UniqueConstraint("run_id", "sequence", name=op.f("uq_run_events_run_id_sequence")),
    )
    op.create_index("ix_run_events_run_created_at", "run_events", ["run_id", "created_at"], unique=False)

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("job_type", sa.String(length=128), nullable=False),
        sa.Column("natural_key", sa.String(length=512), nullable=False),
        sa.Column("payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_jobs_attempts_nonnegative")),
        sa.CheckConstraint("max_attempts >= 1", name=op.f("ck_jobs_max_attempts_positive")),
        sa.CheckConstraint(
            "status IN ('cancelled', 'claimed', 'failed_retryable', 'failed_terminal', 'queued', 'retry_wait', "
            "'running', 'succeeded', 'waiting_auth', 'waiting_user')",
            name=op.f("ck_jobs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["sync_runs.id"],
            name=op.f("fk_jobs_run_id_sync_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("job_type", "natural_key", name=op.f("uq_jobs_job_type_natural_key")),
    )
    op.create_index("ix_jobs_claimable", "jobs", ["status", "available_at", "priority"], unique=False)
    op.create_index("ix_jobs_lease_expires_at", "jobs", ["lease_expires_at"], unique=False)
    op.create_index("ix_jobs_run_id", "jobs", ["run_id"], unique=False)

    op.create_table(
        "export_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("content_id", sa.String(length=36), nullable=False),
        sa.Column("exporter", sa.String(length=64), server_default="emby", nullable=False),
        sa.Column("exporter_version", sa.String(length=32), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("output_path", sa.Text(), nullable=False),
        sa.Column("rendered_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["contents.id"],
            name=op.f("fk_export_records_content_id_contents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_export_records")),
        sa.UniqueConstraint(
            "content_id",
            "exporter",
            "exporter_version",
            "source_fingerprint",
            name=op.f("uq_export_records_content_id_exporter_exporter_version_source_fingerprint"),
        ),
    )
    op.create_index(
        "ix_export_records_content_exporter",
        "export_records",
        ["content_id", "exporter"],
        unique=False,
    )
    op.create_index("ix_export_records_status", "export_records", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("export_records")
    op.drop_table("jobs")
    op.drop_table("run_events")
    op.drop_table("assets")
    op.drop_table("sync_runs")
    op.drop_table("contents")
    op.drop_table("subscriptions")
    op.drop_table("login_sessions")
    op.drop_table("authors")
    op.drop_table("accounts")
