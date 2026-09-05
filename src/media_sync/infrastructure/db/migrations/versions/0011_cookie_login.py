"""Add an independent Cookie-login Operation without changing QR history.

Revision ID: 0011_cookie_login
Revises: 0010_creator_profiles
"""

from collections.abc import Sequence
from importlib import import_module

import sqlalchemy as sa
from alembic import op

revision: str = "0011_cookie_login"
down_revision: str | None = "0010_creator_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREVIOUS_KINDS = (
    "account-login",
    "asset-download",
    "creator-profile",
    "emby-export",
    "media-server-probe",
    "media-server-scan",
    "pipeline-run",
    "scheduler-run",
)


def _replace(kinds: tuple[str, ...]) -> None:
    migration = import_module("media_sync.infrastructure.db.migrations.versions.0007_media_server_operations")
    migration._replace_kind_check(kinds)


def upgrade() -> None:
    _replace((*_PREVIOUS_KINDS, "account-cookie-login"))


def downgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError("cookie_login_downgrade_requires_online_audit")
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM operations WHERE kind='account-cookie-login' LIMIT 1")).first():
        raise RuntimeError("cookie_login_history_prevents_downgrade")
    if connection.execute(sa.text("SELECT 1 FROM accounts WHERE credential_ref LIKE 'managed:%' LIMIT 1")).first():
        raise RuntimeError("managed_credentials_prevent_downgrade")
    _replace(_PREVIOUS_KINDS)
