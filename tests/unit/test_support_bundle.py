from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import text

import media_sync.application.support_bundle as support_bundle_module
from media_sync.application.support_bundle import (
    MAX_RECENT_ERROR_CODES,
    MAX_SUPPORT_BUNDLE_BYTES,
    SUPPORT_BUNDLE_SCHEMA_VERSION,
    SupportBundleError,
    SupportBundleService,
)
from media_sync.infrastructure.db.database import Database
from media_sync.infrastructure.db.migration import upgrade_database
from media_sync.infrastructure.db.models import (
    OPERATION_KINDS,
    OPERATION_STATES,
    Account,
    Asset,
    Author,
    Content,
    Job,
    Operation,
    Subscription,
)

NOW = datetime(2026, 9, 4, 1, 2, 3, tzinfo=UTC)
REVISION = "0007_media_server_operations"


def _database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    database_url = _database_url(tmp_path / "support.sqlite3")
    upgrade_database(database_url)
    instance = Database(database_url)
    try:
        yield instance
    finally:
        instance.dispose()


def _service(
    database: Database,
    *,
    application_version: str = "0.1.0",
    expected_revision: str = REVISION,
) -> SupportBundleService:
    return SupportBundleService(
        database,
        application_version=application_version,
        expected_revision=expected_revision,
        clock=lambda: NOW,
    )


def _operation(
    number: int,
    *,
    kind: str = "pipeline-run",
    state: str = "failed_terminal",
    error_code: str | None = "pipeline_run_failed",
    requested_at: datetime = NOW,
    result_summary: dict[str, object] | None = None,
) -> Operation:
    terminal = state not in {"queued", "running"}
    return Operation(
        id=str(UUID(int=number)),
        kind=kind,
        state=state,
        requested_at=requested_at,
        finished_at=requested_at if terminal else None,
        request_fingerprint=f"{number:064x}"[-64:],
        correlation_id=str(UUID(int=number + 10_000)),
        error_code=error_code,
        result_summary=result_summary or {},
    )


def _decoded(service: SupportBundleService) -> tuple[bytes, dict[str, object]]:
    encoded = service.build()
    return encoded, json.loads(encoded)


def test_bundle_has_only_closed_keys_and_aggregate_counts(database: Database) -> None:
    with database.session() as session:
        account = Account(platform="xhs", display_name="primary", auth_status="authenticated")
        author = Author(platform="xhs", remote_id="author-1", display_name="Author One")
        session.add_all([account, author])
        session.flush()
        subscription = Subscription(account_id=account.id, author_id=author.id)
        content = Content(
            author_id=author.id,
            platform="xhs",
            remote_id="content-1",
            kind="video",
        )
        session.add_all([subscription, content])
        session.flush()
        session.add_all(
            [
                Asset(
                    content_id=content.id,
                    platform="xhs",
                    kind="video",
                    semantic_fingerprint="a" * 64,
                    locator_fingerprint="b" * 64,
                ),
                Job(job_type="asset.download", natural_key="job-1"),
                _operation(1, state="queued", error_code=None),
                _operation(2, error_code="pipeline_run_failed"),
                _operation(3, kind="asset-download", state="failed_retryable", error_code="download_failed"),
                _operation(4, kind="emby-export", state="interrupted", error_code="pipeline_run_failed"),
            ]
        )

    encoded, bundle = _decoded(_service(database))

    assert len(encoded) <= MAX_SUPPORT_BUNDLE_BYTES
    assert set(bundle) == {
        "schema_version",
        "generated_at",
        "project",
        "build",
        "database",
        "entity_counts",
        "operations",
    }
    assert bundle["schema_version"] == SUPPORT_BUNDLE_SCHEMA_VERSION
    assert bundle["generated_at"] == "2026-09-04T01:02:03+00:00"
    assert bundle["project"] == {"name": "media-sync", "version": "0.1.0"}
    assert bundle["build"] == {"expected_schema_revision": REVISION}
    assert bundle["database"] == {
        "reachable": True,
        "ready": True,
        "schema_revision": REVISION,
        "revision_matches": True,
    }
    assert bundle["entity_counts"] == {
        "accounts": 1,
        "subscriptions": 1,
        "authors": 1,
        "contents": 1,
        "assets": 1,
        "jobs": 1,
        "operations": 4,
    }
    operations = bundle["operations"]
    assert isinstance(operations, dict)
    state_counts = {item["state"]: item["count"] for item in operations["state_counts"]}
    kind_counts = {item["kind"]: item["count"] for item in operations["kind_counts"]}
    assert set(state_counts) == OPERATION_STATES
    assert set(kind_counts) == OPERATION_KINDS
    assert state_counts | {} == {
        "cancelled": 0,
        "failed_retryable": 1,
        "failed_terminal": 1,
        "interrupted": 1,
        "queued": 1,
        "running": 0,
        "succeeded": 0,
    }
    assert kind_counts | {} == {
        "account-login": 0,
        "asset-download": 1,
        "emby-export": 1,
        "media-server-probe": 0,
        "media-server-scan": 0,
        "pipeline-run": 2,
        "scheduler-run": 0,
    }
    assert operations["recent_error_counts"] == [
        {"error_code": "pipeline_run_failed", "count": 2},
        {"error_code": "download_failed", "count": 1},
    ]
    assert all(set(item) == {"state", "count"} for item in operations["state_counts"])
    assert all(set(item) == {"kind", "count"} for item in operations["kind_counts"])
    assert all(set(item) == {"error_code", "count"} for item in operations["recent_error_counts"])


def test_bundle_never_reads_sensitive_row_fields(database: Database) -> None:
    sentinel = "private-sentinel-value"
    with database.session() as session:
        account = Account(
            platform="xhs",
            display_name="sensitive",
            login_method="cookie",
            credential_ref=f"keyring:{sentinel}",
            profile_path=rf"C:\Users\private\{sentinel}",
        )
        author = Author(
            platform="xhs",
            remote_id="author-sensitive",
            display_name="Sensitive Author",
            profile_url=f"https://example.invalid/?token={sentinel}",
            raw={"traceback": sentinel},
        )
        session.add_all([account, author])
        session.flush()
        content = Content(
            author_id=author.id,
            platform="xhs",
            remote_id="content-sensitive",
            kind="video",
            canonical_url=f"https://example.invalid/content?secret={sentinel}",
            raw={"qr_material": sentinel},
        )
        session.add(content)
        session.flush()
        session.add_all(
            [
                Asset(
                    content_id=content.id,
                    platform="xhs",
                    kind="video",
                    source_url=f"https://example.invalid/media?cookie={sentinel}",
                    local_path=f"/private/{sentinel}",
                    locator={"authorization": sentinel},
                    semantic_fingerprint="c" * 64,
                    locator_fingerprint="d" * 64,
                ),
                Job(
                    job_type="asset.download",
                    natural_key="sensitive-job",
                    payload={"session_token": sentinel},
                    last_error_message=f"RuntimeError: {sentinel}",
                ),
                _operation(
                    20,
                    error_code="pipeline_run_failed",
                    result_summary={
                        "request": {"url": f"https://example.invalid/?token={sentinel}"},
                        "path": rf"\\server\share\{sentinel}",
                        "traceback": sentinel,
                    },
                ),
            ]
        )

    encoded = _service(database).build()
    lowered = encoded.lower()

    assert sentinel.encode() not in encoded
    assert b"example.invalid" not in encoded
    assert b"traceback" not in lowered
    assert b"authorization" not in lowered
    assert b"session_token" not in lowered


def test_recent_errors_are_bounded_ranked_and_ignore_older_rows(database: Database) -> None:
    with database.session() as session:
        session.add(_operation(100, error_code="old_failure", requested_at=NOW - timedelta(days=1)))
        for index in range(200):
            session.add(
                _operation(
                    101 + index,
                    error_code="recent_failure",
                    requested_at=NOW + timedelta(seconds=index),
                )
            )
        for index in range(MAX_RECENT_ERROR_CODES + 1):
            session.add(
                _operation(
                    1_000 + index,
                    error_code=f"bounded_{index:02d}",
                    requested_at=NOW + timedelta(hours=1, seconds=index),
                )
            )

    _, bundle = _decoded(_service(database))
    operations = bundle["operations"]
    assert isinstance(operations, dict)
    errors = operations["recent_error_counts"]

    assert len(errors) == MAX_RECENT_ERROR_CODES
    assert {item["error_code"] for item in errors}.isdisjoint({"old_failure"})
    assert errors == sorted(errors, key=lambda item: (-item["count"], item["error_code"]))


def test_safe_redacted_secret_classification_is_allowed(database: Database) -> None:
    with database.session() as session:
        session.add(_operation(30, error_code="locator_secret_forbidden"))

    _, bundle = _decoded(_service(database))
    operations = bundle["operations"]
    assert isinstance(operations, dict)
    assert operations["recent_error_counts"] == [{"error_code": "locator_secret_forbidden", "count": 1}]


@pytest.mark.parametrize(
    "unsafe_code",
    [
        "https://example.invalid/?token=private-sentinel",
        "query?secret=private-sentinel",
        r"C:\Users\private\sentinel",
        "/home/private/sentinel",
        r"\\server\share\sentinel",
        "qr_material_leaked",
        "credential_material_leaked",
        "raw_traceback_leaked",
        "private_sentinel",
    ],
)
def test_unsafe_error_codes_fail_closed_without_reflection(database: Database, unsafe_code: str) -> None:
    with database.session() as session:
        session.add(_operation(40, error_code=unsafe_code))

    with pytest.raises(SupportBundleError) as captured:
        _service(database).build()

    assert captured.value.code == "support_bundle_content_unsafe"
    assert unsafe_code not in str(captured.value)
    assert unsafe_code not in repr(captured.value)
    assert "private-sentinel" not in str(captured.value)
    assert "private-sentinel" not in repr(captured.value)


def test_revision_mismatch_is_reported_without_becoming_unreachable(database: Database) -> None:
    with database.session() as session:
        session.execute(text("UPDATE alembic_version SET version_num = '0005_asset_refresh_sources'"))

    _, bundle = _decoded(_service(database))

    assert bundle["database"] == {
        "reachable": True,
        "ready": False,
        "schema_revision": "0005_asset_refresh_sources",
        "revision_matches": False,
    }


def test_malformed_database_revision_fails_without_reflection(database: Database) -> None:
    with database.session() as session:
        session.execute(text("UPDATE alembic_version SET version_num = 'private-sentinel-revision'"))

    with pytest.raises(SupportBundleError) as captured:
        _service(database).build()

    assert captured.value.code == "support_bundle_database_failed"
    assert "private-sentinel" not in str(captured.value)
    assert "private-sentinel" not in repr(captured.value)


def test_database_failure_is_fixed_and_does_not_expose_database_url(database: Database) -> None:
    database.drop_schema()

    with pytest.raises(SupportBundleError) as captured:
        _service(database).build()

    assert captured.value.code == "support_bundle_database_failed"
    assert "support.sqlite3" not in str(captured.value)
    assert "support.sqlite3" not in repr(captured.value)


@pytest.mark.parametrize(
    "application_version",
    ["1.0.0-secret", "1.0.0-qr", "1.0.0-traceback", "1.0.0-private-sentinel"],
)
def test_encoded_second_pass_rejects_sensitive_build_values(
    database: Database,
    application_version: str,
) -> None:
    with pytest.raises(SupportBundleError) as captured:
        _service(database, application_version=application_version).build()

    assert captured.value.code == "support_bundle_content_unsafe"
    assert application_version not in str(captured.value)
    assert application_version not in repr(captured.value)


@pytest.mark.parametrize(
    "value",
    [
        "https://example.invalid/version?secret=value",
        r"C:\private\version",
        "/private/version",
        r"\\server\share\version",
        " version-with-whitespace ",
    ],
)
def test_invalid_configuration_is_rejected_without_reflection(database: Database, value: str) -> None:
    with pytest.raises(SupportBundleError) as captured:
        _service(database, application_version=value)

    assert captured.value.code == "support_bundle_configuration_invalid"
    assert value not in str(captured.value)
    assert value not in repr(captured.value)


def test_invalid_clock_is_fixed_and_does_not_reflect_exception(database: Database) -> None:
    def broken_clock() -> datetime:
        raise RuntimeError("private-sentinel-clock")

    service = SupportBundleService(
        database,
        application_version="0.1.0",
        expected_revision=REVISION,
        clock=broken_clock,
    )
    with pytest.raises(SupportBundleError) as captured:
        service.build()

    assert captured.value.code == "support_bundle_clock_invalid"
    assert "private-sentinel" not in str(captured.value)
    assert "private-sentinel" not in repr(captured.value)


def test_naive_clock_is_rejected(database: Database) -> None:
    service = SupportBundleService(
        database,
        application_version="0.1.0",
        expected_revision=REVISION,
        clock=lambda: NOW.replace(tzinfo=None),
    )

    with pytest.raises(SupportBundleError) as captured:
        service.build()

    assert captured.value.code == "support_bundle_clock_invalid"


def test_encoded_size_limit_fails_closed(database: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(support_bundle_module, "MAX_SUPPORT_BUNDLE_BYTES", 1)

    with pytest.raises(SupportBundleError) as captured:
        _service(database).build()

    assert captured.value.code == "support_bundle_too_large"
