"""Strict, offline scheduling evidence; no completion inferred from summaries."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

import pytest
from pydantic import ValidationError

from media_sync.config import Settings
from media_sync.infrastructure.db.models import Account, Author, Job, Subscription, SyncRun
from media_sync.integrations.mediacrawler.bilibili_multifeed import (
    BiliDynamicLane,
    BiliDynamicSnapshotRef,
    BiliDynamicState,
    BiliMultiFeedState,
)
from media_sync.integrations.mediacrawler.bilibili_scan import (
    BiliIdentity,
    BiliLane,
    BiliPage,
    BiliScanState,
    BiliUnitSummary,
)
from media_sync.integrations.mediacrawler.bridge import MANIFEST_SCHEMA_VERSION
from media_sync.integrations.mediacrawler.subscription_policy import MediaCrawlerSubscriptionPolicy
from media_sync.scheduler.bili_scan_continuation import BiliScanContinuationPolicy, validate_continuation_delay

SHA = "a" * 40
ACCOUNT_ID = UUID("85c05fb1-69da-43ec-9c34-312a2372e695")
AUTHOR_HASH = hashlib.sha256(b"252671524").hexdigest()
NOW = datetime(2026, 9, 6, tzinfo=UTC)
INITIAL = BiliScanState.initial(ACCOUNT_ID, AUTHOR_HASH, SHA)
WITNESS = BiliPage(1, 1, (BiliIdentity("1000", "BV0000000000", 1767225600),))
PENDING = replace(INITIAL, head=BiliLane(witness=WITNESS, index=1))
SNAPSHOT = BiliDynamicSnapshotRef("b" * 64, "", "", True, 0)


def _evidence(state: BiliScanState | BiliMultiFeedState = PENDING) -> tuple[Job, SyncRun, Subscription]:
    account = Account(id=str(ACCOUNT_ID), platform="bili", adapter="mediacrawler", auth_status="authenticated")
    author = Author(id=str(uuid4()), platform="bili", remote_id="252671524")
    scope = state.scope if isinstance(state, BiliMultiFeedState) else None
    subscription = Subscription(
        id=str(uuid4()),
        account_id=account.id,
        author_id=author.id,
        account=account,
        author=author,
        enabled=True,
        deleted_at=None,
        interval_seconds=21600,
        max_items=2,
        checkpoint_revision=1,
        schedule_revision=1,
        cursor={"value": state.to_cursor()},
        policy={"mediacrawler": MediaCrawlerSubscriptionPolicy(False, 2, True, bili_scope=scope).to_payload()},
    )
    run = SyncRun(
        id=str(uuid4()),
        subscription_id=subscription.id,
        status="succeeded",
        attempt=1,
        cursor_before=None,
        cursor_after=dict(subscription.cursor),
        checkpoint_revision_before=0,
        checkpoint_revision_after=1,
        error_code=None,
        finished_at=NOW,
    )
    job = Job(
        id=str(uuid4()),
        job_type="sync.subscription",
        status="succeeded",
        run_id=run.id,
        subscription_id=subscription.id,
        platform="bili",
        account_id=account.id,
        attempts=1,
    )
    run.manifest = {
        "schema_version": 1,
        "adapter": "mediacrawler",
        "scheduler_job_id": job.id,
        "schedule_revision": 0,
        "attempt": 1,
        "sync_run_id": run.id,
        "platform": "bili",
        "mode": "forward",
        "crawl_revision_before": 0,
        "artifact_schema_version": MANIFEST_SCHEMA_VERSION,
        "upstream_sha": SHA,
        "execution_id": str(uuid5(UUID(job.id), "media-sync/mediacrawler/attempt/1")),
        "output_fingerprint_sha256": "c" * 64,
        "input_records": 0,
    }
    return job, run, subscription


def _delay(evidence: tuple[Job, SyncRun, Subscription], *, policy: BiliScanContinuationPolicy | None = None) -> int:
    job, run, subscription = evidence
    return (policy or BiliScanContinuationPolicy(upstream_sha=SHA)).delay_after_success(
        job=job,
        run=run,
        subscription=subscription,
        schedule_revision=0,
        ordinary_interval=subscription.interval_seconds,
    )


@pytest.mark.parametrize("lane", ["head", "history"])
@pytest.mark.parametrize(
    "context", [BiliLane(witness=WITNESS), BiliLane(witness=WITNESS, index=1), BiliLane(page=2, previous_pubdate=10)]
)
def test_upload_pending_in_either_lane_including_consumed_witness(lane: str, context: BiliLane) -> None:
    state = replace(INITIAL, **{lane: context})
    assert _delay(_evidence(state)) == 300


@pytest.mark.parametrize("reason", ["source_end", "head_boundary", "restarted", "item_limit"])
def test_empty_lanes_are_unknown_not_permanent_history_completion(reason: str) -> None:
    state = replace(INITIAL, head_boundary=1767225600, last_unit=BiliUnitSummary("history", reason, 0, 0, 0))
    assert state.public_summary()["history_active"] is True
    assert _delay(_evidence(state)) == 21600
    assert _delay(_evidence(replace(state, head=PENDING.head))) == 300


@pytest.mark.parametrize("lane", ["head", "history"])
@pytest.mark.parametrize("context", [BiliDynamicLane(snapshot=SNAPSHOT), BiliDynamicLane(offset="next-page")])
@pytest.mark.parametrize("scope", ["dynamics", "both"])
def test_dynamic_snapshot_even_empty_or_offset_in_any_enabled_lane(
    scope: str, lane: str, context: BiliDynamicLane
) -> None:
    state = BiliMultiFeedState(INITIAL, scope, "dynamics", replace(BiliDynamicState(), **{lane: context}))
    assert _delay(_evidence(state)) == 300
    assert _delay(_evidence(replace(state, dynamics=BiliDynamicState()))) == 21600


def test_scope_preserves_but_does_not_accelerate_inactive_feed() -> None:
    dynamic = BiliDynamicState(history=BiliDynamicLane(snapshot=SNAPSHOT))
    uploads_only = BiliMultiFeedState(INITIAL, "uploads", "uploads", dynamic)
    assert _delay(_evidence(uploads_only)) == 21600
    assert _delay(_evidence(uploads_only.with_scope("both"))) == 300
    dynamics_only = BiliMultiFeedState(PENDING, "dynamics", "dynamics")
    assert _delay(_evidence(dynamics_only)) == 21600
    assert _delay(_evidence(dynamics_only.with_scope("both"))) == 300


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("job", "id", "invalid"),
        ("job", "run_id", str(uuid4())),
        ("job", "status", "running"),
        ("job", "job_type", "pipeline.subscription"),
        ("job", "subscription_id", str(uuid4())),
        ("job", "account_id", str(uuid4())),
        ("job", "platform", "dy"),
        ("job", "attempts", 2),
        ("run", "status", "failed_terminal"),
        ("run", "subscription_id", str(uuid4())),
        ("run", "finished_at", None),
        ("run", "error_code", "schema_invalid"),
        ("run", "attempt", 2),
        ("run", "checkpoint_revision_before", None),
        ("run", "checkpoint_revision_before", True),
        ("run", "checkpoint_revision_after", 2),
        ("run", "manifest", {}),
        ("subscription", "enabled", False),
        ("subscription", "deleted_at", NOW),
        ("subscription", "schedule_revision", 2),
        ("subscription", "checkpoint_revision", 2),
        ("subscription", "cursor", {"value": "legacy"}),
        ("subscription", "policy", {}),
        ("account", "id", str(uuid4())),
        ("account", "platform", "dy"),
        ("account", "adapter", "fake"),
        ("account", "auth_status", "expired"),
        ("author", "id", str(uuid4())),
        ("author", "platform", "dy"),
        ("author", "remote_id", "other-creator"),
    ],
)
def test_unbound_failed_paused_deleted_or_stale_evidence_retains_ordinary_delay(
    section: str, field: str, value: Any
) -> None:
    evidence = _evidence()
    job, run, subscription = evidence
    subjects = {
        "job": job,
        "run": run,
        "subscription": subscription,
        "account": subscription.account,
        "author": subscription.author,
    }
    setattr(subjects[section], field, value)
    assert _delay(evidence) == 21600


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("adapter", "fake"),
        ("scheduler_job_id", str(uuid4())),
        ("schedule_revision", 1),
        ("attempt", 2),
        ("execution_id", str(uuid4())),
        ("sync_run_id", str(uuid4())),
        ("platform", "dy"),
        ("mode", "backfill"),
        ("crawl_revision_before", 1),
        ("artifact_schema_version", 2),
        ("upstream_sha", "d" * 40),
        ("output_fingerprint_sha256", "wrong"),
        ("input_records", True),
        ("input_records", -1),
        ("unknown", "future-schema"),
        ("recovered_artifact", {}),
    ],
)
def test_exact_provenance_is_required(key: str, value: Any) -> None:
    evidence = _evidence()
    evidence[1].manifest[key] = value
    assert _delay(evidence) == 21600


@pytest.mark.parametrize(
    "cursor",
    [
        None,
        {},
        {"value": "legacy"},
        {"value": "bili-scan-v99:{}"},
        {"value": True},
        {"value": PENDING.to_cursor(), "extra": 1},
    ],
)
def test_unknown_cursor_is_not_initialized(cursor: Any) -> None:
    evidence = _evidence()
    evidence[1].cursor_after = evidence[2].cursor = cursor
    assert _delay(evidence) == 21600


@pytest.mark.parametrize(
    "state",
    [
        replace(PENDING, account_id=uuid4()),
        replace(PENDING, author_fingerprint_sha256="d" * 64),
        replace(PENDING, upstream_sha="d" * 40),
    ],
)
def test_current_cursor_identity_must_match_account_author_and_lock(state: BiliScanState) -> None:
    assert _delay(_evidence(state)) == 21600


def test_changed_scope_rejects_success_from_previous_scope() -> None:
    evidence = _evidence(BiliMultiFeedState(PENDING, "both"))
    evidence[2].policy["mediacrawler"]["bili_scope"] = "uploads"
    assert _delay(evidence) == 21600


@pytest.mark.parametrize(
    "delay,ordinary,expected", [(300, 21600, 300), (60, 21600, 60), (600, 120, 120), (0, 21600, 21600)]
)
def test_delay_is_paced_capped_and_can_be_disabled(delay: int, ordinary: int, expected: int) -> None:
    evidence = _evidence()
    evidence[2].interval_seconds = ordinary
    assert _delay(evidence, policy=BiliScanContinuationPolicy(delay, SHA)) == expected
    assert _delay(evidence, policy=BiliScanContinuationPolicy(delay)) == ordinary


@pytest.mark.parametrize("value", [True, False, 300.0, -1, 1, 59, 604801, "300.0", "-0", "01", None])
def test_invalid_configuration_is_rejected(value: Any) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, bili_scan_continuation_delay_seconds=value)
    with pytest.raises(ValueError):
        validate_continuation_delay(value)


@pytest.mark.parametrize("value", ["0", "60", "300", "604800"])
def test_environment_integer_configuration(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("MEDIA_SYNC_BILI_SCAN_CONTINUATION_DELAY_SECONDS", value)
    assert Settings(_env_file=None).bili_scan_continuation_delay_seconds == int(value)


def test_lock_binding_and_missing_lock_fail_closed(tmp_path: Path) -> None:
    policy = BiliScanContinuationPolicy.from_lock(Path(__file__).resolve().parents[2] / "upstreams.lock.json")
    assert policy.upstream_sha is not None and len(policy.upstream_sha) == 40
    unknown = BiliScanContinuationPolicy.from_lock(tmp_path / "missing.json")
    assert unknown.upstream_sha is None and _delay(_evidence(), policy=unknown) == 21600
    disabled = BiliScanContinuationPolicy.from_lock(tmp_path / "missing.json", delay_seconds=0)
    assert disabled.delay_seconds == 0 and disabled.upstream_sha is None


def test_exact_recovered_artifact_provenance_is_accepted() -> None:
    evidence = _evidence()
    job, run, _subscription = evidence
    source_run_id = str(uuid4())
    run.manifest["recovered_artifact"] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "attempt": 1,
        "execution_id": run.manifest["execution_id"],
        "sync_run_id": source_run_id,
    }
    run.attempt = job.attempts = run.manifest["attempt"] = 2
    run.manifest["execution_id"] = str(uuid5(UUID(job.id), "media-sync/mediacrawler/attempt/2"))
    assert _delay(evidence) == 300
    run.manifest["recovered_artifact"]["sync_run_id"] = run.id
    assert _delay(evidence) == 21600


@pytest.mark.parametrize(
    "section,field",
    [("job", "attempts"), ("subscription", "schedule_revision"), ("subscription", "checkpoint_revision")],
)
def test_boolean_durable_revision_is_not_an_integer(section: str, field: str) -> None:
    evidence = _evidence()
    setattr(evidence[0] if section == "job" else evidence[2], field, True)
    assert _delay(evidence) == 21600


@pytest.mark.parametrize("delay", [0, 60, 300, 600])
def test_common_cli_and_api_worker_factory_injects_configured_current_lock(tmp_path: Path, delay: int) -> None:
    from media_sync.infrastructure.db import Database
    from media_sync.interfaces.cli import _build_subscription_worker

    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'factory.sqlite3').as_posix()}")
    settings = Settings(
        _env_file=None,
        state_dir=tmp_path,
        mediacrawler_lock_path=Path(__file__).resolve().parents[2] / "upstreams.lock.json",
        bili_scan_continuation_delay_seconds=delay,
    )
    try:
        worker = _build_subscription_worker(
            database, settings, enable_mediacrawler=False, accept_mediacrawler_license=False
        )
        assert worker.bili_scan_continuation is not None
        assert worker.bili_scan_continuation.delay_seconds == delay
        assert (worker.bili_scan_continuation.upstream_sha is None) is (delay == 0)
    finally:
        database.dispose()
