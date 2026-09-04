"""Closed, redaction-safe catalogue projections for content and assets.

The explorer deliberately owns its public dictionaries.  ORM objects, upstream
raw records, locators, source URLs, local paths, download validators, exception
text and export paths never cross this boundary.
"""

from __future__ import annotations

import re
from datetime import datetime
from ipaddress import ip_address
from typing import Final
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import func, or_, select
from sqlalchemy.sql.selectable import ScalarSelect

from media_sync.application.archive_preview import SAFE_ARCHIVE_MEDIA_TYPES
from media_sync.infrastructure.db.database import Database
from media_sync.infrastructure.db.models import Asset, Author, Content, ExportRecord

MAX_EXPLORER_LIMIT: Final = 1_000
MAX_EXPLORER_QUERY_LENGTH: Final = 200
ARCHIVED_ASSET_STATES: Final = frozenset({"verified", "exported"})

_CHECKSUM = re.compile(r"[0-9a-f]{64}\Z")
_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]{0,127}\Z")
_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_LEGACY_IP_LABEL = re.compile(r"(?:0x[0-9a-f]+|[0-9]+)\Z")
_LOCAL_HOST_SUFFIXES: Final = ("localhost", "local", "internal", "home.arpa")
_CANONICAL_HOST_SUFFIXES: Final[dict[str, tuple[str, ...]]] = {
    "bili": ("bilibili.com", "b23.tv"),
    "xhs": ("xiaohongshu.com",),
    "dy": ("douyin.com",),
    "ks": ("kuaishou.com",),
    "wb": ("weibo.cn", "weibo.com"),
    "tieba": ("tieba.baidu.com",),
    "zhihu": ("zhihu.com",),
}
_ERROR_MESSAGES: Final = {
    "catalog_content_not_found": "content was not found",
    "catalog_asset_not_found": "asset was not found",
    "catalog_query_invalid": "catalogue query is invalid",
}


class CatalogExplorerError(RuntimeError):
    """A fixed-code catalogue rejection that never reflects stored values."""

    def __init__(self, code: str) -> None:
        try:
            message = _ERROR_MESSAGES[code]
        except KeyError as error:  # pragma: no cover - programmer error
            raise ValueError("unknown catalogue error code") from error
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _iso_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _bounded_limit(limit: int) -> int:
    if type(limit) is not int or not 1 <= limit <= MAX_EXPLORER_LIMIT:
        raise CatalogExplorerError("catalog_query_invalid")
    return limit


def _literal_search_pattern(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CatalogExplorerError("catalog_query_invalid")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > MAX_EXPLORER_QUERY_LENGTH or any(not character.isprintable() for character in normalized):
        raise CatalogExplorerError("catalog_query_invalid")
    escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _safe_checksum(value: object) -> str | None:
    return value if isinstance(value, str) and _CHECKSUM.fullmatch(value) is not None else None


def _safe_mime_type(value: object) -> str | None:
    return value if isinstance(value, str) and value in SAFE_ARCHIVE_MEDIA_TYPES else None


def _safe_nonnegative(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _safe_error_code(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and _ERROR_CODE.fullmatch(value) is not None:
        return value
    return "asset_error_unknown"


def _is_public_web_host(host: str) -> bool:
    try:
        address = ip_address(host)
    except ValueError:
        if ":" in host or "%" in host:
            return False
        labels = host.split(".")
        if len(labels) < 2 or any(_HOST_LABEL.fullmatch(label) is None for label in labels):
            return False
        if all(_LEGACY_IP_LABEL.fullmatch(label) is not None for label in labels):
            return False
        return not any(host == suffix or host.endswith(f".{suffix}") for suffix in _LOCAL_HOST_SUFFIXES)
    return address.is_global and not address.is_multicast


def _safe_canonical_url(value: object, *, platform: str) -> str | None:
    """Return a query-free public http(s) URL or no URL at all."""

    if not isinstance(value, str) or not value or len(value) > 4_096 or any(ord(character) < 32 for character in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or parsed.username is not None or parsed.password is not None:
            return None
        hostname = parsed.hostname
        if hostname is None or not hostname.isascii() or len(hostname) > 253:
            return None
        port = parsed.port
        host = hostname.lower().rstrip(".")
        if not host or not _is_public_web_host(host):
            return None
        allowed_suffixes = _CANONICAL_HOST_SUFFIXES.get(platform)
        if allowed_suffixes is None or not any(
            host == suffix or host.endswith(f".{suffix}") for suffix in allowed_suffixes
        ):
            return None
        rendered_host = f"[{host}]" if ":" in host else host
        default_port = 80 if parsed.scheme == "http" else 443
        netloc = rendered_host if port is None or port == default_port else f"{rendered_host}:{port}"
        path = parsed.path or "/"
        return urlunsplit((parsed.scheme, netloc, path, "", ""))
    except (UnicodeError, ValueError):
        return None


def _archive_state(asset_count: int, archived_count: int) -> str:
    if asset_count == 0:
        return "empty"
    if archived_count == 0:
        return "pending"
    if archived_count == asset_count:
        return "complete"
    return "partial"


def _archive_projection(asset: Asset) -> dict[str, object]:
    checksum = _safe_checksum(asset.checksum_sha256)
    size_bytes = _safe_nonnegative(asset.size_bytes)
    eligible = (
        asset.status in ARCHIVED_ASSET_STATES
        and isinstance(asset.local_path, str)
        and bool(asset.local_path)
        and checksum is not None
        and size_bytes is not None
    )
    return {
        "state": "eligible" if eligible else "not_ready",
        "eligible": eligible,
        "preview_url": f"/api/v1/assets/{asset.id}/archive" if eligible else None,
        "recovery_url": f"/api/v1/assets/{asset.id}/download",
    }


def _asset_actions(asset: Asset, *, preview_eligible: bool) -> list[str]:
    actions: list[str] = []
    if preview_eligible:
        actions.append("preview")
    if asset.status in {"discovered", "failed_retryable", "verified", "exported"}:
        actions.append("download")
    if asset.status in ARCHIVED_ASSET_STATES:
        actions.append("export_author")
    return actions


def _asset_summary(
    asset: Asset,
    *,
    author_id: str,
    author_display_name: str,
    content_title: str | None,
) -> dict[str, object]:
    archive = _archive_projection(asset)
    return {
        "id": asset.id,
        "author_id": author_id,
        "author_display_name": author_display_name,
        "content_id": asset.content_id,
        "content_title": content_title,
        "platform": asset.platform,
        "kind": asset.kind,
        "position": asset.position,
        "generation": asset.generation,
        "status": asset.status,
        "mime_type": _safe_mime_type(asset.mime_type),
        "size_bytes": _safe_nonnegative(asset.size_bytes),
        "verified_at": _iso_datetime(asset.verified_at),
        "archive": archive,
        "allowed_actions": _asset_actions(asset, preview_eligible=archive["eligible"] is True),
    }


def _content_summary(
    content: Content,
    *,
    author_display_name: str,
    asset_count: int,
    archived_count: int,
    export_count: int,
) -> dict[str, object]:
    return {
        "id": content.id,
        "author_id": content.author_id,
        "author_display_name": author_display_name,
        "platform": content.platform,
        "remote_type": content.remote_type,
        "remote_id": content.remote_id,
        "kind": content.kind,
        "title": content.title,
        "body_excerpt": content.body[:280] if content.body else None,
        "canonical_url": _safe_canonical_url(content.canonical_url, platform=content.platform),
        "published_at": _iso_datetime(content.published_at),
        "asset_count": asset_count,
        "archived_count": archived_count,
        "export_count": export_count,
        "archive_state": _archive_state(asset_count, archived_count),
        "tombstoned": content.tombstoned_at is not None,
    }


def _content_counts() -> tuple[ScalarSelect[int], ScalarSelect[int], ScalarSelect[int]]:
    asset_count = (
        select(func.count(Asset.id)).where(Asset.content_id == Content.id).correlate(Content).scalar_subquery()
    )
    archived_count = (
        select(func.count(Asset.id))
        .where(Asset.content_id == Content.id, Asset.status.in_(tuple(ARCHIVED_ASSET_STATES)))
        .correlate(Content)
        .scalar_subquery()
    )
    export_count = (
        select(func.count(ExportRecord.id))
        .where(ExportRecord.content_id == Content.id, ExportRecord.status == "succeeded")
        .correlate(Content)
        .scalar_subquery()
    )
    return asset_count, archived_count, export_count


class ContentAssetExplorer:
    """Read-only catalogue service with an explicit public projection."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def list_contents(
        self,
        *,
        platform: str | None = None,
        kind: str | None = None,
        author_id: str | None = None,
        archived: bool | None = None,
        exported: bool | None = None,
        query: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        bounded_limit = _bounded_limit(limit)
        pattern = _literal_search_pattern(query)
        asset_count, archived_count, export_count = _content_counts()
        statement = (
            select(
                Content,
                Author.display_name,
                asset_count.label("asset_count"),
                archived_count.label("archived_count"),
                export_count.label("export_count"),
            )
            .join(Author, Content.author_id == Author.id)
            .order_by(Content.published_at.desc(), Content.created_at.desc(), Content.id.desc())
            .limit(bounded_limit)
        )
        if platform is not None:
            statement = statement.where(Content.platform == platform)
        if kind is not None:
            statement = statement.where(Content.kind == kind)
        if author_id is not None:
            statement = statement.where(Content.author_id == author_id)
        if archived is True:
            statement = statement.where(asset_count > 0, archived_count == asset_count)
        elif archived is False:
            statement = statement.where(or_(asset_count == 0, archived_count < asset_count))
        if exported is True:
            statement = statement.where(export_count > 0)
        elif exported is False:
            statement = statement.where(export_count == 0)
        if pattern is not None:
            statement = statement.where(
                or_(
                    Content.title.ilike(pattern, escape="\\"),
                    Content.remote_id.ilike(pattern, escape="\\"),
                    Author.display_name.ilike(pattern, escape="\\"),
                )
            )
        with self._database.session() as session:
            rows = session.execute(statement).all()
            return [
                _content_summary(
                    content,
                    author_display_name=author_display_name,
                    asset_count=row_asset_count,
                    archived_count=row_archived_count,
                    export_count=row_export_count,
                )
                for content, author_display_name, row_asset_count, row_archived_count, row_export_count in rows
            ]

    def get_content(self, content_id: str) -> dict[str, object]:
        asset_count, archived_count, export_count = _content_counts()
        with self._database.session() as session:
            row = session.execute(
                select(
                    Content,
                    Author.display_name,
                    asset_count.label("asset_count"),
                    archived_count.label("archived_count"),
                    export_count.label("export_count"),
                )
                .join(Author, Content.author_id == Author.id)
                .where(Content.id == content_id)
            ).one_or_none()
            if row is None:
                raise CatalogExplorerError("catalog_content_not_found")
            content, author_display_name, row_asset_count, row_archived_count, row_export_count = row
            payload = _content_summary(
                content,
                author_display_name=author_display_name,
                asset_count=row_asset_count,
                archived_count=row_archived_count,
                export_count=row_export_count,
            )
            assets = session.execute(
                select(Asset, Author.display_name, Content.title)
                .join(Content, Asset.content_id == Content.id)
                .join(Author, Content.author_id == Author.id)
                .where(Asset.content_id == content.id)
                .order_by(Asset.kind, Asset.position, Asset.id)
            ).all()
            last_exported_at = session.scalar(
                select(func.max(ExportRecord.exported_at)).where(
                    ExportRecord.content_id == content.id,
                    ExportRecord.status == "succeeded",
                )
            )
            payload.update(
                {
                    "body": content.body,
                    "remote_updated_at": _iso_datetime(content.remote_updated_at),
                    "first_seen_at": _iso_datetime(content.first_seen_at),
                    "last_seen_at": _iso_datetime(content.last_seen_at),
                    "assets": [
                        _asset_summary(
                            asset,
                            author_id=content.author_id,
                            author_display_name=row_author_display_name,
                            content_title=content_title,
                        )
                        for asset, row_author_display_name, content_title in assets
                    ],
                    "exports": {
                        "succeeded_count": row_export_count,
                        "last_exported_at": _iso_datetime(last_exported_at),
                    },
                }
            )
            return payload

    def list_assets(
        self,
        *,
        platform: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        author_id: str | None = None,
        content_id: str | None = None,
        archived: bool | None = None,
        query: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        bounded_limit = _bounded_limit(limit)
        pattern = _literal_search_pattern(query)
        statement = (
            select(Asset, Content.author_id, Author.display_name, Content.title)
            .join(Content, Asset.content_id == Content.id)
            .join(Author, Content.author_id == Author.id)
            .order_by(Content.author_id, Asset.content_id, Asset.kind, Asset.position, Asset.id)
            .limit(bounded_limit)
        )
        if platform is not None:
            statement = statement.where(Asset.platform == platform)
        if kind is not None:
            statement = statement.where(Asset.kind == kind)
        if status is not None:
            statement = statement.where(Asset.status == status)
        if author_id is not None:
            statement = statement.where(Content.author_id == author_id)
        if content_id is not None:
            statement = statement.where(Asset.content_id == content_id)
        if archived is True:
            statement = statement.where(Asset.status.in_(tuple(ARCHIVED_ASSET_STATES)))
        elif archived is False:
            statement = statement.where(Asset.status.not_in(tuple(ARCHIVED_ASSET_STATES)))
        if pattern is not None:
            statement = statement.where(
                or_(
                    Asset.id.ilike(pattern, escape="\\"),
                    Content.remote_id.ilike(pattern, escape="\\"),
                    Content.title.ilike(pattern, escape="\\"),
                    Author.display_name.ilike(pattern, escape="\\"),
                )
            )
        with self._database.session() as session:
            rows = session.execute(statement).all()
            return [
                _asset_summary(
                    asset,
                    author_id=row_author_id,
                    author_display_name=author_display_name,
                    content_title=content_title,
                )
                for asset, row_author_id, author_display_name, content_title in rows
            ]

    def get_asset(self, asset_id: str) -> dict[str, object]:
        with self._database.session() as session:
            row = session.execute(
                select(Asset, Content, Author.display_name)
                .join(Content, Asset.content_id == Content.id)
                .join(Author, Content.author_id == Author.id)
                .where(Asset.id == asset_id)
            ).one_or_none()
            if row is None:
                raise CatalogExplorerError("catalog_asset_not_found")
            asset, content, author_display_name = row
            payload = _asset_summary(
                asset,
                author_id=content.author_id,
                author_display_name=author_display_name,
                content_title=content.title,
            )
            payload.update(
                {
                    "checksum_sha256": _safe_checksum(asset.checksum_sha256),
                    "width": _safe_nonnegative(asset.width),
                    "height": _safe_nonnegative(asset.height),
                    "duration_ms": _safe_nonnegative(asset.duration_ms),
                    "downloaded_at": _iso_datetime(asset.downloaded_at),
                    "created_at": _iso_datetime(asset.created_at),
                    "updated_at": _iso_datetime(asset.updated_at),
                    "last_error_code": _safe_error_code(asset.last_error_code),
                    "content": {
                        "id": content.id,
                        "remote_id": content.remote_id,
                        "kind": content.kind,
                        "title": content.title,
                        "published_at": _iso_datetime(content.published_at),
                    },
                }
            )
            return payload

    def list_library(
        self,
        *,
        platform: str | None = None,
        query: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        bounded_limit = _bounded_limit(limit)
        pattern = _literal_search_pattern(query)
        content_count = (
            select(func.count(Content.id)).where(Content.author_id == Author.id).correlate(Author).scalar_subquery()
        )
        asset_count = (
            select(func.count(Asset.id))
            .select_from(Asset)
            .join(Content, Asset.content_id == Content.id)
            .where(Content.author_id == Author.id)
            .correlate(Author)
            .scalar_subquery()
        )
        archived_count = (
            select(func.count(Asset.id))
            .select_from(Asset)
            .join(Content, Asset.content_id == Content.id)
            .where(Content.author_id == Author.id, Asset.status.in_(tuple(ARCHIVED_ASSET_STATES)))
            .correlate(Author)
            .scalar_subquery()
        )
        exported_count = (
            select(func.count(ExportRecord.id))
            .select_from(ExportRecord)
            .join(Content, ExportRecord.content_id == Content.id)
            .where(Content.author_id == Author.id, ExportRecord.status == "succeeded")
            .correlate(Author)
            .scalar_subquery()
        )
        last_published_at = (
            select(func.max(Content.published_at))
            .where(Content.author_id == Author.id)
            .correlate(Author)
            .scalar_subquery()
        )
        statement = (
            select(
                Author,
                content_count.label("content_count"),
                asset_count.label("asset_count"),
                archived_count.label("archived_count"),
                exported_count.label("exported_count"),
                last_published_at.label("last_published_at"),
            )
            .order_by(Author.display_name, Author.id)
            .limit(bounded_limit)
        )
        if platform is not None:
            statement = statement.where(Author.platform == platform)
        if pattern is not None:
            statement = statement.where(
                or_(
                    Author.display_name.ilike(pattern, escape="\\"),
                    Author.remote_id.ilike(pattern, escape="\\"),
                )
            )
        with self._database.session() as session:
            rows = session.execute(statement).all()
            return [
                {
                    "author_id": author.id,
                    "platform": author.platform,
                    "display_name": author.display_name,
                    "remote_id": author.remote_id,
                    "content_count": row_content_count,
                    "asset_count": row_asset_count,
                    "archived_count": row_archived_count,
                    "exported_count": row_exported_count,
                    "last_published_at": _iso_datetime(last_published),
                    "archive_state": _archive_state(row_asset_count, row_archived_count),
                }
                for (
                    author,
                    row_content_count,
                    row_asset_count,
                    row_archived_count,
                    row_exported_count,
                    last_published,
                ) in rows
            ]


__all__ = [
    "ARCHIVED_ASSET_STATES",
    "MAX_EXPLORER_LIMIT",
    "MAX_EXPLORER_QUERY_LENGTH",
    "CatalogExplorerError",
    "ContentAssetExplorer",
]
