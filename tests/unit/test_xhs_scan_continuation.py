from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from media_sync.config import Settings
from media_sync.infrastructure.db import Database
from media_sync.interfaces.cli import _build_pipeline_worker, _build_subscription_worker
from media_sync.scheduler.xhs_scan_continuation import (
    XhsScanContinuationPolicy,
    validate_xhs_continuation_delay,
)

LOCK_PATH = Path(__file__).resolve().parents[2] / "upstreams.lock.json"


@pytest.mark.parametrize("value", [True, False, 300.0, -1, 1, 59, 604801, "300.0", "-0", "01", None])
def test_invalid_xhs_continuation_configuration_is_rejected(value: Any) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, xhs_scan_continuation_delay_seconds=value)
    with pytest.raises(ValueError):
        validate_xhs_continuation_delay(value)


@pytest.mark.parametrize("value", ["0", "60", "300", "604800"])
def test_xhs_environment_integer_configuration(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("MEDIA_SYNC_XHS_SCAN_CONTINUATION_DELAY_SECONDS", value)
    assert Settings(_env_file=None).xhs_scan_continuation_delay_seconds == int(value)


def test_xhs_lock_binding_and_missing_lock_fail_closed(tmp_path: Path) -> None:
    policy = XhsScanContinuationPolicy.from_lock(LOCK_PATH)
    assert policy.upstream_sha is not None and len(policy.upstream_sha) == 40
    unknown = XhsScanContinuationPolicy.from_lock(tmp_path / "missing.json")
    assert unknown.upstream_sha is None and unknown.delay_seconds == 300
    disabled = XhsScanContinuationPolicy.from_lock(tmp_path / "missing.json", delay_seconds=0)
    assert disabled.upstream_sha is None and disabled.delay_seconds == 0
    ordinary = XhsScanContinuationPolicy.from_lock(LOCK_PATH, delay_seconds=0)
    assert ordinary.upstream_sha == policy.upstream_sha and ordinary.delay_seconds == 0


@pytest.mark.parametrize("delay", [0, 60, 300, 600])
def test_common_worker_factories_inject_xhs_policy(tmp_path: Path, delay: int) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'factory.sqlite3').as_posix()}")
    settings = Settings(
        _env_file=None,
        state_dir=tmp_path,
        mediacrawler_lock_path=LOCK_PATH,
        xhs_scan_continuation_delay_seconds=delay,
    )
    try:
        subscription = _build_subscription_worker(
            database,
            settings,
            enable_mediacrawler=False,
            accept_mediacrawler_license=False,
        )
        pipeline = _build_pipeline_worker(
            database,
            settings,
            worker_id="xhs-policy-test",
            retry_delay_seconds=30,
            enable_mediacrawler=False,
            accept_mediacrawler_license=False,
            xhs_detail_reference_ref=None,
        )
        assert subscription.xhs_scan_continuation is not None
        assert subscription.xhs_scan_continuation.delay_seconds == delay
        assert pipeline.xhs_delivery_policy.delay_seconds == delay
        assert pipeline.xhs_delivery_policy.upstream_sha is not None
    finally:
        database.dispose()
