from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID

import pytest

from media_sync.application.operation_payloads import (
    MAX_OPERATION_ARRAY_ITEMS,
    MAX_OPERATION_COUNT,
    OPERATION_EVENT_CODES,
    OPERATION_KINDS,
    OPERATION_PAYLOAD_SCHEMA_VERSION,
    OperationPayloadError,
    operation_event_context,
    operation_idempotency_key_digest,
    operation_request_fingerprint,
    operation_result_summary,
)

ACCOUNT_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
ASSET_ID = "33333333-3333-4333-8333-333333333333"
JOB_ID = "44444444-4444-4444-8444-444444444444"
AUTHOR_ID = "55555555-5555-4555-8555-555555555555"
SUBJECT_ID = "66666666-6666-4666-8666-666666666666"
REFERENCE_DIGEST = "a" * 64
PROFILE_FINGERPRINT = "b" * 64
LIBRARY_ID_DIGEST = "c" * 64
KIND_ROUTES = {
    "account-login": "/api/v1/accounts/{account_id}/login",
    "asset-download": "/api/v1/assets/{asset_id}/download",
    "scheduler-run": "/api/v1/scheduler/run",
    "pipeline-run": "/api/v1/pipeline/run",
    "emby-export": "/api/v1/emby/export",
    "media-server-probe": "/api/v1/media-server/probe",
    "media-server-scan": "/api/v1/media-server/scan",
}
KIND_TARGET_TYPES = {
    "account-login": "account",
    "asset-download": "asset",
    "scheduler-run": None,
    "pipeline-run": None,
    "emby-export": "author",
    "media-server-probe": None,
    "media-server-scan": None,
}


def _request_parameters(kind: str) -> dict[str, object]:
    common = {
        "enable_mediacrawler": True,
        "accept_mediacrawler_license": True,
    }
    if kind == "account-login":
        return {**common, "timeout_microseconds": 30_000_000}
    if kind == "asset-download":
        return {
            **common,
            "lease_seconds": 60,
            "max_attempts": 3,
            "xhs_detail_reference_digest": REFERENCE_DIGEST,
        }
    if kind == "scheduler-run":
        return {
            **common,
            "max_jobs": 25,
            "global_capacity": 8,
            "lease_seconds": 60,
            "scan_limit": 100,
        }
    if kind == "pipeline-run":
        return {
            **common,
            "max_jobs": 25,
            "lease_seconds": 60,
            "scan_limit": 100,
            "retry_delay_seconds": 30,
            "xhs_detail_reference_digest": None,
        }
    if kind == "emby-export":
        return {"lease_seconds": 60, "max_attempts": 3}
    if kind in {"media-server-probe", "media-server-scan"}:
        return {"profile_fingerprint": PROFILE_FINGERPRINT}
    raise AssertionError(f"unexpected test kind: {kind}")


@pytest.mark.parametrize(
    ("kind", "payload", "expected"),
    [
        (
            "account-login",
            {
                "account_id": UUID(ACCOUNT_ID),
                "login_session_id": SESSION_ID,
                "runner_status": "authenticated",
                "login_session_status": "succeeded",
                "auth_status": "authenticated",
                "expires_at": "2026-09-04T10:00:00+08:00",
                "completed_at": datetime(2026, 9, 4, 2, 1, tzinfo=UTC),
            },
            {
                "account_id": ACCOUNT_ID,
                "login_session_id": SESSION_ID,
                "runner_status": "authenticated",
                "login_session_status": "succeeded",
                "auth_status": "authenticated",
                "expires_at": "2026-09-04T02:00:00+00:00",
                "completed_at": "2026-09-04T02:01:00+00:00",
            },
        ),
        (
            "asset-download",
            {
                "asset_id": ASSET_ID,
                "job_id": JOB_ID,
                "ok": True,
                "status": "verified",
                "disposition": "downloaded",
                "generation": 2,
                "size_bytes": 4096,
            },
            {
                "asset_id": ASSET_ID,
                "job_id": JOB_ID,
                "ok": True,
                "status": "verified",
                "disposition": "downloaded",
                "generation": 2,
                "size_bytes": 4096,
            },
        ),
        (
            "scheduler-run",
            {"statuses": ["succeeded", "retry_wait", "succeeded"]},
            {"processed_count": 3, "status_counts": {"retry_wait": 1, "succeeded": 2}},
        ),
        (
            "pipeline-run",
            {"statuses": []},
            {"processed_count": 0, "status_counts": {}},
        ),
        (
            "emby-export",
            {
                "author_id": AUTHOR_ID,
                "job_id": JOB_ID,
                "already_exported": False,
                "managed_file_count": 7,
            },
            {
                "author_id": AUTHOR_ID,
                "job_id": JOB_ID,
                "already_exported": False,
                "managed_file_count": 7,
            },
        ),
        (
            "media-server-probe",
            {
                "provider": "emby",
                "server_version": "4.8.11.0",
                "library_id_digest": LIBRARY_ID_DIGEST,
                "library_present": True,
            },
            {
                "provider": "emby",
                "server_version": "4.8.11.0",
                "library_id_digest": LIBRARY_ID_DIGEST,
                "library_present": True,
            },
        ),
        (
            "media-server-scan",
            {
                "provider": "jellyfin",
                "server_version": "10.10.7",
                "library_id_digest": LIBRARY_ID_DIGEST,
                "scan_state": "accepted",
            },
            {
                "provider": "jellyfin",
                "server_version": "10.10.7",
                "library_id_digest": LIBRARY_ID_DIGEST,
                "scan_state": "accepted",
            },
        ),
    ],
)
def test_operation_result_summary_projects_each_closed_kind(
    kind: str,
    payload: dict[str, object],
    expected: dict[str, object],
) -> None:
    assert operation_result_summary(kind, payload) == expected


def test_batch_summary_retains_only_bounded_counts_in_sorted_order() -> None:
    statuses = ["succeeded"] * (MAX_OPERATION_ARRAY_ITEMS - 1) + ["queued"]

    result = operation_result_summary("pipeline-run", {"statuses": statuses})

    assert result == {
        "processed_count": MAX_OPERATION_ARRAY_ITEMS,
        "status_counts": {"queued": 1, "succeeded": MAX_OPERATION_ARRAY_ITEMS - 1},
    }
    assert "statuses" not in result
    assert "jobs" not in result


@pytest.mark.parametrize(
    "payload",
    [
        {"statuses": ["succeeded"] * (MAX_OPERATION_ARRAY_ITEMS + 1)},
        {"statuses": [{"job_id": JOB_ID}]},
        {"jobs": [{"id": JOB_ID, "status": "succeeded"}]},
    ],
)
def test_batch_summary_rejects_lists_or_job_details_outside_contract(payload: object) -> None:
    with pytest.raises(OperationPayloadError, match="operation_result_invalid"):
        operation_result_summary("scheduler-run", payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"statuses": ["succeeded"], "request_body": "private-sentinel"},
        {"statuses": ["https://example.invalid/media?token=private-sentinel"]},
        {"statuses": [r"C:\\Users\\private-sentinel\\asset.mp4"]},
        {"statuses": ["/srv/media/private-sentinel/asset.mp4"]},
        {"statuses": [r"\\server\share\private-sentinel"]},
        {"statuses": ["qr_private-sentinel_bytes"]},
    ],
)
def test_result_contract_rejects_raw_body_url_path_qr_and_secret_values(payload: object) -> None:
    with pytest.raises(OperationPayloadError) as captured:
        operation_result_summary("pipeline-run", payload)

    assert "private-sentinel" not in str(captured.value)
    assert "private-sentinel" not in repr(captured.value)


@pytest.mark.parametrize(
    "mutation",
    [
        {"ok": 1},
        {"generation": True},
        {"generation": -1},
        {"size_bytes": MAX_OPERATION_COUNT + 1},
        {"asset_id": "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"},
        {"asset_id": "not-a-uuid"},
    ],
)
def test_result_scalar_boundaries_fail_closed(mutation: dict[str, object]) -> None:
    payload: dict[str, object] = {
        "asset_id": ASSET_ID,
        "job_id": JOB_ID,
        "ok": True,
        "status": "verified",
        "disposition": "downloaded",
        "generation": 2,
        "size_bytes": 4096,
    }
    payload.update(mutation)

    with pytest.raises(OperationPayloadError, match="operation_result_invalid"):
        operation_result_summary("asset-download", payload)


def test_result_time_requires_timezone_and_normalizes_to_utc() -> None:
    base: dict[str, object] = {
        "account_id": ACCOUNT_ID,
        "login_session_id": SESSION_ID,
        "runner_status": "authenticated",
        "login_session_status": "succeeded",
        "auth_status": "authenticated",
        "expires_at": datetime(2026, 9, 4, 10, tzinfo=timezone(timedelta(hours=8))),
        "completed_at": None,
    }

    assert operation_result_summary("account-login", base)["expires_at"] == "2026-09-04T02:00:00+00:00"
    base["expires_at"] = datetime(2026, 9, 4, 10)
    with pytest.raises(OperationPayloadError, match="operation_result_invalid"):
        operation_result_summary("account-login", base)


@pytest.mark.parametrize(
    ("kind", "mutation"),
    [
        ("media-server-probe", {"provider": "plex"}),
        ("media-server-probe", {"server_version": "10.10.7 private build"}),
        ("media-server-probe", {"server_version": "api-key-private-sentinel"}),
        ("media-server-probe", {"server_version": "v" * 65}),
        ("media-server-probe", {"library_id_digest": "A" * 64}),
        ("media-server-probe", {"library_present": 1}),
        ("media-server-scan", {"scan_state": "completed"}),
        ("media-server-scan", {"server_version": "10.10.7+private-sentinel"}),
        ("media-server-scan", {"server_origin": "https://private-sentinel.invalid"}),
    ],
)
def test_media_server_result_summary_is_closed_and_redaction_safe(
    kind: str,
    mutation: dict[str, object],
) -> None:
    payload: dict[str, object]
    if kind == "media-server-probe":
        payload = {
            "provider": "emby",
            "server_version": "4.8.11.0",
            "library_id_digest": LIBRARY_ID_DIGEST,
            "library_present": True,
        }
    else:
        payload = {
            "provider": "jellyfin",
            "server_version": "10.10.7",
            "library_id_digest": LIBRARY_ID_DIGEST,
            "scan_state": "accepted",
        }
    payload.update(mutation)

    with pytest.raises(OperationPayloadError) as captured:
        operation_result_summary(kind, payload)

    assert captured.value.code == "operation_result_invalid"
    assert "private-sentinel" not in str(captured.value)
    assert "private-sentinel" not in repr(captured.value)


@pytest.mark.parametrize(
    ("event_code", "context", "expected"),
    [
        (
            "operation_requested",
            {"kind": "account-login", "target_id": ACCOUNT_ID},
            {"kind": "account-login", "target_type": "account", "target_id": ACCOUNT_ID},
        ),
        (
            "operation_requested",
            {"kind": "pipeline-run", "target_id": None},
            {"kind": "pipeline-run", "target_type": None, "target_id": None},
        ),
        ("operation_started", {}, {}),
        ("operation_phase_changed", {"phase": "claiming_jobs"}, {"phase": "claiming_jobs"}),
        (
            "operation_progressed",
            {
                "phase": "downloading",
                "progress_current": 2,
                "progress_total": 5,
                "progress_unit": "items",
            },
            {
                "phase": "downloading",
                "progress_current": 2,
                "progress_total": 5,
                "progress_unit": "items",
            },
        ),
        (
            "operation_entity_linked",
            {"subject_type": "job", "subject_id": SUBJECT_ID, "role": "execution"},
            {"subject_type": "job", "subject_id": SUBJECT_ID, "role": "execution"},
        ),
        ("operation_cancel_requested", {}, {}),
        ("operation_cancel_observed", {"phase": "between_jobs"}, {"phase": "between_jobs"}),
        ("operation_succeeded", {}, {}),
        (
            "operation_failed",
            {"error_code": "job_failed_retryable", "retryable": True},
            {"error_code": "job_failed_retryable", "retryable": True},
        ),
        ("operation_cancelled", {"phase": None}, {"phase": None}),
        (
            "operation_interrupted",
            {"error_code": "owner_lease_expired", "retryable": False},
            {"error_code": "owner_lease_expired", "retryable": False},
        ),
        (
            "operation_reconciled",
            {"subject_type": "login_session", "subject_state": "succeeded"},
            {"subject_type": "login_session", "subject_state": "succeeded"},
        ),
    ],
)
def test_every_event_code_has_one_closed_safe_context(
    event_code: str,
    context: dict[str, object],
    expected: dict[str, object],
) -> None:
    assert operation_event_context(event_code, context) == expected


def test_event_fixture_covers_the_complete_event_vocabulary() -> None:
    tested_codes = {
        "operation_requested",
        "operation_started",
        "operation_phase_changed",
        "operation_progressed",
        "operation_entity_linked",
        "operation_cancel_requested",
        "operation_cancel_observed",
        "operation_succeeded",
        "operation_failed",
        "operation_cancelled",
        "operation_interrupted",
        "operation_reconciled",
    }

    assert tested_codes == OPERATION_EVENT_CODES


@pytest.mark.parametrize(
    ("event_code", "context"),
    [
        ("not_an_event", {}),
        ("operation_started", {"request_body": "private-sentinel"}),
        (
            "operation_progressed",
            {"phase": "work", "progress_current": 6, "progress_total": 5, "progress_unit": "items"},
        ),
        (
            "operation_progressed",
            {"phase": "work", "progress_current": True, "progress_total": 5, "progress_unit": "items"},
        ),
        (
            "operation_entity_linked",
            {"subject_type": "credential", "subject_id": SUBJECT_ID, "role": "target"},
        ),
        ("operation_failed", {"error_code": "raw_secret_value", "retryable": False}),
        ("operation_failed", {"error_code": "lease_token_exposed", "retryable": False}),
        ("operation_failed", {"error_code": r"c:\\private-sentinel", "retryable": False}),
        ("operation_interrupted", {"error_code": "raw_exception?private-sentinel", "retryable": False}),
    ],
)
def test_event_context_rejects_unknown_progress_subject_and_sensitive_context(
    event_code: str,
    context: dict[str, object],
) -> None:
    with pytest.raises(OperationPayloadError) as captured:
        operation_event_context(event_code, context)

    assert "private-sentinel" not in str(captured.value)
    assert "private-sentinel" not in repr(captured.value)


def test_fixed_safe_error_code_may_describe_secret_boundary_without_secret_material() -> None:
    assert operation_event_context(
        "operation_failed",
        {"error_code": "locator_secret_forbidden", "retryable": False},
    ) == {"error_code": "locator_secret_forbidden", "retryable": False}


@pytest.mark.parametrize("kind", sorted(OPERATION_KINDS))
def test_request_fingerprint_is_stable_for_mapping_order(kind: str) -> None:
    parameters = _request_parameters(kind)
    target_id = None if KIND_TARGET_TYPES[kind] is None else ACCOUNT_ID

    first = operation_request_fingerprint(kind, target_id=target_id, parameters=parameters)
    second = operation_request_fingerprint(
        kind,
        target_id=target_id,
        parameters=dict(reversed(list(parameters.items()))),
    )

    assert first == second
    assert len(first) == 64
    assert first == first.lower()


@pytest.mark.parametrize("kind", sorted(OPERATION_KINDS))
def test_request_fingerprint_binds_the_fixed_post_route(kind: str) -> None:
    parameters = _request_parameters(kind)
    target_id = None if KIND_TARGET_TYPES[kind] is None else ACCOUNT_ID
    normalized = {
        "schema_version": OPERATION_PAYLOAD_SCHEMA_VERSION,
        "method": "POST",
        "route": KIND_ROUTES[kind],
        "kind": kind,
        "target_type": KIND_TARGET_TYPES[kind],
        "target_id": target_id,
        "parameters": parameters,
    }
    encoded = json.dumps(normalized, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    expected = sha256(b"media-sync:operation-request:v1\0" + encoded).hexdigest()

    actual = operation_request_fingerprint(kind, target_id=target_id, parameters=parameters)

    assert actual == expected
    normalized["route"] = "/api/v1/not-the-bound-route"
    wrong_route = json.dumps(normalized, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    assert actual != sha256(b"media-sync:operation-request:v1\0" + wrong_route).hexdigest()


def test_request_fingerprint_changes_with_kind_target_or_parameter() -> None:
    base = operation_request_fingerprint(
        "account-login",
        target_id=ACCOUNT_ID,
        parameters=_request_parameters("account-login"),
    )
    changed_target = operation_request_fingerprint(
        "account-login",
        target_id=AUTHOR_ID,
        parameters=_request_parameters("account-login"),
    )
    parameters = _request_parameters("account-login")
    parameters["timeout_microseconds"] = 30_000_001
    changed_parameter = operation_request_fingerprint(
        "account-login",
        target_id=ACCOUNT_ID,
        parameters=parameters,
    )
    changed_kind = operation_request_fingerprint(
        "emby-export",
        target_id=ACCOUNT_ID,
        parameters=_request_parameters("emby-export"),
    )

    assert len({base, changed_target, changed_parameter, changed_kind}) == 4


@pytest.mark.parametrize(
    ("kind", "target_id", "parameters"),
    [
        (
            "account-login",
            ACCOUNT_ID,
            {**_request_parameters("account-login"), "worker_id": "user-chosen-owner"},
        ),
        (
            "asset-download",
            ASSET_ID,
            {**_request_parameters("asset-download"), "xhs_detail_reference_digest": "raw-secret-reference"},
        ),
        (
            "scheduler-run",
            None,
            {**_request_parameters("scheduler-run"), "request_body": "private-sentinel"},
        ),
        (
            "pipeline-run",
            None,
            {**_request_parameters("pipeline-run"), "source_url": "https://example.invalid/?token=private-sentinel"},
        ),
        (
            "emby-export",
            AUTHOR_ID,
            {**_request_parameters("emby-export"), "output_path": r"C:\\private-sentinel"},
        ),
        (
            "media-server-probe",
            None,
            {**_request_parameters("media-server-probe"), "server_url": "https://private-sentinel.invalid"},
        ),
        (
            "media-server-scan",
            None,
            {"profile_fingerprint": "raw-secret-reference"},
        ),
    ],
)
def test_request_fingerprint_rejects_owner_secret_body_url_and_path(
    kind: str,
    target_id: str | None,
    parameters: dict[str, object],
) -> None:
    with pytest.raises(OperationPayloadError) as captured:
        operation_request_fingerprint(kind, target_id=target_id, parameters=parameters)

    assert "private-sentinel" not in str(captured.value)
    assert "private-sentinel" not in repr(captured.value)


@pytest.mark.parametrize(
    ("kind", "target_id"),
    [
        ("scheduler-run", ACCOUNT_ID),
        ("media-server-probe", ACCOUNT_ID),
        ("media-server-scan", ACCOUNT_ID),
        ("account-login", None),
        ("account-login", "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"),
    ],
)
def test_request_fingerprint_enforces_target_shape(kind: str, target_id: object) -> None:
    with pytest.raises(OperationPayloadError, match="operation_request_identity_invalid"):
        operation_request_fingerprint(kind, target_id=target_id, parameters=_request_parameters(kind))


def test_idempotency_digest_is_stable_domain_separated_and_does_not_retain_key() -> None:
    key = "Client.Retry:2026-09-04_0001"

    digest = operation_idempotency_key_digest(key)

    assert digest == operation_idempotency_key_digest(key)
    assert digest != sha256(key.encode("ascii")).hexdigest()
    assert key not in digest
    assert len(digest) == 64


@pytest.mark.parametrize(
    "key",
    [
        "short",
        "x" * 129,
        "contains whitespace",
        "contains/slash/value",
        r"contains\\backslash",
        "非ASCII幂等键值",
    ],
)
def test_idempotency_key_shape_fails_closed_without_reflection(key: str) -> None:
    with pytest.raises(OperationPayloadError) as captured:
        operation_idempotency_key_digest(key)

    assert captured.value.code == "operation_idempotency_key_invalid"
    assert key not in str(captured.value)
    assert key not in repr(captured.value)


def test_unknown_kind_and_oversized_mapping_fail_with_fixed_codes() -> None:
    with pytest.raises(OperationPayloadError) as kind_error:
        operation_result_summary("private-sentinel", {})
    with pytest.raises(OperationPayloadError) as mapping_error:
        operation_result_summary("pipeline-run", {f"key_{index}": index for index in range(33)})

    assert kind_error.value.code == "operation_kind_invalid"
    assert mapping_error.value.code == "operation_result_invalid"
    assert "private-sentinel" not in repr(kind_error.value)
