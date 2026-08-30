"""Persistence defense-in-depth tests for credential and raw-data sinks."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from media_sync.infrastructure.db import (
    AccountRepository,
    AssetRepository,
    AssetUpsert,
    AuthorRepository,
    AuthorUpsert,
    ContentUpsert,
    Database,
    JobRepository,
    LoginSessionRepository,
    SubscriptionRepository,
    SyncRunRepository,
)
from media_sync.infrastructure.db.models import Asset, Author, Content, Job, LoginSession, RunEvent, SyncRun
from media_sync.media.locator import AdapterRefreshLocator, parse_locator
from media_sync.security import REDACTED, InvalidSecretReferenceError

SENTINEL = "sentinel-secret-value"


def _database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def test_repository_rejects_inline_account_credentials(tmp_path: Path) -> None:
    database = Database(_database_url(tmp_path / "rejected.sqlite3"))
    database.create_schema()
    try:
        with pytest.raises(InvalidSecretReferenceError), database.session() as session:
            AccountRepository(session).create(
                platform="bili",
                display_name="unsafe",
                login_method="cookie",
                credential_ref=f"SESSDATA={SENTINEL}; bili_jct={SENTINEL}",
            )

        with database.session() as session:
            assert AccountRepository(session).list() == []
    finally:
        database.dispose()


def test_all_json_error_and_url_sinks_redact_before_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "redacted.sqlite3"
    database = Database(_database_url(database_path))
    database.create_schema()
    now = datetime(2026, 8, 30, tzinfo=UTC)
    try:
        with database.session() as session:
            account = AccountRepository(session).create(
                platform="bili",
                display_name="safe-reference",
                login_method="cookie",
                credential_ref="env:MEDIA_SYNC_TEST_COOKIE",
            )
            author, contents = AuthorRepository(session).upsert_with_contents(
                AuthorUpsert(
                    platform="bili",
                    remote_id="author-1",
                    display_name="Author",
                    profile_url=f"https://example.test/author?token={SENTINEL}",
                    raw={
                        "nested": {"cookie": SENTINEL},
                        "credential_path_url": f"https://media.test/token/{SENTINEL}/avatar.jpg",
                    },
                ),
                [
                    ContentUpsert(
                        remote_id="content-1",
                        kind="video",
                        body=f"request token={SENTINEL}",
                        canonical_url=f"https://example.test/content?xsec_token={SENTINEL}",
                        published_at=now,
                        raw={"headers": {"Authorization": f"Bearer {SENTINEL}"}},
                    )
                ],
            )
            content = contents[0]
            AssetRepository(session).upsert_for_content(
                content.id,
                AssetUpsert(
                    platform="bili",
                    kind="video",
                    position=0,
                    source_url=f"https://media.test/video.mp4?signature={SENTINEL}&quality=1080",
                    raw={"cookie": SENTINEL},
                ),
            )
            subscription = SubscriptionRepository(session).create(account_id=account.id, author_id=author.id)
            login_session = LoginSessionRepository(session).create(
                account_id=account.id,
                method="cookie",
                public_payload={
                    "cookie": SENTINEL,
                    "api_key": f"{SENTINEL}-api",
                    "access_key": f"{SENTINEL}-access",
                    "aws_access_key_id": f"{SENTINEL}-aws-snake",
                    "AWSAccessKeyId": f"{SENTINEL}-aws-camel",
                    "x-api-key": f"{SENTINEL}-x-api",
                    "key": "ordinary-key",
                    "public_key": "ordinary-public-key",
                    "key_id": "ordinary-key-id",
                },
            )
            run = SyncRunRepository(session).create(
                subscription_id=subscription.id,
                manifest={"authorization": SENTINEL},
            )
            run_repository = SyncRunRepository(session)
            run_repository.set_status(
                run.id,
                "claimed",
                expected_status="queued",
                error_message=f"token={SENTINEL}",
            )
            run_repository.add_event(
                run.id,
                "safe_event",
                message=f"Cookie: {SENTINEL}",
                payload={"secret": SENTINEL},
            )
            job_repository = JobRepository(session)
            job = job_repository.enqueue(
                job_type="sync",
                natural_key="secret-sink-test",
                payload={"nested": {"password": SENTINEL}},
                run_id=run.id,
                available_at=now,
            )
            claimed = job_repository.claim_next(worker_id="worker", now=now)
            assert claimed is not None and claimed.lease_token is not None
            job_repository.start(
                claimed.id,
                worker_id="worker",
                lease_token=claimed.lease_token,
                now=now,
            )
            job_repository.fail(
                claimed.id,
                worker_id="worker",
                lease_token=claimed.lease_token,
                retryable=True,
                error_code="temporary",
                error_message=f"Authorization: Bearer {SENTINEL}",
                now=now,
            )

            author_id = author.id
            content_id = content.id
            login_session_id = login_session.id
            run_id = run.id
            job_id = job.id

        with database.session() as session:
            stored_author = session.get(Author, author_id)
            stored_content = session.get(Content, content_id)
            stored_asset = session.scalar(select(Asset).where(Asset.content_id == content_id))
            stored_login = session.get(LoginSession, login_session_id)
            stored_run = session.get(SyncRun, run_id)
            stored_events = list(session.scalars(select(RunEvent).where(RunEvent.run_id == run_id)))
            stored_job = session.get(Job, job_id)

            assert stored_author is not None and stored_author.raw["nested"]["cookie"] == REDACTED
            assert SENTINEL not in stored_author.raw["credential_path_url"]
            assert "%5BREDACTED%5D" in stored_author.raw["credential_path_url"]
            assert stored_author.profile_url is not None and SENTINEL not in stored_author.profile_url
            assert stored_content is not None and SENTINEL not in (stored_content.body or "")
            assert stored_content.canonical_url is not None and SENTINEL not in stored_content.canonical_url
            assert stored_asset is not None and SENTINEL not in (stored_asset.source_url or "")
            assert isinstance(parse_locator(stored_asset.locator), AdapterRefreshLocator)
            assert SENTINEL not in str(stored_asset.locator)
            assert stored_login is not None and stored_login.public_payload["cookie"] == REDACTED
            assert stored_login.public_payload["api_key"] == REDACTED
            assert stored_login.public_payload["access_key"] == REDACTED
            assert stored_login.public_payload["aws_access_key_id"] == REDACTED
            assert stored_login.public_payload["AWSAccessKeyId"] == REDACTED
            assert stored_login.public_payload["x-api-key"] == REDACTED
            assert stored_login.public_payload["key"] == "ordinary-key"
            assert stored_login.public_payload["public_key"] == "ordinary-public-key"
            assert stored_login.public_payload["key_id"] == "ordinary-key-id"
            assert stored_run is not None and stored_run.manifest["authorization"] == REDACTED
            assert stored_run.error_message is not None and SENTINEL not in stored_run.error_message
            assert all(SENTINEL not in (event.message or "") for event in stored_events)
            assert stored_job is not None and stored_job.payload["nested"]["password"] == REDACTED
            assert stored_job.last_error_message is not None and SENTINEL not in stored_job.last_error_message
    finally:
        database.dispose()

    assert SENTINEL.encode() not in database_path.read_bytes()


@pytest.mark.parametrize(
    ("label", "path"),
    [
        ("raw", f"/token/{SENTINEL}/video.mp4"),
        ("encoded", f"/token%2F{SENTINEL}%2Fvideo.mp4"),
        ("double-encoded", f"/token%252F{SENTINEL}%252Fvideo.mp4"),
    ],
)
def test_credential_bearing_asset_paths_never_reach_orm_or_sqlite(
    tmp_path: Path,
    label: str,
    path: str,
) -> None:
    database_path = tmp_path / f"path-secret-{label}.sqlite3"
    database = Database(_database_url(database_path))
    database.create_schema()
    try:
        with database.session() as session:
            author, contents = AuthorRepository(session).upsert_with_contents(
                AuthorUpsert(platform="bili", remote_id="author-path", display_name="Author"),
                [ContentUpsert(remote_id="content-path", kind="video")],
            )
            stored = AssetRepository(session).upsert_for_content(
                contents[0].id,
                AssetUpsert(
                    platform="bili",
                    kind="video",
                    position=0,
                    source_url=f"https://media.test{path}",
                ),
            )
            asset_id = stored.id
            assert author.id

        with database.session() as session:
            stored = session.get(Asset, asset_id)
            assert stored is not None
            assert stored.source_url is None
            assert isinstance(parse_locator(stored.locator), AdapterRefreshLocator)
            assert SENTINEL not in str(stored.locator)
    finally:
        database.dispose()

    assert SENTINEL.encode() not in database_path.read_bytes()


def test_infrastructure_upsert_repr_hides_secret_adjacent_fields() -> None:
    values = (
        AuthorUpsert(
            platform="bili",
            remote_id="author-1",
            display_name="Author",
            profile_url=f"https://example.test?token={SENTINEL}",
            raw={"cookie": SENTINEL},
        ),
        ContentUpsert(
            remote_id="content-1",
            kind="video",
            body=SENTINEL,
            canonical_url=f"https://example.test?token={SENTINEL}",
            raw={"cookie": SENTINEL},
        ),
        AssetUpsert(
            platform="bili",
            kind="video",
            position=0,
            source_url=f"https://example.test?token={SENTINEL}",
            locator={"token": SENTINEL},
            raw={"cookie": SENTINEL},
        ),
    )

    assert SENTINEL not in repr(values)
