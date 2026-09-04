"""Safe catalogue projection and filtering contracts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from media_sync.application.explorer import CatalogExplorerError, ContentAssetExplorer
from media_sync.infrastructure.db import Asset, Author, Content, Database, ExportRecord


def _database(tmp_path: Path) -> Database:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'catalog.sqlite3').as_posix()}")
    database.create_schema()
    return database


def _seed(database: Database, tmp_path: Path) -> dict[str, str]:
    published = datetime(2026, 9, 5, 1, 2, 3, tzinfo=UTC)
    author_id = str(uuid4())
    other_author_id = str(uuid4())
    content_id = str(uuid4())
    pending_content_id = str(uuid4())
    other_content_id = str(uuid4())
    asset_id = str(uuid4())
    pending_asset_id = str(uuid4())
    secret = "catalog-secret-sentinel"
    with database.session() as session:
        author = Author(
            id=author_id,
            platform="bili",
            remote_id="creator-100",
            display_name="Literal 100%_Creator",
            profile_url=f"https://example.test/profile?token={secret}",
            avatar_url=f"https://example.test/avatar?signature={secret}",
            raw={"secret": secret},
        )
        other_author = Author(
            id=other_author_id,
            platform="xhs",
            remote_id="creator-200",
            display_name="Other Creator",
            raw={"secret": secret},
        )
        content = Content(
            id=content_id,
            author_id=author_id,
            platform="bili",
            remote_type="video",
            remote_id="BV-safe",
            kind="video",
            title="Literal 100%_Title",
            body="A complete plain-text body.",
            canonical_url=f"https://www.bilibili.com/video/BV-safe?token={secret}#private",
            published_at=published,
            remote_updated_at=published,
            metrics={"private": secret},
            raw={"cookie": secret},
            first_seen_at=published,
            last_seen_at=published,
        )
        pending_content = Content(
            id=pending_content_id,
            author_id=author_id,
            platform="bili",
            remote_type="article",
            remote_id="pending-safe",
            kind="article",
            title="Pending item",
            body=None,
            canonical_url="file:///private/catalog-secret-sentinel",
            published_at=published,
            raw={"secret": secret},
            first_seen_at=published,
            last_seen_at=published,
        )
        other_content = Content(
            id=other_content_id,
            author_id=other_author_id,
            platform="xhs",
            remote_type="note",
            remote_id="other-safe",
            kind="image",
            title="Other item",
            published_at=published,
            raw={"secret": secret},
            first_seen_at=published,
            last_seen_at=published,
        )
        session.add_all([author, other_author, content, pending_content, other_content])
        session.flush()
        verified = Asset(
            id=asset_id,
            content_id=content_id,
            platform="bili",
            remote_id="remote-private",
            kind="video",
            position=0,
            generation=2,
            status="verified",
            source_url=f"https://cdn.example.test/media.mp4?token={secret}",
            locator={"url": f"https://cdn.example.test/media.mp4?token={secret}"},
            semantic_fingerprint="1" * 64,
            locator_fingerprint="2" * 64,
            mime_type="video/mp4",
            size_bytes=42,
            checksum_sha256="a" * 64,
            local_path=str(tmp_path / secret / "private.mp4"),
            width=1920,
            height=1080,
            duration_ms=12_345,
            etag=secret,
            last_modified=secret,
            verified_at=published,
            downloaded_at=published,
            last_error_code="archive_blob_missing",
            last_error_message=secret,
            raw={"secret": secret},
        )
        pending_asset = Asset(
            id=pending_asset_id,
            content_id=pending_content_id,
            platform="bili",
            remote_id="pending-private",
            kind="image",
            position=0,
            status="discovered",
            source_url=f"https://cdn.example.test/image.png?token={secret}",
            locator={"private": secret},
            semantic_fingerprint="3" * 64,
            locator_fingerprint="4" * 64,
            mime_type="text/html",
            last_error_code="UPPERCASE PRIVATE MESSAGE",
            last_error_message=secret,
            raw={"secret": secret},
        )
        session.add_all([verified, pending_asset])
        session.flush()
        session.add(
            ExportRecord(
                id=str(uuid4()),
                content_id=content_id,
                exporter="emby",
                exporter_version="1",
                source_fingerprint="5" * 64,
                output_path=str(tmp_path / secret / "library"),
                status="succeeded",
                exported_at=published,
                error_message=secret,
            )
        )
    return {
        "author_id": author_id,
        "content_id": content_id,
        "pending_content_id": pending_content_id,
        "asset_id": asset_id,
        "pending_asset_id": pending_asset_id,
    }


def test_safe_content_and_asset_details_omit_private_fields(tmp_path: Path) -> None:
    database = _database(tmp_path)
    try:
        ids = _seed(database, tmp_path)
        explorer = ContentAssetExplorer(database)

        content = explorer.get_content(ids["content_id"])
        assert content["body"] == "A complete plain-text body."
        assert content["canonical_url"] == "https://www.bilibili.com/video/BV-safe"
        assert content["archive_state"] == "complete"
        assert content["exports"] == {
            "succeeded_count": 1,
            "last_exported_at": "2026-09-05T01:02:03+00:00",
        }
        assert [item["id"] for item in content["assets"]] == [ids["asset_id"]]  # type: ignore[index]

        asset = explorer.get_asset(ids["asset_id"])
        assert asset["checksum_sha256"] == "a" * 64
        assert asset["archive"] == {
            "state": "eligible",
            "eligible": True,
            "preview_url": f"/api/v1/assets/{ids['asset_id']}/archive",
            "recovery_url": f"/api/v1/assets/{ids['asset_id']}/download",
        }
        assert asset["allowed_actions"] == ["preview", "download", "export_author"]
        assert asset["last_error_code"] == "archive_blob_missing"

        encoded = json.dumps({"content": content, "asset": asset}, sort_keys=True)
        assert "catalog-secret-sentinel" not in encoded
        for forbidden in (
            "raw",
            "locator",
            "source_url",
            "local_path",
            "etag",
            "last_modified",
            "last_error_message",
            "output_path",
            "error_message",
        ):
            assert forbidden not in encoded
    finally:
        database.dispose()


def test_lists_apply_literal_filters_and_preserve_safe_legacy_fields(tmp_path: Path) -> None:
    database = _database(tmp_path)
    try:
        ids = _seed(database, tmp_path)
        explorer = ContentAssetExplorer(database)

        literal = explorer.list_contents(query="%_", archived=True, exported=True)
        assert [item["id"] for item in literal] == [ids["content_id"]]
        assert set(
            (
                "id",
                "author_id",
                "author_display_name",
                "platform",
                "remote_type",
                "remote_id",
                "kind",
                "title",
                "body_excerpt",
                "canonical_url",
                "published_at",
                "asset_count",
                "archived_count",
                "export_count",
            )
        ).issubset(literal[0])

        incomplete = explorer.list_contents(
            platform="bili",
            author_id=ids["author_id"],
            archived=False,
            exported=False,
        )
        assert [item["id"] for item in incomplete] == [ids["pending_content_id"]]
        assets = explorer.list_assets(
            platform="bili",
            kind="video",
            author_id=ids["author_id"],
            content_id=ids["content_id"],
            archived=True,
            query="Literal",
        )
        assert [item["id"] for item in assets] == [ids["asset_id"]]
        assert assets[0]["author_display_name"] == "Literal 100%_Creator"
        assert assets[0]["content_title"] == "Literal 100%_Title"

        legacy_order = explorer.list_assets()
        legacy_keys = [
            (item["author_id"], item["content_id"], item["kind"], item["position"], item["id"]) for item in legacy_order
        ]
        assert legacy_keys == sorted(legacy_keys)

        pending = explorer.get_asset(ids["pending_asset_id"])
        assert pending["mime_type"] is None
        assert pending["archive"] == {
            "state": "not_ready",
            "eligible": False,
            "preview_url": None,
            "recovery_url": f"/api/v1/assets/{ids['pending_asset_id']}/download",
        }
        assert pending["allowed_actions"] == ["download"]
        assert pending["last_error_code"] == "asset_error_unknown"
    finally:
        database.dispose()


@pytest.mark.parametrize(
    "canonical_url",
    [
        "http://localhost/admin",
        "http://service.local/admin",
        "http://metadata.internal/latest",
        "http://127.0.0.1/admin",
        "http://127.1/admin",
        "http://0x7f.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/admin",
        "http://[::1]/admin",
        "http://[fe80::1]/admin",
        "https://evilbilibili.com/video/BV1",
        "https://bilibili.com.evil.test/video/BV1",
        "https://www.xiaohongshu.com/explore/not-a-bili-host",
    ],
)
def test_content_projection_rejects_non_public_canonical_urls(tmp_path: Path, canonical_url: str) -> None:
    database = _database(tmp_path)
    try:
        ids = _seed(database, tmp_path)
        with database.session() as session:
            content = session.get(Content, ids["pending_content_id"])
            assert content is not None
            content.canonical_url = canonical_url

        detail = ContentAssetExplorer(database).get_content(ids["pending_content_id"])
        assert detail["canonical_url"] is None
    finally:
        database.dispose()


def test_content_projection_accepts_only_the_matching_platform_host_and_removes_authority_fragments(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    try:
        ids = _seed(database, tmp_path)
        explorer = ContentAssetExplorer(database)
        cases = (
            ("bili", "https://t.bilibili.com/123?token=private#fragment", "https://t.bilibili.com/123"),
            ("xhs", "https://www.xiaohongshu.com/explore/123?token=private", "https://www.xiaohongshu.com/explore/123"),
            ("dy", "https://v.douyin.com/abc/?token=private", "https://v.douyin.com/abc/"),
            ("ks", "https://www.kuaishou.com/short-video/123#fragment", "https://www.kuaishou.com/short-video/123"),
            ("wb", "https://m.weibo.cn/detail/123?token=private", "https://m.weibo.cn/detail/123"),
            ("tieba", "https://tieba.baidu.com/p/123?pn=1", "https://tieba.baidu.com/p/123"),
            (
                "zhihu",
                "https://www.zhihu.com/question/1/answer/2#fragment",
                "https://www.zhihu.com/question/1/answer/2",
            ),
        )
        for platform, canonical_url, expected in cases:
            with database.session() as session:
                content = session.get(Content, ids["pending_content_id"])
                assert content is not None
                content.platform = platform
                content.canonical_url = canonical_url

            detail = explorer.get_content(ids["pending_content_id"])
            assert detail["canonical_url"] == expected
    finally:
        database.dispose()


def test_library_filters_and_not_found_errors_are_fixed(tmp_path: Path) -> None:
    database = _database(tmp_path)
    try:
        ids = _seed(database, tmp_path)
        explorer = ContentAssetExplorer(database)

        library = explorer.list_library(platform="bili", query="%_")
        assert len(library) == 1
        assert library[0]["author_id"] == ids["author_id"]
        assert library[0]["archive_state"] == "partial"
        assert explorer.list_library(platform="xhs", query="%_") == []

        with pytest.raises(CatalogExplorerError, match="catalog_content_not_found") as content_error:
            explorer.get_content(str(uuid4()))
        assert content_error.value.code == "catalog_content_not_found"
        with pytest.raises(CatalogExplorerError, match="catalog_asset_not_found") as asset_error:
            explorer.get_asset(str(uuid4()))
        assert asset_error.value.code == "catalog_asset_not_found"
        with pytest.raises(CatalogExplorerError, match="catalog_query_invalid"):
            explorer.list_contents(query="x" * 201)
        with pytest.raises(CatalogExplorerError, match="catalog_query_invalid"):
            explorer.list_assets(limit=0)
    finally:
        database.dispose()


@pytest.mark.parametrize("mime_type", ["application/pdf", "application/x-subrip", "text/vtt"])
def test_asset_projection_preserves_every_verified_probe_mime(tmp_path: Path, mime_type: str) -> None:
    database = _database(tmp_path)
    try:
        ids = _seed(database, tmp_path)
        with database.session() as session:
            asset = session.get(Asset, ids["asset_id"])
            assert asset is not None
            asset.mime_type = mime_type

        detail = ContentAssetExplorer(database).get_asset(ids["asset_id"])
        assert detail["mime_type"] == mime_type
    finally:
        database.dispose()
