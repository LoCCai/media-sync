"""Add replay-safe asset download lifecycle fields.

Revision ID: 0003_media_download_emby
Revises: 0002_checkpoint
Create Date: 2026-08-30
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "0003_media_download_emby"
down_revision: str | None = "0002_checkpoint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SECRET_PATH_MARKERS = frozenset(
    {
        "access_key",
        "access_token",
        "accesskey",
        "apikey",
        "api_key",
        "auth",
        "auth_key",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "password",
        "passwd",
        "private_key",
        "refresh_token",
        "secret",
        "session",
        "session_id",
        "sessionid",
        "sig",
        "sign",
        "signature",
        "signing_key",
        "token",
        "x_api_key",
        "xapikey",
    }
)
_COMPOSITE_SECRET_PATH_MARKER = re.compile(r"(?:^|_)(?:api|access)_?key(?:$|_)")
_MAX_PATH_DECODE_PASSES = 3


def _canonical_sha256(value: Mapping[str, Any], *, ensure_ascii: bool = False) -> str:
    payload = json.dumps(value, ensure_ascii=ensure_ascii, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalized_secret_name(value: str) -> str:
    value = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", value)
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    return value.lower().replace("-", "_")


def _is_secret_path_marker(value: str) -> bool:
    normalized = _normalized_secret_name(value)
    return normalized in _SECRET_PATH_MARKERS or _COMPOSITE_SECRET_PATH_MARKER.search(normalized) is not None


def _has_secret_url_path(path: str) -> bool:
    current = path
    for _ in range(_MAX_PATH_DECODE_PASSES + 1):
        segments = current.split("/")
        for index, segment in enumerate(segments):
            matrix_parts = segment.split(";")
            if _is_secret_path_marker(matrix_parts[0]) and any(segments[index + 1 :]):
                return True
            for assignment in matrix_parts:
                key, separator, candidate = assignment.partition("=")
                if separator and candidate and _is_secret_path_marker(key):
                    return True
        decoded = unquote(current)
        if decoded == current:
            break
        current = decoded
    return False


def _json_mapping(value: object) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return None
    return decoded if isinstance(decoded, Mapping) else None


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _is_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _recoverable_emby_intent_record_ids(payload: Mapping[str, Any]) -> set[str] | None:
    """Mirror the application's closed publication-intent contract."""

    source_fingerprint = payload.get("source_fingerprint")
    intent = payload.get("intent")
    if not isinstance(intent, Mapping):
        return None
    tree_sha256 = intent.get("tree_sha256")
    manifest_sha256 = intent.get("manifest_sha256")
    managed_file_count = intent.get("managed_file_count")
    records = intent.get("records")
    if (
        intent.get("schema_version") != 1
        or intent.get("source_fingerprint") != source_fingerprint
        or not _is_sha256(source_fingerprint)
        or not _is_sha256(tree_sha256)
        or not _is_sha256(manifest_sha256)
        or isinstance(managed_file_count, bool)
        or not isinstance(managed_file_count, int)
        or managed_file_count < 0
        or not isinstance(records, list)
    ):
        return None

    record_ids: set[str] = set()
    identities: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, Mapping):
            return None
        record_id = record.get("record_id")
        content_id = record.get("content_id")
        if (
            not _is_uuid(record_id)
            or not _is_uuid(content_id)
            or record.get("source_fingerprint") != source_fingerprint
        ):
            return None
        assert isinstance(record_id, str) and isinstance(content_id, str)
        identity = record_id, content_id
        if identity in identities:
            return None
        identities.add(identity)
        record_ids.add(record_id)
    return record_ids


def _preserved_emby_recovery_identities(connection: sa.engine.Connection) -> tuple[set[str], set[str]]:
    """Find post-publication recovery state that must survive a round trip."""

    job_ids: set[str] = set()
    record_ids: set[str] = set()
    rows = connection.execute(
        sa.text("SELECT id, payload FROM jobs WHERE job_type = 'export.emby' AND status <> 'succeeded'")
    ).mappings()
    for row in rows:
        payload = _json_mapping(row["payload"])
        if payload is None:
            continue
        intent_record_ids = _recoverable_emby_intent_record_ids(payload)
        if intent_record_ids is None:
            continue
        job_ids.add(str(row["id"]))
        record_ids.update(intent_record_ids)
    return job_ids, record_ids


def _delete_except_ids(
    connection: sa.engine.Connection,
    *,
    table: str,
    predicate: str,
    preserved_ids: set[str],
) -> None:
    if not preserved_ids:
        connection.execute(sa.text(f"DELETE FROM {table} WHERE {predicate}"))
        return
    statement = sa.text(f"DELETE FROM {table} WHERE {predicate} AND id NOT IN :preserved_ids").bindparams(
        sa.bindparam("preserved_ids", expanding=True)
    )
    connection.execute(statement, {"preserved_ids": tuple(sorted(preserved_ids))})


def _semantic_source(source_url: str | None) -> str | None:
    if source_url is None:
        return None
    if source_url != source_url.strip() or len(source_url) > 4_096:
        return None
    if "\\" in source_url or any(ord(character) < 0x20 or ord(character) == 0x7F for character in source_url):
        return None
    try:
        parsed = urlsplit(source_url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or hostname is None:
        return None
    if _has_secret_url_path(parsed.path):
        return None
    try:
        normalized_host = hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    if not normalized_host or "%" in normalized_host:
        return None
    if ":" in normalized_host:
        normalized_host = f"[{normalized_host}]"
    default_port = 80 if scheme == "http" else 443
    authority = normalized_host if port in {None, default_port} else f"{normalized_host}:{port}"
    return f"{scheme}://{authority}{parsed.path or '/'}"


def _backfill_fingerprints() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT assets.id, assets.platform, assets.remote_id, assets.kind, assets.position, "
            "assets.source_url, assets.width, assets.height, assets.duration_ms, "
            "assets.mime_type, assets.size_bytes, assets.checksum_sha256, assets.local_path, "
            "assets.status, assets.created_at, assets.updated_at, "
            "contents.remote_type AS content_remote_type, contents.remote_id AS content_remote_id "
            "FROM assets JOIN contents ON contents.id = assets.content_id"
        )
    ).mappings()
    update_row = sa.text(
        "UPDATE assets SET source_url = :source_url, locator = :locator, "
        "semantic_fingerprint = :semantic_fingerprint, "
        "locator_fingerprint = :locator_fingerprint, status = :status, "
        "mime_type = :mime_type, size_bytes = :size_bytes, checksum_sha256 = :checksum_sha256, "
        "local_path = :local_path, downloaded_at = :downloaded_at, verified_at = :verified_at, "
        "last_error_code = :last_error_code, last_error_message = :last_error_message, "
        "last_error_at = :last_error_at WHERE id = :asset_id"
    )
    for row in rows:
        original_source_url = row["source_url"]
        semantic_source = _semantic_source(original_source_url)
        stable_key = _canonical_sha256(
            {
                "version": 1,
                "platform": row["platform"],
                "content_remote_type": row["content_remote_type"],
                "content_remote_id": row["content_remote_id"],
                "kind": row["kind"],
                "position": row["position"],
                "remote_id": row["remote_id"],
            },
            ensure_ascii=True,
        )
        locator: dict[str, Any]
        if original_source_url is not None and original_source_url == semantic_source:
            locator = {"type": "direct", "url": semantic_source, "version": 1}
        else:
            locator = {
                "adapter": "legacy",
                "asset_key": stable_key,
                "type": "adapter_refresh",
                "version": 1,
            }
        semantic: dict[str, Any] = {
            "version": 1,
            "platform": row["platform"],
            "content_remote_type": row["content_remote_type"],
            "content_remote_id": row["content_remote_id"],
            "kind": row["kind"],
            "position": row["position"],
            "remote_id": row["remote_id"],
            "source": semantic_source,
            "width": row["width"],
            "height": row["height"],
            "duration_ms": row["duration_ms"],
        }
        if semantic_source is None:
            semantic["locator"] = locator
        checksum = row["checksum_sha256"]
        local_path = row["local_path"]
        mime_type = row["mime_type"]
        size_bytes = row["size_bytes"]
        preserves_verified = bool(
            row["status"] == "verified"
            and isinstance(local_path, str)
            and local_path.strip()
            and Path(local_path).is_absolute()
            and isinstance(mime_type, str)
            and mime_type.strip()
            and isinstance(size_bytes, int)
            and size_bytes >= 0
            and isinstance(checksum, str)
            and len(checksum) == 64
            and all(character in "0123456789abcdefABCDEF" for character in checksum)
        )
        transient_statuses = {"downloading", "downloaded", "exported"}
        normalized_status = "discovered" if row["status"] in transient_statuses else row["status"]
        if row["status"] == "verified" and not preserves_verified:
            normalized_status = "discovered"
        requires_reset = normalized_status != row["status"]
        observed_at = row["updated_at"] or row["created_at"]
        connection.execute(
            update_row,
            {
                "asset_id": row["id"],
                "source_url": semantic_source,
                "locator": json.dumps(locator, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
                "semantic_fingerprint": _canonical_sha256(semantic),
                "locator_fingerprint": _canonical_sha256(locator, ensure_ascii=True),
                "status": normalized_status,
                "mime_type": mime_type if preserves_verified else None,
                "size_bytes": size_bytes if preserves_verified else None,
                "checksum_sha256": checksum.lower() if preserves_verified else None,
                "local_path": local_path if preserves_verified else None,
                "downloaded_at": observed_at if preserves_verified else None,
                "verified_at": observed_at if preserves_verified else None,
                "last_error_code": None if not requires_reset else "legacy_asset_reset",
                "last_error_message": (None if not requires_reset else "legacy asset state requires a fresh download"),
                "last_error_at": None if not requires_reset else observed_at,
            },
        )


def upgrade() -> None:
    with op.batch_alter_table("assets") as batch_op:
        batch_op.add_column(sa.Column("semantic_fingerprint", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("locator_fingerprint", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("generation", sa.Integer(), server_default="1", nullable=False))
        batch_op.add_column(sa.Column("download_job_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("etag", sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column("last_modified", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("download_started_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_error_code", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("last_error_message", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True))

    _backfill_fingerprints()

    with op.batch_alter_table("assets") as batch_op:
        batch_op.alter_column("semantic_fingerprint", existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column("locator_fingerprint", existing_type=sa.String(length=64), nullable=False)
        batch_op.create_check_constraint(op.f("ck_assets_generation_positive"), "generation >= 1")
        batch_op.create_foreign_key(
            op.f("fk_assets_download_job_id_jobs"),
            "jobs",
            ["download_job_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_index("ix_assets_download_job_id", "assets", ["download_job_id"], unique=False)


def downgrade() -> None:
    connection = op.get_bind()

    # Generation is introduced by this revision, while durable job identities
    # already exist in 0001.  A downgrade necessarily forgets the current
    # generation, so retaining generation-keyed jobs would poison the matching
    # identities if the database is upgraded and reaches that generation again.
    # Clear the FK first so this remains valid with SQLite foreign keys enabled.
    connection.execute(sa.text("UPDATE assets SET download_job_id = NULL"))
    connection.execute(sa.text("DELETE FROM jobs WHERE job_type = 'asset_download'"))

    # Successful Emby jobs are the durable chain for an already-published tree
    # and must survive a round trip.  A non-succeeded job with a persisted
    # publication intent may also describe bytes already committed to disk, so
    # retain that job and every record named by its intent for exact recovery.
    # Only pre-publication retryable/terminal identities are safe to discard.
    preserved_job_ids, preserved_record_ids = _preserved_emby_recovery_identities(connection)
    _delete_except_ids(
        connection,
        table="export_records",
        predicate="exporter = 'emby' AND status <> 'succeeded'",
        preserved_ids=preserved_record_ids,
    )
    _delete_except_ids(
        connection,
        table="jobs",
        predicate="job_type = 'export.emby' AND status <> 'succeeded'",
        preserved_ids=preserved_job_ids,
    )

    op.drop_index("ix_assets_download_job_id", table_name="assets")
    with op.batch_alter_table("assets") as batch_op:
        batch_op.drop_constraint(op.f("fk_assets_download_job_id_jobs"), type_="foreignkey")
        batch_op.drop_constraint(op.f("ck_assets_generation_positive"), type_="check")
        batch_op.drop_column("last_error_at")
        batch_op.drop_column("last_error_message")
        batch_op.drop_column("last_error_code")
        batch_op.drop_column("verified_at")
        batch_op.drop_column("downloaded_at")
        batch_op.drop_column("download_started_at")
        batch_op.drop_column("queued_at")
        batch_op.drop_column("last_modified")
        batch_op.drop_column("etag")
        batch_op.drop_column("download_job_id")
        batch_op.drop_column("generation")
        batch_op.drop_column("locator_fingerprint")
        batch_op.drop_column("semantic_fingerprint")
