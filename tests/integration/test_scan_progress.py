"""Only committed, replay-verified Bili coverage becomes scan evidence."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from media_sync.config import Settings
from media_sync.domain import AuthorSnapshot, ContentKind, ContentSnapshot, Platform
from media_sync.infrastructure.db import (
    AccountRepository,
    AuthorRepository,
    AuthorUpsert,
    Database,
    LeaseLostError,
    MediaCrawlerIngestionService,
    RepositoryError,
    SubscriptionRepository,
    SyncRunRepository,
)
from media_sync.infrastructure.db.models import Content, Subscription, SubscriptionScanProgress, SyncRun
from media_sync.infrastructure.db.scan_progress_repository import MAX_PROGRESS_NUMBER, scan_progress_payload
from media_sync.integrations.mediacrawler.bilibili_multifeed import (
    BiliDynamicPage,
    BiliDynamicSnapshotRef,
    BiliDynamicUnit,
    BiliMultiFeedCoverage,
    BiliMultiFeedState,
    state_for_cursor,
    state_from_cursor,
    wrap_upload_coverage,
)
from media_sync.integrations.mediacrawler.bilibili_scan import (
    BiliIdentity,
    BiliPage,
    BiliScanCoverage,
    BiliScanState,
    BiliScanUnit,
)
from media_sync.integrations.mediacrawler.normalizers import NormalizedMediaRecord
from media_sync.integrations.mediacrawler.subscription_policy import MediaCrawlerSubscriptionPolicy

SHA = "b" * 40


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    database = Database(f"sqlite:///{(tmp_path / 'progress.sqlite3').as_posix()}")
    database.create_schema()
    yield database
    database.dispose()


def seed(
    database: Database, *, platform: str = "bili", history: bool = True, scope: str | None = None, max_items: int = 30
) -> str:
    with database.session() as session:
        account = AccountRepository(session).create(
            platform=platform, adapter="mediacrawler", display_name=str(uuid4())
        )
        author = AuthorRepository(session).upsert(
            AuthorUpsert(platform=platform, remote_id="123", display_name="Creator")
        )
        subscription = SubscriptionRepository(session).create(
            account_id=account.id, author_id=author.id, max_items=max_items
        )
        subscription.watermarked_at = datetime(2026, 9, 6, tzinfo=UTC)
        if platform == "bili":
            subscription.policy = {
                "mediacrawler": MediaCrawlerSubscriptionPolicy(False, 1, True, bili_scope=scope).to_payload()
            }
            state = state_for_cursor(
                None,
                account_id=UUID(account.id),
                author_fingerprint_sha256=hashlib.sha256(b"123").hexdigest(),
                upstream_sha=SHA,
                scope=scope,
            )
            if history:
                if isinstance(state, BiliMultiFeedState):
                    state = replace(
                        state,
                        uploads=replace(state.uploads, next_lane="history"),
                        dynamics=replace(state.dynamics, next_lane="history"),
                    )
                else:
                    state = replace(state, next_lane="history")
            subscription.cursor = {"value": state.to_cursor()}
        return subscription.id


def begin(database: Database, subscription_id: str) -> tuple[str, int, str]:
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        repository = SyncRunRepository(session)
        run = repository.create(
            subscription_id=subscription_id,
            cursor_before=subscription.cursor,
            checkpoint_revision_before=subscription.checkpoint_revision,
            manifest={"upstream_sha": SHA},
        )
        for before, after in zip(("queued", "claimed", "running"), ("claimed", "running", "ingesting"), strict=True):
            repository.set_status(run.id, after, expected_status=before)
        return run.id, subscription.checkpoint_revision, subscription.cursor["value"]


def record(identity: BiliIdentity) -> NormalizedMediaRecord:
    author = AuthorSnapshot(platform=Platform.BILI, remote_id="123", display_name="Creator")
    return NormalizedMediaRecord(
        author,
        ContentSnapshot(
            platform=Platform.BILI,
            remote_id=identity.aid,
            author_remote_id="123",
            kind=ContentKind.VIDEO,
            title="Synthetic",
            published_at=datetime.fromtimestamp(identity.pubdate, UTC),
        ),
        (),
    )


def upload_coverage(cursor: str, *, size: int = 1, maximum: int = 30) -> BiliScanCoverage:
    state = state_from_cursor(cursor)
    assert isinstance(state, BiliScanState)
    unit = BiliScanUnit(state, maximum)
    items = tuple(BiliIdentity(str(n), f"BV{n:010d}", 100000 - n) for n in range(1, size + 1))
    while (action := unit.next_action()).kind != "stop":
        if action.kind == "list":
            unit.observe_page(BiliPage(action.page, len(items), items[(action.page - 1) * 30 : action.page * 30]))
        else:
            unit.consume(action.identity)
    return unit.coverage()


def commit(
    database: Database,
    subscription_id: str,
    *,
    coverage: BiliScanCoverage | BiliMultiFeedCoverage | None = None,
    size: int = 1,
    guard: object = None,
) -> tuple[str, dict[str, object]]:
    run_id, revision, cursor = begin(database, subscription_id)
    with database.session() as session:
        maximum = session.get(Subscription, subscription_id).max_items
    coverage = coverage or upload_coverage(cursor, size=size, maximum=maximum)
    uploads = coverage if isinstance(coverage, BiliScanCoverage) else coverage.uploads
    records = tuple(record(identity) for identity in uploads.consumed) if uploads is not None else ()
    args = dict(
        subscription_id=subscription_id,
        run_id=run_id,
        expected_revision=revision,
        input_cursor=cursor,
        next_cursor=coverage.next_state.to_cursor(),
        coverage=coverage,
        ownership_guard=guard,
    )
    MediaCrawlerIngestionService(database).ingest_bili_bounded(records, **args)
    return run_id, {"records": records, **args}


def progress(database: Database, subscription_id: str, sha: str | None = SHA) -> dict[str, object]:
    with database.session() as session:
        return scan_progress_payload(session.get(Subscription, subscription_id), upstream_sha=sha)


def test_history_source_end_is_persistent_observation_not_completeness(database: Database) -> None:
    subscription_id = seed(database)
    run_id, args = commit(database, subscription_id)
    payload = progress(database, subscription_id)
    row = payload["feeds"][0]
    assert payload["history_complete"] is False
    assert row["state"] == "source_end_observed"
    assert row["source_end_run_id"] == run_id
    assert row["history_unit_count"] == row["history_item_count"] == 1
    assert row["upstream_sha"] == SHA and row["contract_version"] == 1
    assert "cursor" not in str(payload)
    with database.session() as session:
        assert session.get(SyncRun, run_id).status == "succeeded"
        assert session.get(Subscription, subscription_id).checkpoint_revision == row["checkpoint_revision"] == 1
        assert session.scalar(select(func.count()).select_from(Content)) == 1  # older than legacy watermark retained
    MediaCrawlerIngestionService(database).ingest_bili_bounded(**args)
    assert progress(database, subscription_id) == payload
    commit(database, subscription_id)  # Head success must not erase historical observation.
    next_row = progress(database, subscription_id)["feeds"][0]
    assert next_row["state"] == "source_end_observed" and next_row["source_end_run_id"] == run_id
    assert next_row["unit_count"] == 2 and next_row["history_unit_count"] == 1


def test_item_limit_is_scanning_and_head_source_end_never_proves_history(database: Database) -> None:
    history_id = seed(database, max_items=1)
    commit(database, history_id, size=2)
    row = progress(database, history_id)["feeds"][0]
    assert row["state"] == "scanning" and row["last_stop_reason"] == "item_limit"
    assert row["source_end_run_id"] is None
    head_id = seed(database, history=False)
    commit(database, head_id)
    head = progress(database, head_id)["feeds"][0]
    assert head["state"] == "unproven" and head["last_stop_reason"] == "source_end"
    assert head["history_unit_count"] == 0 and head["source_end_run_id"] is None


def test_later_history_unit_resumes_scanning_but_keeps_last_observed_end(database: Database) -> None:
    subscription_id = seed(database)
    run_id, _args = commit(database, subscription_id)
    observed = progress(database, subscription_id)["feeds"][0]
    commit(database, subscription_id)
    commit(database, subscription_id, size=31)
    resumed = progress(database, subscription_id)["feeds"][0]
    assert resumed["state"] == "scanning" and resumed["last_stop_reason"] == "item_limit"
    assert resumed["generation_id"] == observed["generation_id"]
    assert resumed["source_end_run_id"] == run_id
    assert resumed["source_end_observed_at"] == observed["source_end_observed_at"]
    assert resumed["history_unit_count"] == 2


@pytest.mark.parametrize("platform", ["xhs", "dy", "ks", "wb", "tieba", "zhihu"])
def test_other_platform_success_is_unproven_and_get_does_not_initialize(database: Database, platform: str) -> None:
    subscription_id = seed(database, platform=platform)
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        subscription.last_success_at = datetime.now(UTC)
        subscription.checkpoint_revision = 50
    payload = progress(database, subscription_id)
    assert payload["history_complete"] is False
    assert payload["feeds"][0]["state"] == "unproven"
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SubscriptionScanProgress)) == 0


def test_legacy_bounded_call_without_coverage_does_not_manufacture_progress(database: Database) -> None:
    subscription_id = seed(database)
    run_id, revision, cursor = begin(database, subscription_id)
    MediaCrawlerIngestionService(database).ingest_bili_bounded(
        (),
        subscription_id=subscription_id,
        run_id=run_id,
        expected_revision=revision,
        input_cursor=cursor,
        next_cursor="legacy",
    )
    assert progress(database, subscription_id)["feeds"][0]["state"] == "unproven"
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SubscriptionScanProgress)) == 0


@pytest.mark.parametrize("at", [1, 2, 3])
def test_lease_failure_rolls_back_progress_contents_checkpoint_and_success(database: Database, at: int) -> None:
    subscription_id = seed(database)
    calls = 0

    def guard(session: object) -> None:
        nonlocal calls
        calls += 1
        if calls == at:
            raise LeaseLostError("synthetic")

    with pytest.raises(LeaseLostError):
        commit(database, subscription_id, guard=guard)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SubscriptionScanProgress)) == 0
        assert session.scalar(select(func.count()).select_from(Content)) == 0
        assert session.get(Subscription, subscription_id).checkpoint_revision == 0
        assert session.scalar(select(SyncRun.status)) == "ingesting"


@pytest.mark.parametrize("tamper", ["summary", "next_cursor", "records", "upstream"])
def test_coverage_reverified_before_any_publication(database: Database, tamper: str) -> None:
    subscription_id = seed(database)
    run_id, revision, cursor = begin(database, subscription_id)
    coverage = upload_coverage(cursor)
    records = tuple(record(identity) for identity in coverage.consumed)
    next_cursor = coverage.next_state.to_cursor()
    if tamper == "summary":
        coverage = replace(coverage, summary=replace(coverage.summary, stop_reason="restarted"))
    elif tamper == "next_cursor":
        next_cursor = cursor
    elif tamper == "records":
        records = ()
    else:
        with database.session() as session:
            session.get(SyncRun, run_id).manifest = {"upstream_sha": "c" * 40}
    with pytest.raises(RepositoryError, match="scan_progress_evidence_invalid"):
        MediaCrawlerIngestionService(database).ingest_bili_bounded(
            records,
            subscription_id=subscription_id,
            run_id=run_id,
            expected_revision=revision,
            input_cursor=cursor,
            next_cursor=next_cursor,
            coverage=coverage,
        )
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SubscriptionScanProgress)) == 0
        assert session.get(Subscription, subscription_id).checkpoint_revision == 0


def test_dynamic_snapshot_and_history_end_are_independent_of_uploads(database: Database) -> None:
    subscription_id = seed(database, scope="dynamics")
    with database.session() as session:
        state = state_from_cursor(session.get(Subscription, subscription_id).cursor["value"])
    page = BiliDynamicPage(BiliDynamicSnapshotRef("a" * 64, "", "", True, 0), ())
    first = BiliDynamicUnit(state, 30)
    first.observe_page(page)
    commit(database, subscription_id, coverage=first.coverage())
    row = progress(database, subscription_id)["feeds"][0]
    assert row["feed"] == "dynamics" and row["state"] == "scanning" and row["source_end_run_id"] is None
    # Consume a head discovery between the two naturally alternating history units.
    second = BiliDynamicUnit(first.coverage().next_state, 30)
    second.observe_page(page)
    commit(database, subscription_id, coverage=second.coverage())
    third = BiliDynamicUnit(second.coverage().next_state, 30)
    third.observe_page(page)
    run_id, _args = commit(database, subscription_id, coverage=third.coverage())
    row = progress(database, subscription_id)["feeds"][0]
    assert row["state"] == "source_end_observed" and row["source_end_run_id"] == run_id
    assert row["contract_version"] == 2 and row["unit_count"] == 3 and row["item_count"] == 0
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SubscriptionScanProgress)) == 1


@pytest.mark.parametrize("sha", [None, "c" * 40])
def test_missing_or_changed_locked_source_does_not_project_old_evidence(database: Database, sha: str | None) -> None:
    subscription_id = seed(database)
    commit(database, subscription_id)
    row = progress(database, subscription_id, sha)["feeds"][0]
    assert row["state"] == "unproven" and row["source_end_run_id"] is None


def test_two_feeds_have_independent_generations_counts_and_source_end(database: Database) -> None:
    subscription_id = seed(database, scope="both")
    with database.session() as session:
        state = state_from_cursor(session.get(Subscription, subscription_id).cursor["value"])
    uploads = wrap_upload_coverage(state, upload_coverage(state.uploads.to_cursor()))
    upload_run, _args = commit(database, subscription_id, coverage=uploads)
    first = progress(database, subscription_id)["feeds"]
    assert [row["feed"] for row in first] == ["uploads", "dynamics"]
    assert first[0]["state"] == "source_end_observed" and first[0]["source_end_run_id"] == upload_run
    assert first[1]["state"] == "unproven" and first[1]["unit_count"] == 0
    unit = BiliDynamicUnit(uploads.next_state, 30)
    unit.observe_page(BiliDynamicPage(BiliDynamicSnapshotRef("a" * 64, "", "", True, 0), ()))
    commit(database, subscription_id, coverage=unit.coverage())
    after = progress(database, subscription_id)["feeds"]
    assert after[0] == first[0]
    assert after[1]["state"] == "scanning" and after[1]["unit_count"] == 1
    assert after[1]["generation_id"] != first[0]["generation_id"]
    assert after[1]["source_end_run_id"] is None


def test_old_success_replay_after_newer_checkpoint_never_regresses_progress(database: Database) -> None:
    subscription_id = seed(database)
    _run, old_args = commit(database, subscription_id)
    commit(database, subscription_id)
    before = progress(database, subscription_id)
    MediaCrawlerIngestionService(database).ingest_bili_bounded(**old_args)
    assert progress(database, subscription_id) == before


def test_completed_run_replay_does_not_reinterpret_later_subscription_policy(database: Database) -> None:
    subscription_id = seed(database)
    _run, args = commit(database, subscription_id)
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        subscription.max_items = 2
        subscription.policy = {
            "mediacrawler": MediaCrawlerSubscriptionPolicy(False, 1, True, bili_scope="dynamics").to_payload()
        }
    result = MediaCrawlerIngestionService(database).ingest_bili_bounded(**args)
    assert result.committed_batches == 0
    with database.session() as session:
        assert session.scalar(select(SubscriptionScanProgress.unit_count)) == 1
        assert session.get(Subscription, subscription_id).checkpoint_revision == 1


def test_counter_overflow_rolls_back_new_run_and_retains_prior_evidence(database: Database) -> None:
    subscription_id = seed(database)
    commit(database, subscription_id)
    with database.session() as session:
        session.get(SubscriptionScanProgress, (subscription_id, "uploads")).unit_count = MAX_PROGRESS_NUMBER
    before = progress(database, subscription_id)
    with pytest.raises(RepositoryError, match="scan_progress_count_invalid"):
        commit(database, subscription_id, size=2)
    assert progress(database, subscription_id) == before
    with database.session() as session:
        assert session.get(Subscription, subscription_id).checkpoint_revision == 1
        assert session.scalar(select(func.count()).select_from(Content)) == 1
        assert sorted(session.scalars(select(SyncRun.status)).all()) == ["ingesting", "succeeded"]


@pytest.mark.parametrize("change", ["source", "contract"])
def test_new_source_or_contract_resets_evidence_generation(database: Database, change: str) -> None:
    subscription_id = seed(database)
    commit(database, subscription_id)
    prior = progress(database, subscription_id)["feeds"][0]
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        subscription.cursor = None
        sha = "c" * 40 if change == "source" else SHA
        scope = "uploads" if change == "contract" else None
        subscription.policy = {
            "mediacrawler": MediaCrawlerSubscriptionPolicy(False, 1, True, bili_scope=scope).to_payload()
        }
        state = state_for_cursor(
            None,
            account_id=UUID(subscription.account_id),
            author_fingerprint_sha256=hashlib.sha256(b"123").hexdigest(),
            upstream_sha=sha,
            scope=scope,
        )
        subscription.cursor = {"value": state.to_cursor()}
    run_id, revision, cursor = begin(database, subscription_id)
    with database.session() as session:
        session.get(SyncRun, run_id).manifest = {"upstream_sha": sha}
    coverage = (
        wrap_upload_coverage(state, upload_coverage(state.uploads.to_cursor()))
        if isinstance(state, BiliMultiFeedState)
        else upload_coverage(cursor)
    )
    MediaCrawlerIngestionService(database).ingest_bili_bounded(
        tuple(record(identity) for identity in coverage.consumed),
        subscription_id=subscription_id,
        run_id=run_id,
        expected_revision=revision,
        input_cursor=cursor,
        next_cursor=coverage.next_state.to_cursor(),
        coverage=coverage,
    )
    row = progress(database, subscription_id, sha)["feeds"][0]
    assert row["generation_id"] != prior["generation_id"]
    assert row["unit_count"] == 1 and row["history_unit_count"] == 0
    assert row["state"] == "unproven" and row["source_end_run_id"] is None
    assert row["contract_version"] == (2 if change == "contract" else 1)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contract_version", True),
        ("unit_count", -1),
        ("unit_count", 2**53),
        ("history_unit_count", 3),
        ("generation_id", "PRIVATE_SENTINEL"),
        ("last_stop_reason", "PRIVATE_SENTINEL"),
        ("checkpoint_revision", 999),
    ],
)
def test_invalid_stored_evidence_is_never_projected(database: Database, field: str, value: object) -> None:
    subscription_id = seed(database)
    commit(database, subscription_id)
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        setattr(subscription.scan_progress[0], field, value)
        payload = scan_progress_payload(subscription, upstream_sha=SHA)
        assert payload["feeds"][0]["state"] == "unproven"
        assert "PRIVATE_SENTINEL" not in str(payload)
        session.rollback()


def test_invalid_policy_suppresses_old_evidence_without_leaking_it(database: Database) -> None:
    subscription_id = seed(database)
    commit(database, subscription_id)
    with database.session() as session:
        subscription = session.get(Subscription, subscription_id)
        subscription.policy = {"PRIVATE_SENTINEL": "PRIVATE_SENTINEL"}
        payload = scan_progress_payload(subscription, upstream_sha=SHA)
        assert payload["feeds"][0]["state"] == "unproven"
        assert "PRIVATE_SENTINEL" not in str(payload)


@pytest.mark.parametrize("platform", ["bili", "xhs", "dy", "ks", "wb", "tieba", "zhihu"])
def test_http_detail_projects_safe_durable_progress_without_writes(
    database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    import media_sync.interfaces.api as api_module
    from tests.unit._api_client import authenticated_test_client

    subscription_id = seed(database, platform=platform)
    if platform == "bili":
        commit(database, subscription_id)
    monkeypatch.setattr(api_module, "load_mediacrawler_lock", lambda _path: SimpleNamespace(commit=SHA))
    settings = Settings(database_url=database.url, state_dir=tmp_path / "state", _env_file=None)
    with authenticated_test_client(settings) as client:
        for _ in range(2):
            response = client.get(f"/api/v1/subscriptions/{subscription_id}")
            assert response.status_code == 200
            payload = response.json()["checkpoint_summary"]["scan_progress"]
            assert payload == progress(database, subscription_id)
            assert payload["history_complete"] is False
            assert payload["feeds"][0]["state"] == ("source_end_observed" if platform == "bili" else "unproven")
            for forbidden in ("bili-scan-v1:", "author_fingerprint_sha256", "witness", str(tmp_path)):
                assert forbidden not in response.text
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SubscriptionScanProgress)) == int(platform == "bili")


def test_page_deletion_drift_can_reach_source_end_without_complete_visible_history() -> None:
    items = tuple(BiliIdentity(str(n), f"BV{n:010d}", 100000 - n) for n in range(1, 61))
    changed = items[1:]
    state = replace(BiliScanState.initial(UUID(int=1), "a" * 64, SHA), next_lane="history")
    seen: set[str] = set()
    reasons: list[str] = []
    for step in range(3):
        state = replace(state, next_lane="history")
        unit = BiliScanUnit(state, 30)
        while (action := unit.next_action()).kind != "stop":
            if action.kind == "list":
                current = items if step == 0 or (step == 1 and action.page == 1) else changed
                unit.observe_page(
                    BiliPage(action.page, len(current), current[(action.page - 1) * 30 : action.page * 30])
                )
            else:
                seen.add(action.identity.aid)
                unit.consume(action.identity)
        coverage = unit.coverage()
        coverage.validate(state, 30, tuple(row.aid for row in coverage.consumed))
        reasons.append(coverage.stop_reason)
        state = coverage.next_state
    assert reasons == ["item_limit", "list_limit", "source_end"]
    assert {row.aid for row in changed} - seen == {"31"}
