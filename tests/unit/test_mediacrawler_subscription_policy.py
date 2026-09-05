"""Closed MediaCrawler subscription-policy v1 coverage."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from media_sync.integrations.mediacrawler.subscription_policy import (
    MAX_REQUEST_DELAY_SECONDS,
    MediaCrawlerSubscriptionPolicy,
    MediaCrawlerSubscriptionPolicyError,
    from_subscription_policy,
)


def _payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "allow_full_history": False,
        "request_delay_seconds": 2,
        "headless": True,
    }
    payload.update(changes)
    return payload


def test_policy_round_trips_exact_closed_payload_without_creator_secret() -> None:
    policy = MediaCrawlerSubscriptionPolicy.from_payload(_payload())

    assert policy == MediaCrawlerSubscriptionPolicy(
        allow_full_history=False,
        request_delay_seconds=2.0,
        headless=True,
    )
    assert policy.to_payload() == {
        "schema_version": 1,
        "allow_full_history": False,
        "request_delay_seconds": 2.0,
        "headless": True,
    }


@pytest.mark.parametrize(
    "reference",
    [
        "env:MEDIA_SYNC_CREATOR_INPUT",
        "file:accounts/bili.creator",
        "keyring:media-sync/bili-creator",
    ],
)
def test_policy_round_trips_canonical_opaque_creator_reference(reference: str) -> None:
    payload = _payload(creator_input={"secret_ref": reference})

    policy = MediaCrawlerSubscriptionPolicy.from_payload(payload)

    assert policy.creator_secret_ref == reference
    assert policy.to_payload() == payload | {"request_delay_seconds": 2.0}
    assert reference not in repr(policy)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"creator_input": {"secret_ref": "env:CREATOR"}},
        _payload(schema_version=2),
        _payload(schema_version=True),
        _payload(extra=True),
        _payload(cookie="a=b"),
        _payload(creator_url="https://example.test/creator?token=raw"),
    ],
)
def test_policy_rejects_missing_wrong_unknown_and_legacy_shapes(payload: Mapping[str, object]) -> None:
    with pytest.raises(MediaCrawlerSubscriptionPolicyError):
        MediaCrawlerSubscriptionPolicy.from_payload(payload)


@pytest.mark.parametrize(
    "creator_input",
    [
        "env:CREATOR",
        {},
        {"secret_ref": "env:CREATOR", "url": "https://example.test"},
        {"secret_ref": None},
        {"secret_ref": "https://example.test/creator?token=raw"},
        {"secret_ref": "cookie:a=b"},
        {"secret_ref": "env:COOKIE=value"},
        {"secret_ref": " ENV:CREATOR "},
        {"secret_ref": "ENV:CREATOR"},
    ],
)
def test_policy_rejects_raw_or_noncanonical_creator_input(creator_input: object) -> None:
    with pytest.raises(MediaCrawlerSubscriptionPolicyError, match=r"secret_ref|creator_input"):
        MediaCrawlerSubscriptionPolicy.from_payload(_payload(creator_input=creator_input))


@pytest.mark.parametrize(
    "delay",
    [True, False, None, "2", 0, -1, float("nan"), float("inf"), -float("inf"), MAX_REQUEST_DELAY_SECONDS + 0.1],
)
def test_policy_rejects_non_numeric_non_finite_or_out_of_bounds_delay(delay: object) -> None:
    with pytest.raises(MediaCrawlerSubscriptionPolicyError, match="request_delay_seconds"):
        MediaCrawlerSubscriptionPolicy.from_payload(_payload(request_delay_seconds=delay))


def test_policy_accepts_positive_delay_boundaries_and_normalizes_numbers() -> None:
    smallest = MediaCrawlerSubscriptionPolicy.from_payload(_payload(request_delay_seconds=0.001))
    largest = MediaCrawlerSubscriptionPolicy.from_payload(_payload(request_delay_seconds=MAX_REQUEST_DELAY_SECONDS))

    assert smallest.request_delay_seconds == 0.001
    assert largest.request_delay_seconds == 300.0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("allow_full_history", 0),
        ("allow_full_history", 1),
        ("allow_full_history", "false"),
        ("headless", 0),
        ("headless", 1),
        ("headless", "true"),
    ],
)
def test_policy_requires_real_booleans(field: str, value: object) -> None:
    with pytest.raises(MediaCrawlerSubscriptionPolicyError, match="boolean"):
        MediaCrawlerSubscriptionPolicy.from_payload(_payload(**{field: value}))


def test_outer_subscription_policy_is_closed_by_default() -> None:
    outer = {"mediacrawler": _payload(), "fake": {"unrelated": True}}

    with pytest.raises(MediaCrawlerSubscriptionPolicyError, match="adapter regions"):
        from_subscription_policy(outer)


def test_outer_subscription_policy_can_explicitly_ignore_other_adapter_regions() -> None:
    unrelated = object()
    outer = {"mediacrawler": _payload(), "future_adapter": unrelated}

    policy = from_subscription_policy(outer, allow_other_adapter_regions=True)

    assert policy == MediaCrawlerSubscriptionPolicy(False, 2.0, True)
    assert outer["future_adapter"] is unrelated


@pytest.mark.parametrize(
    "outer",
    [
        {},
        {"fake": {}},
        {"mediacrawler": None},
        {"mediacrawler": "legacy"},
        {"mediacrawler": {"creator_input": {"secret_ref": "env:CREATOR"}}},
    ],
)
def test_outer_subscription_policy_requires_a_valid_mediacrawler_object(outer: Mapping[str, object]) -> None:
    with pytest.raises(MediaCrawlerSubscriptionPolicyError):
        from_subscription_policy(outer, allow_other_adapter_regions=True)


def test_constructor_enforces_same_closed_value_boundaries() -> None:
    with pytest.raises(MediaCrawlerSubscriptionPolicyError, match="request_delay_seconds"):
        MediaCrawlerSubscriptionPolicy(False, True, True)  # type: ignore[arg-type]
    with pytest.raises(MediaCrawlerSubscriptionPolicyError, match="allow_full_history"):
        MediaCrawlerSubscriptionPolicy(0, 2, True)  # type: ignore[arg-type]
    with pytest.raises(MediaCrawlerSubscriptionPolicyError, match="headless"):
        MediaCrawlerSubscriptionPolicy(False, 2, 1)  # type: ignore[arg-type]
    with pytest.raises(MediaCrawlerSubscriptionPolicyError, match="secret_ref"):
        MediaCrawlerSubscriptionPolicy(False, 2, True, "https://example.test/raw")


@pytest.mark.parametrize("scope", ["uploads", "dynamics", "both"])
def test_explicit_bili_scope_round_trips_closed_v2_and_enforces_record_budget(scope: str) -> None:
    policy = MediaCrawlerSubscriptionPolicy(False, 2, True, bili_scope=scope)
    assert policy.effective_bili_scope == scope
    assert policy.to_payload() == _payload(schema_version=2, bili_scope=scope)
    assert MediaCrawlerSubscriptionPolicy.from_payload(policy.to_payload()) == policy
    policy.validate_bili_max_items(2)
    if scope == "uploads":
        policy.validate_bili_max_items(1)
    else:
        with pytest.raises(MediaCrawlerSubscriptionPolicyError, match="at least 2"):
            policy.validate_bili_max_items(1)


def test_legacy_v1_never_silently_enables_dynamic_capture() -> None:
    policy = MediaCrawlerSubscriptionPolicy.from_payload(_payload())
    assert policy.bili_scope is None and policy.effective_bili_scope == "uploads"
    assert policy.to_payload() == _payload()
    policy.validate_bili_max_items(1)


@pytest.mark.parametrize("scope", [None, True, 1, [], {}, "", "video", "DYNAMICS", " uploads"])
def test_v2_scope_is_required_and_closed(scope: object) -> None:
    with pytest.raises(MediaCrawlerSubscriptionPolicyError):
        MediaCrawlerSubscriptionPolicy.from_payload(_payload(schema_version=2, bili_scope=scope))


def test_v1_rejects_scope_and_v2_rejects_unknown_fields() -> None:
    for payload in (_payload(bili_scope="both"), _payload(schema_version=2, bili_scope="both", extra=True)):
        with pytest.raises(MediaCrawlerSubscriptionPolicyError):
            MediaCrawlerSubscriptionPolicy.from_payload(payload)
