"""Safety and offline-only properties of the manual browser fixture seeder."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
from _console_smoke_fixture import fixture_png, seed_fixture
from sqlalchemy import select

from media_sync.application.archive_preview import ArchivePreviewService, ArchivePreviewSource
from media_sync.infrastructure.db import Account, Asset, Database


def test_console_fixture_has_only_local_synthetic_media_and_no_live_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "fixture"
    outside = tmp_path / "outside.sqlite3"
    outside.write_bytes(b"unrelated sentinel database")
    monkeypatch.setenv("MEDIA_SYNC_DATABASE_URL", f"sqlite:///{outside}")
    routes = seed_fixture(root)

    assert outside.read_bytes() == b"unrelated sentinel database"
    assert set(routes) == {"synthetic_qr_image", "image_archive"}
    assert all(route.startswith("/api/v1/") and "?" not in route for route in routes.values())
    database = Database(f"sqlite:///{root / 'state' / 'media-sync.sqlite3'}")
    try:
        with database.session() as session:
            account = session.scalar(select(Account))
            assert account is not None
            assert account.auth_status == "unknown"
            assert account.credential_ref is None
            asset = session.scalar(select(Asset))
            assert asset is not None and asset.local_path is not None
            assert asset.source_url is None
            assert asset.locator == {}
            assert Path(asset.local_path).read_bytes() == fixture_png()
            assert asset.checksum_sha256 == hashlib.sha256(fixture_png()).hexdigest()
    finally:
        database.dispose()


def test_console_fixture_refuses_existing_data_or_relative_target(tmp_path: Path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    sentinel = existing / "keep.txt"
    sentinel.write_text("user-owned", encoding="utf-8")

    for target in (existing, Path("relative-fixture")):
        with pytest.raises(ValueError, match="console_fixture_requires_empty_absolute_directory"):
            seed_fixture(target)

    assert sentinel.read_text(encoding="utf-8") == "user-owned"
    assert list(existing.iterdir()) == [sentinel]


@pytest.mark.parametrize("video", [False, True])
def test_console_fixture_archives_pass_real_immutable_preview(tmp_path: Path, video: bool) -> None:
    if video and shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg unavailable for optional synthetic video fixture")
    root = tmp_path / "fixture"
    seed_fixture(root, video=video)
    database = Database(f"sqlite:///{root / 'state' / 'media-sync.sqlite3'}")
    preview_service = ArchivePreviewService(root / "archive")
    try:
        with database.session() as session:
            assets = list(session.scalars(select(Asset)))
            assert {asset.kind for asset in assets} == ({"image", "video"} if video else {"image"})
            for asset in assets:
                assert asset.local_path is not None
                path = Path(asset.local_path)
                assert not path.stat().st_mode & 0o222
                source = ArchivePreviewSource(
                    status=asset.status,
                    local_path=asset.local_path,
                    checksum_sha256=asset.checksum_sha256,
                    size_bytes=asset.size_bytes,
                    mime_type=asset.mime_type,
                )
                with preview_service.open(source) as preview:
                    assert preview.media_type == ("video/mp4" if asset.kind == "video" else "image/png")
                    assert preview.content_length == asset.size_bytes
                    assert b"".join(preview.iter_bytes()) == path.read_bytes()
    finally:
        database.dispose()
