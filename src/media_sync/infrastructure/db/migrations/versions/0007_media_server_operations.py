"""Extend the closed Operation vocabulary for media-server work.

Revision ID: 0007_media_server_operations
Revises: 0006_operations_observability
Create Date: 2026-09-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_media_server_operations"
down_revision: str | None = "0006_operations_observability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEGACY_KINDS = (
    "account-login",
    "asset-download",
    "emby-export",
    "pipeline-run",
    "scheduler-run",
)
_MEDIA_SERVER_KINDS = ("media-server-probe", "media-server-scan")
_CURRENT_KINDS = (*_LEGACY_KINDS, *_MEDIA_SERVER_KINDS)


def _kind_check(kinds: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{kind}'" for kind in sorted(kinds))
    return f"kind IN ({quoted})"


def _set_sqlite_foreign_keys(connection: sa.engine.Connection, *, enabled: bool) -> None:
    # The application installs a SQLAlchemy ``begin`` hook that emits an
    # explicit BEGIN.  Executing this PRAGMA through SQLAlchemy would trigger
    # that hook and SQLite would silently ignore the setting change.  The raw
    # cursor is used only inside Alembic's autocommit block.
    dbapi_connection = connection.connection.driver_connection
    # Alembic creates a synthetic SQLAlchemy transaction even after selecting
    # AUTOCOMMIT.  This repository's explicit-begin hook turns that synthetic
    # transaction into a real SQLite BEGIN, so end it at the DBAPI boundary
    # before changing the connection-wide PRAGMA.
    dbapi_connection.commit()
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")
        observed = cursor.execute("PRAGMA foreign_keys").fetchone()
    finally:
        cursor.close()
    if observed != (1 if enabled else 0,):
        raise RuntimeError("media_server_operation_migration_foreign_key_control_failed")


def _replace_kind_check(kinds: tuple[str, ...]) -> None:
    connection = op.get_bind()
    if connection.dialect.name != "sqlite":
        op.drop_constraint(op.f("ck_operations_kind"), "operations", type_="check")
        op.create_check_constraint(
            op.f("ck_operations_kind"),
            "operations",
            _kind_check(kinds),
        )
        return

    # SQLite must copy the table to alter a CHECK constraint.  Referencing
    # event/subject rows survive only when FK enforcement is suspended outside
    # a transaction and restored immediately after the copy.
    context = op.get_context()
    with context.autocommit_block():
        _set_sqlite_foreign_keys(connection, enabled=False)
    if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 0:
        raise RuntimeError("media_server_operation_migration_foreign_key_control_failed")
    try:
        with op.batch_alter_table("operations", recreate="always") as batch_op:
            batch_op.drop_constraint(op.f("ck_operations_kind"), type_="check")
            batch_op.create_check_constraint(
                op.f("ck_operations_kind"),
                _kind_check(kinds),
            )
    finally:
        with context.autocommit_block():
            _set_sqlite_foreign_keys(connection, enabled=True)

    if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 1:
        raise RuntimeError("media_server_operation_migration_foreign_key_control_failed")

    violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    if violations:
        raise RuntimeError("media_server_operation_migration_foreign_key_invalid")


def upgrade() -> None:
    _replace_kind_check(_CURRENT_KINDS)


def downgrade() -> None:
    context = op.get_context()
    if context.as_sql:
        raise RuntimeError("media_server_operation_downgrade_requires_online_audit")

    operations = sa.table("operations", sa.column("kind", sa.String(length=64)))
    contains_media_server_rows = (
        op.get_bind()
        .execute(sa.select(sa.literal(1)).where(operations.c.kind.in_(_MEDIA_SERVER_KINDS)).limit(1))
        .first()
    )
    if contains_media_server_rows is not None:
        raise RuntimeError("media_server_operation_rows_prevent_downgrade")
    _replace_kind_check(_LEGACY_KINDS)
