"""Douyin continuation pacing validation and lock binding."""

from __future__ import annotations

import pytest

from media_sync.scheduler.douyin_scan_continuation import (
    DEFAULT_DOUYIN_SCAN_CONTINUATION_DELAY_SECONDS,
    DouyinScanContinuationPolicy,
    validate_douyin_continuation_delay,
)


@pytest.mark.parametrize("value", [0, 60, 300, 604_800])
def test_delay_validation_accepts_the_closed_domain(value: int) -> None:
    assert validate_douyin_continuation_delay(value) == value


@pytest.mark.parametrize("value", [1, 59, 604_801, True, 300.0, "300", None])
def test_delay_validation_rejects_everything_else(value: object) -> None:
    with pytest.raises(ValueError):
        validate_douyin_continuation_delay(value)


def test_policy_defaults_are_bounded() -> None:
    policy = DouyinScanContinuationPolicy()
    assert policy.delay_seconds == DEFAULT_DOUYIN_SCAN_CONTINUATION_DELAY_SECONDS == 300
    assert policy.upstream_sha is None


def test_policy_rejects_malformed_upstream_sha() -> None:
    with pytest.raises(ValueError):
        DouyinScanContinuationPolicy(delay_seconds=300, upstream_sha="not-a-sha")


def test_policy_from_lock_fails_closed_without_a_valid_checkout(tmp_path) -> None:
    policy = DouyinScanContinuationPolicy.from_lock(tmp_path / "missing.lock", delay_seconds=60)
    assert policy.delay_seconds == 60
    assert policy.upstream_sha is None
