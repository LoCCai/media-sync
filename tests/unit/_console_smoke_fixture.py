"""Create an explicitly empty disposable dataset for manual browser smoke tests.

No platform request, real QR challenge, operator credential or auth bypass is
created. Serve this fixture with the ordinary authenticated CLI after building
the frontend. The generated picture/video is not live qualification evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import zlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from media_sync.config import Settings
from media_sync.infrastructure.db import Account, Asset, Author, Content, Database, LoginSessionRepository
from media_sync.infrastructure.db.migration import upgrade_database


def fixture_png() -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack("!I", len(payload)) + kind + payload + struct.pack("!I", zlib.crc32(kind + payload))

    width, height = 160, 90
    pixels = b"".join(b"\0" + b"".join(bytes((x, y * 2, 120)) for x in range(width)) for y in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(pixels))
        + chunk(b"IEND", b"")
    )


def seed_fixture(root: Path, *, video: bool = False) -> dict[str, str]:
    if not root.is_absolute() or root.is_symlink() or (root.exists() and (not root.is_dir() or any(root.iterdir()))):
        raise ValueError("console_fixture_requires_empty_absolute_directory")
    root.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        database_url=f"sqlite:///{root / 'state' / 'media-sync.sqlite3'}",
        state_dir=root / "state",
        archive_dir=root / "archive",
        export_dir=root / "library",
        job_dir=root / "jobs",
        mediacrawler_runtime_dir=root / "mediacrawler",
        _env_file=None,
    )
    media: list[tuple[str, str, bytes]] = [("image", "png", fixture_png())]
    if video:
        executable = shutil.which("ffmpeg")
        if executable is None:
            raise ValueError("console_fixture_ffmpeg_unavailable")
        generated = root / "synthetic.mp4"
        subprocess.run(
            [
                executable,
                "-nostdin",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=160x90:rate=10",
                "-t",
                "2",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(generated),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        media.append(("video", "mp4", generated.read_bytes()))
    upgrade_database(settings.resolved_database_url)
    database = Database(settings.resolved_database_url)
    routes: dict[str, str] = {}
    try:
        with database.session() as session:
            account = Account(
                platform="bili", adapter="mediacrawler", display_name="Offline fixture", login_method="qr"
            )
            author = Author(platform="bili", remote_id="fixture-only", display_name="Offline fixture author")
            session.add_all([account, author])
            session.flush()
            login = LoginSessionRepository(session).create(account_id=account.id, method="qr", challenge_kind="qr")
            login.status = "waiting_user"
            qr_path = settings.resolved_mediacrawler_runtime_dir / "accounts" / "bili" / account.id / "login-qr.png"
            qr_path.parent.mkdir(parents=True)
            qr_path.write_bytes(fixture_png())
            routes["synthetic_qr_image"] = f"/api/v1/login-sessions/{login.id}/qr.png"
            now = datetime.now(UTC)
            for kind, extension, payload in media:
                checksum = hashlib.sha256(payload).hexdigest()
                archive = settings.archive_dir / "sha256" / checksum[:2] / f"{checksum}.{extension}"
                archive.parent.mkdir(parents=True, exist_ok=True)
                archive.write_bytes(payload)
                archive.chmod(0o444)
                content = Content(
                    author_id=author.id,
                    platform="bili",
                    remote_type=kind,
                    remote_id=f"fixture-{kind}",
                    kind="video" if kind == "video" else "article",
                    title=f"Offline synthetic {kind}",
                    body="Disposable local fixture; no platform capture or live qualification.",
                    published_at=now,
                )
                session.add(content)
                session.flush()
                asset = Asset(
                    id=str(uuid4()),
                    content_id=content.id,
                    platform="bili",
                    kind=kind,
                    semantic_fingerprint="1" * 64,
                    locator_fingerprint="2" * 64,
                    mime_type="video/mp4" if kind == "video" else "image/png",
                    size_bytes=len(payload),
                    checksum_sha256=checksum,
                    local_path=str(archive),
                    status="verified",
                    verified_at=now,
                )
                session.add(asset)
                routes[f"{kind}_archive"] = f"/api/v1/assets/{asset.id}/archive"
    finally:
        database.dispose()
    (root / "fixture-routes.json").write_text(json.dumps(routes, indent=2) + "\n", encoding="utf-8")
    return routes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="An empty absolute disposable directory.")
    parser.add_argument("--video", action="store_true", help="Generate a two-second synthetic video with ffmpeg.")
    arguments = parser.parse_args()
    print(json.dumps(seed_fixture(arguments.root, video=arguments.video)))


if __name__ == "__main__":
    main()
