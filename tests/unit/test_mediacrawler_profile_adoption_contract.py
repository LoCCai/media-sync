"""Pure contract checks for WebUI profile adoption inputs and failures."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from media_sync.application.mediacrawler_profile_adoption import (
    PROFILE_ADOPTION_ERROR_CODES,
    MediaCrawlerProfileAdoptionError,
    MediaCrawlerProfileAdoptionRequest,
)


def test_request_normalizes_probe_timing_without_exposing_mutable_inputs() -> None:
    request = MediaCrawlerProfileAdoptionRequest(
        account_id=uuid4(),
        expected_auth_revision=7,
        timeout_seconds=30,
        poll_seconds=1,
    )

    assert (request.timeout_seconds, request.poll_seconds) == (30.0, 1.0)
    assert replace(request, expected_auth_revision=8).expected_auth_revision == 8


@pytest.mark.parametrize("revision", [-1, True, 2**63 - 1])
def test_request_rejects_invalid_auth_generation(revision: int) -> None:
    with pytest.raises(ValueError, match="expected_auth_revision"):
        MediaCrawlerProfileAdoptionRequest(uuid4(), revision)


@pytest.mark.parametrize(
    ("timeout", "poll"),
    [(0, 0.05), (float("nan"), 0.05), (3601, 0.05), (10, 0), (10, True), (10, 10), (10, 6)],
)
def test_request_rejects_unbounded_probe_timing(timeout: float, poll: float) -> None:
    with pytest.raises(ValueError):
        MediaCrawlerProfileAdoptionRequest(uuid4(), 0, timeout_seconds=timeout, poll_seconds=poll)


def test_error_contract_is_closed_and_never_echoes_unknown_input() -> None:
    sentinel = "Cookie=PRIVATE-PROFILE-SENTINEL"
    error = MediaCrawlerProfileAdoptionError(sentinel)

    assert error.code == "profile_adoption_filesystem_failed"
    assert sentinel not in str(error) and sentinel not in error.message
    assert set(PROFILE_ADOPTION_ERROR_CODES) == {
        "profile_adoption_account_not_found",
        "profile_adoption_account_ineligible",
        "profile_adoption_busy",
        "profile_adoption_cancelled",
        "profile_adoption_cleanup_failed",
        "profile_adoption_conflict",
        "profile_adoption_copy_failed",
        "profile_adoption_filesystem_failed",
        "profile_adoption_probe_failed",
        "profile_adoption_probe_unavailable",
        "profile_adoption_result_invalid",
        "profile_adoption_rollback_failed",
        "profile_adoption_source_empty",
        "profile_adoption_source_invalid",
        "profile_adoption_source_missing",
    }
