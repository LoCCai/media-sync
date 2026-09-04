"""HTTP contracts for the safe content and asset catalogue."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from starlette.requests import ClientDisconnect
from starlette.types import Message, Scope

from media_sync.application import ArchivePreviewService, ArchivePreviewSource
from media_sync.config import Settings
from media_sync.infrastructure.db import Asset, Author, Content, Database, ExportRecord, Operation
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.interfaces.api import _ArchiveStreamingResponse, create_api_app

ARCHIVE_BYTES = b"0123456789abcdefghijklmnopqrstuvwxyz"


def _asgi_exchange(app: FastAPI, method: str, path: str) -> list[Message]:
    async def exchange() -> list[Message]:
        messages: list[Message] = []
        request_sent = False

        async def receive() -> Message:
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            messages.append(message)

        scope: Scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"testserver")],
            "client": ("testclient", 50_000),
            "server": ("testserver", 80),
            "state": {},
        }
        await app(scope, receive, send)
        return messages

    return asyncio.run(exchange())


def _asgi_status_and_body(messages: list[Message]) -> tuple[int, bytes]:
    starts = [message for message in messages if message["type"] == "http.response.start"]
    assert len(starts) == 1
    body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return starts[0]["status"], body


def _seeded_client(tmp_path: Path) -> tuple[TestClient, dict[str, str]]:
    settings = Settings(
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        export_dir=tmp_path / "library",
        job_dir=tmp_path / "jobs",
        mediacrawler_runtime_dir=tmp_path / "mediacrawler",
    )
    upgrade_database(settings.resolved_database_url)
    author_id = str(uuid4())
    content_id = str(uuid4())
    asset_id = str(uuid4())
    fixed_at = datetime(2026, 9, 5, 2, 3, 4, tzinfo=UTC)
    secret = "api-explorer-secret-sentinel"
    checksum = hashlib.sha256(ARCHIVE_BYTES).hexdigest()
    archive_path = settings.archive_dir / "sha256" / checksum[:2] / f"{checksum}.mp4"
    archive_path.parent.mkdir(parents=True)
    archive_path.write_bytes(ARCHIVE_BYTES)
    archive_path.chmod(0o444)
    database = Database(settings.resolved_database_url)
    try:
        with database.session() as session:
            session.add(
                Author(
                    id=author_id,
                    platform="bili",
                    remote_id="creator-safe",
                    display_name="Catalogue creator",
                    profile_url=f"https://example.test/profile?token={secret}",
                    raw={"secret": secret},
                )
            )
            session.add(
                Content(
                    id=content_id,
                    author_id=author_id,
                    platform="bili",
                    remote_type="video",
                    remote_id="BV-catalogue",
                    kind="video",
                    title="Catalogue title",
                    body="Catalogue body",
                    canonical_url=f"https://www.bilibili.com/video/BV-catalogue?token={secret}",
                    published_at=fixed_at,
                    remote_updated_at=fixed_at,
                    first_seen_at=fixed_at,
                    last_seen_at=fixed_at,
                    metrics={"secret": secret},
                    raw={"secret": secret},
                )
            )
            session.flush()
            session.add(
                Asset(
                    id=asset_id,
                    content_id=content_id,
                    platform="bili",
                    kind="video",
                    position=0,
                    generation=1,
                    status="verified",
                    source_url=f"https://cdn.example.test/video.mp4?signature={secret}",
                    locator={"secret": secret},
                    semantic_fingerprint="1" * 64,
                    locator_fingerprint="2" * 64,
                    mime_type="video/mp4",
                    size_bytes=len(ARCHIVE_BYTES),
                    checksum_sha256=checksum,
                    local_path=str(archive_path.absolute()),
                    verified_at=fixed_at,
                    last_error_message=secret,
                    raw={"secret": secret},
                )
            )
            session.add(
                ExportRecord(
                    id=str(uuid4()),
                    content_id=content_id,
                    exporter="emby",
                    exporter_version="1",
                    source_fingerprint="4" * 64,
                    output_path=str(tmp_path / secret / "library"),
                    status="succeeded",
                    exported_at=fixed_at,
                    error_message=secret,
                )
            )
    finally:
        database.dispose()
    return TestClient(create_api_app(settings)), {
        "author_id": author_id,
        "content_id": content_id,
        "asset_id": asset_id,
        "secret": secret,
        "archive_path": str(archive_path),
        "database_url": settings.resolved_database_url,
    }


def test_catalogue_lists_filters_and_details_are_safe(tmp_path: Path) -> None:
    client, ids = _seeded_client(tmp_path)

    contents = client.get(
        "/api/v1/contents",
        params={
            "platform": "bili",
            "kind": "video",
            "author_id": ids["author_id"],
            "archived": "true",
            "exported": "true",
            "q": "Catalogue",
        },
    )
    assert contents.status_code == 200
    assert [item["id"] for item in contents.json()] == [ids["content_id"]]
    assert contents.json()[0]["archive_state"] == "complete"

    assets = client.get(
        "/api/v1/assets",
        params={
            "platform": "bili",
            "kind": "video",
            "status": "verified",
            "author_id": ids["author_id"],
            "content_id": ids["content_id"],
            "archived": "true",
            "q": "Catalogue",
        },
    )
    assert assets.status_code == 200
    assert [item["id"] for item in assets.json()] == [ids["asset_id"]]
    assert assets.json()[0]["allowed_actions"] == ["preview", "download", "export_author"]

    content = client.get(f"/api/v1/contents/{ids['content_id']}")
    assert content.status_code == 200
    assert content.json()["body"] == "Catalogue body"
    assert content.json()["canonical_url"] == "https://www.bilibili.com/video/BV-catalogue"
    assert content.json()["exports"]["succeeded_count"] == 1

    asset = client.get(f"/api/v1/assets/{ids['asset_id']}")
    assert asset.status_code == 200
    assert asset.json()["content"]["id"] == ids["content_id"]
    assert asset.json()["archive"]["preview_url"] == f"/api/v1/assets/{ids['asset_id']}/archive"

    library = client.get("/api/v1/library", params={"platform": "bili", "q": "Catalogue"})
    assert library.status_code == 200
    assert [item["author_id"] for item in library.json()] == [ids["author_id"]]

    encoded = json.dumps(
        {
            "contents": contents.json(),
            "assets": assets.json(),
            "content": content.json(),
            "asset": asset.json(),
            "library": library.json(),
        },
        sort_keys=True,
    )
    assert ids["secret"] not in encoded
    assert str(tmp_path) not in encoded
    for forbidden in (
        '"raw"',
        '"locator"',
        '"source_url"',
        '"local_path"',
        '"etag"',
        '"last_modified"',
        '"last_error_message"',
        '"output_path"',
        '"error_message"',
    ):
        assert forbidden not in encoded


def test_catalogue_validation_and_not_found_are_fixed(tmp_path: Path) -> None:
    client, ids = _seeded_client(tmp_path)

    missing_content = client.get(f"/api/v1/contents/{uuid4()}")
    assert missing_content.status_code == 404
    assert missing_content.json() == {"detail": "catalog_content_not_found"}
    missing_asset = client.get(f"/api/v1/assets/{uuid4()}")
    assert missing_asset.status_code == 404
    assert missing_asset.json() == {"detail": "catalog_asset_not_found"}

    invalid_kind = client.get("/api/v1/assets", params={"kind": "private-kind"})
    assert invalid_kind.status_code == 422
    assert invalid_kind.json()["detail"] == "request_validation_failed"
    oversized = "sensitive-value-" * 20
    invalid_query = client.get("/api/v1/contents", params={"q": oversized})
    assert invalid_query.status_code == 422
    assert oversized not in invalid_query.text

    # The new exact detail route must not shadow the older two-segment
    # durable download endpoint.
    download = client.post(
        f"/api/v1/assets/{ids['asset_id']}/download",
        json={"enable_mediacrawler": False, "accept_mediacrawler_license": False},
    )
    assert download.status_code == 202


def test_archive_preview_get_head_and_single_ranges(tmp_path: Path) -> None:
    client, ids = _seeded_client(tmp_path)
    url = f"/api/v1/assets/{ids['asset_id']}/archive"

    full = client.get(url)
    assert full.status_code == 200
    assert full.content == ARCHIVE_BYTES
    assert full.headers["content-type"] == "video/mp4"
    assert full.headers["content-length"] == str(len(ARCHIVE_BYTES))
    assert full.headers["accept-ranges"] == "bytes"
    assert full.headers["etag"].startswith('"') and full.headers["etag"].endswith('"')
    assert full.headers["cache-control"] == "private, no-store"
    assert full.headers["content-security-policy"] == "sandbox; default-src 'none'"
    assert full.headers["cross-origin-resource-policy"] == "same-origin"
    assert full.headers["x-content-type-options"] == "nosniff"
    assert str(tmp_path) not in str(full.headers)

    head = client.head(url)
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["content-length"] == str(len(ARCHIVE_BYTES))
    assert head.headers["etag"] == full.headers["etag"]

    prefix = client.get(url, headers={"Range": "bytes=2-7"})
    assert prefix.status_code == 206
    assert prefix.content == ARCHIVE_BYTES[2:8]
    assert prefix.headers["content-range"] == f"bytes 2-7/{len(ARCHIVE_BYTES)}"
    assert prefix.headers["content-length"] == "6"

    open_ended = client.get(url, headers={"Range": "bytes=30-"})
    assert open_ended.status_code == 206
    assert open_ended.content == ARCHIVE_BYTES[30:]
    suffix = client.get(url, headers={"Range": "bytes=-5"})
    assert suffix.status_code == 206
    assert suffix.content == ARCHIVE_BYTES[-5:]

    uppercase_unit = client.get(url, headers={"Range": "BYTES=0-3"})
    assert uppercase_unit.status_code == 206
    assert uppercase_unit.content == ARCHIVE_BYTES[:4]

    matching_if_range = client.get(
        url,
        headers={"Range": "bytes=0-3", "If-Range": full.headers["etag"]},
    )
    assert matching_if_range.status_code == 206
    assert matching_if_range.content == ARCHIVE_BYTES[:4]
    for validator in ('"stale-checksum"', f"W/{full.headers['etag']}", "Sat, 05 Sep 2026 02:03:04 GMT"):
        ignored = client.get(url, headers={"Range": "bytes=0-3", "If-Range": validator})
        assert ignored.status_code == 200
        assert ignored.content == ARCHIVE_BYTES
        assert "content-range" not in ignored.headers
    ignored_unsatisfiable = client.get(
        url,
        headers={"Range": "bytes=99-", "If-Range": '"stale-checksum"'},
    )
    assert ignored_unsatisfiable.status_code == 200
    assert ignored_unsatisfiable.content == ARCHIVE_BYTES

    ranged_head = client.head(url, headers={"Range": "bytes=0-3"})
    assert ranged_head.status_code == 200
    assert ranged_head.content == b""
    assert "content-range" not in ranged_head.headers
    assert ranged_head.headers["content-length"] == str(len(ARCHIVE_BYTES))

    # Catalogue and archive reads never reset asset state or enqueue recovery.
    database = Database(ids["database_url"])
    try:
        with database.session() as session:
            persisted = session.get(Asset, ids["asset_id"])
            assert persisted is not None
            assert (
                persisted.status,
                persisted.local_path,
                persisted.checksum_sha256,
                persisted.size_bytes,
            ) == (
                "verified",
                ids["archive_path"],
                hashlib.sha256(ARCHIVE_BYTES).hexdigest(),
                len(ARCHIVE_BYTES),
            )
            assert session.scalar(select(func.count(Operation.id))) == 0
    finally:
        database.dispose()


def test_archive_preview_range_and_recovery_errors_are_safe(tmp_path: Path) -> None:
    client, ids = _seeded_client(tmp_path)
    url = f"/api/v1/assets/{ids['asset_id']}/archive"

    for value in ("bytes=99-", "bytes=0-1,4-5", "items=0-1", "bytes=-0"):
        rejected = client.get(url, headers={"Range": value})
        assert rejected.status_code == 416
        assert rejected.json() == {"detail": "asset_archive_range_unsatisfiable"}
        assert rejected.headers["content-range"] == f"bytes */{len(ARCHIVE_BYTES)}"
        assert ids["archive_path"] not in rejected.text

    ignored_head = client.head(url, headers={"Range": "bytes=99-"})
    assert ignored_head.status_code == 200
    assert ignored_head.content == b""
    assert "content-range" not in ignored_head.headers
    assert ignored_head.headers["content-length"] == str(len(ARCHIVE_BYTES))

    archive_path = Path(ids["archive_path"])
    archive_path.chmod(0o600)
    archive_path.unlink()
    missing = client.get(url)
    assert missing.status_code == 409
    assert missing.json() == {
        "detail": "asset_archive_missing",
        "recovery": {
            "operation_kind": "asset-download",
            "method": "POST",
            "url": f"/api/v1/assets/{ids['asset_id']}/download",
        },
    }
    assert ids["archive_path"] not in missing.text
    missing_with_range = client.get(url, headers={"Range": "bytes=99-"})
    assert missing_with_range.status_code == 409
    assert missing_with_range.json()["detail"] == "asset_archive_missing"
    assert missing_with_range.json()["recovery"]["url"] == f"/api/v1/assets/{ids['asset_id']}/download"
    missing_head = client.head(url)
    assert missing_head.status_code == 409
    assert missing_head.content == b""
    assert int(missing_head.headers["content-length"]) > 0


def test_archive_preview_not_ready_and_corrupt_errors_are_safe(tmp_path: Path) -> None:
    client, ids = _seeded_client(tmp_path)
    url = f"/api/v1/assets/{ids['asset_id']}/archive"
    database = Database(ids["database_url"])
    try:
        with database.session() as session:
            asset = session.get(Asset, ids["asset_id"])
            assert asset is not None
            asset.status = "discovered"
        not_ready = client.get(url)
        assert not_ready.status_code == 409
        assert not_ready.json()["detail"] == "asset_archive_not_ready"
        assert not_ready.json()["recovery"]["url"] == f"/api/v1/assets/{ids['asset_id']}/download"
        not_ready_with_range = client.get(url, headers={"Range": "bytes=99-"})
        assert not_ready_with_range.status_code == 409
        assert not_ready_with_range.json()["detail"] == "asset_archive_not_ready"

        with database.session() as session:
            asset = session.get(Asset, ids["asset_id"])
            assert asset is not None
            asset.status = "verified"
        archive_path = Path(ids["archive_path"])
        archive_path.chmod(0o600)
        archive_path.write_bytes(b"x" * len(ARCHIVE_BYTES))
        archive_path.chmod(0o444)

        corrupt = client.get(url, headers={"Range": "bytes=99-"})
        assert corrupt.status_code == 409
        assert corrupt.json()["detail"] == "asset_archive_invalid"
        assert corrupt.json()["recovery"]["url"] == f"/api/v1/assets/{ids['asset_id']}/download"
        assert ids["archive_path"] not in corrupt.text
    finally:
        database.dispose()


def test_archive_preview_unknown_mime_and_empty_file_are_bounded(tmp_path: Path) -> None:
    client, ids = _seeded_client(tmp_path)
    url = f"/api/v1/assets/{ids['asset_id']}/archive"
    database = Database(ids["database_url"])
    try:
        with database.session() as session:
            asset = session.get(Asset, ids["asset_id"])
            assert asset is not None
            asset.mime_type = "text/html"

        fallback = client.get(url)
        assert fallback.status_code == 200
        assert fallback.headers["content-type"] == "application/octet-stream"
        assert fallback.content == ARCHIVE_BYTES

        empty_checksum = hashlib.sha256(b"").hexdigest()
        empty_path = tmp_path / "archive" / "sha256" / empty_checksum[:2] / f"{empty_checksum}.mp4"
        empty_path.parent.mkdir(parents=True)
        empty_path.write_bytes(b"")
        empty_path.chmod(0o444)
        with database.session() as session:
            asset = session.get(Asset, ids["asset_id"])
            assert asset is not None
            asset.local_path = str(empty_path.absolute())
            asset.checksum_sha256 = empty_checksum
            asset.size_bytes = 0
            asset.mime_type = "video/mp4"

        empty = client.get(url)
        assert empty.status_code == 200
        assert empty.content == b""
        assert empty.headers["content-length"] == "0"
        empty_head = client.head(url)
        assert empty_head.status_code == 200
        assert empty_head.content == b""
        assert empty_head.headers["content-length"] == "0"
        empty_range = client.get(url, headers={"Range": "bytes=0-"})
        assert empty_range.status_code == 416
        assert empty_range.headers["content-range"] == "bytes */0"
    finally:
        database.dispose()


@pytest.mark.parametrize("fail_on", ["http.response.start", "http.response.body"])
def test_archive_response_closes_descriptor_when_asgi_send_fails(tmp_path: Path, fail_on: str) -> None:
    _, ids = _seeded_client(tmp_path)
    archive_path = Path(ids["archive_path"])
    preview = ArchivePreviewService(archive_path.parents[2]).open(
        ArchivePreviewSource(
            status="verified",
            local_path=archive_path,
            checksum_sha256=hashlib.sha256(ARCHIVE_BYTES).hexdigest(),
            size_bytes=len(ARCHIVE_BYTES),
            mime_type="video/mp4",
        )
    )
    response = _ArchiveStreamingResponse(preview, status_code=200, headers={})

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == fail_on:
            raise OSError("injected send failure")

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/archive",
        "raw_path": b"/archive",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("testclient", 50_000),
        "server": ("testserver", 80),
        "state": {},
    }

    with pytest.raises(ClientDisconnect):
        asyncio.run(response(scope, receive, send))
    assert preview.closed


def test_archive_head_errors_emit_no_asgi_body(tmp_path: Path) -> None:
    client, ids = _seeded_client(tmp_path)

    missing_messages = _asgi_exchange(
        client.app,
        "HEAD",
        f"/api/v1/assets/{uuid4()}/archive",
    )
    assert _asgi_status_and_body(missing_messages) == (404, b"")

    invalid_messages = _asgi_exchange(
        client.app,
        "HEAD",
        "/api/v1/assets/not-a-uuid/archive",
    )
    assert _asgi_status_and_body(invalid_messages) == (422, b"")

    database = Database(ids["database_url"])
    try:
        with database.session() as session:
            asset = session.get(Asset, ids["asset_id"])
            assert asset is not None
            asset.status = "discovered"
    finally:
        database.dispose()
    not_ready_messages = _asgi_exchange(
        client.app,
        "HEAD",
        f"/api/v1/assets/{ids['asset_id']}/archive",
    )
    assert _asgi_status_and_body(not_ready_messages) == (409, b"")
