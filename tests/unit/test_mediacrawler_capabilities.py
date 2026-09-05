"""Closed, safe MediaCrawler platform-capability coverage."""

from __future__ import annotations

import json
from typing import cast

import pytest

from media_sync.domain import LoginMethod, Platform
from media_sync.integrations.mediacrawler import (
    CAPABILITY_SCHEMA_VERSION,
    MEDIACRAWLER_PLATFORM_CAPABILITIES,
    MediaCrawlerCapabilityError,
    capability_for,
    normalize_creator_stable_id,
    platform_capabilities_payload,
)
from media_sync.integrations.mediacrawler.policies import FULL_HISTORY_PLATFORMS


def test_capability_contract_is_versioned_complete_and_stably_ordered() -> None:
    payload = platform_capabilities_payload()
    platforms = cast(list[dict[str, object]], payload["platforms"])

    assert payload["version"] == CAPABILITY_SCHEMA_VERSION == 1
    assert [row["platform"] for row in platforms] == [platform.value for platform in Platform]
    assert tuple(capability.platform for capability in MEDIACRAWLER_PLATFORM_CAPABILITIES) == tuple(Platform)


def test_every_platform_exposes_the_closed_login_and_honest_live_contract() -> None:
    for platform in Platform:
        capability = capability_for(platform)

        assert capability.login_methods == (
            LoginMethod.QR,
            LoginMethod.COOKIE,
            LoginMethod.SAVED_SESSION,
        )
        assert capability.qr_login is True
        assert capability.requires_full_history_acknowledgement is (platform in FULL_HISTORY_PLATFORMS)
        assert capability.live_qualification == "NOT_RUN"
        assert capability.offline_shapes
        assert capability.limitations


def test_creator_secret_reference_is_exposed_only_for_xhs() -> None:
    allowing = [
        capability.platform
        for capability in MEDIACRAWLER_PLATFORM_CAPABILITIES
        if capability.creator_input.allows_secret_reference
    ]

    assert allowing == [Platform.XHS]


def test_bilibili_and_weibo_numeric_guidance_does_not_narrow_compatible_ids() -> None:
    for platform in (Platform.BILI, Platform.WB):
        capability = capability_for(platform)

        assert "numeric" in " ".join(capability.limitations).lower()
        assert capability.creator_input.examples == ("123456",)
        assert normalize_creator_stable_id("legacy.creator-ID_1") == "legacy.creator-ID_1"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("creator", "creator"),
        (" creator.ID_1-2 ", "creator.ID_1-2"),
        ("a" * 255, "a" * 255),
    ],
)
def test_stable_creator_id_normalization_accepts_only_the_conservative_compatibility_shape(
    raw: str,
    expected: str,
) -> None:
    assert normalize_creator_stable_id(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "a" * 256,
        "creator id",
        "作者",
        "https://example.invalid/creator",
        "creator?signature=private",
        "creator/path",
        "creator=value",
        "creator;value",
        "creator\nvalue",
    ],
)
def test_stable_creator_id_normalization_rejects_ambiguous_or_unsafe_values(raw: str) -> None:
    with pytest.raises(MediaCrawlerCapabilityError, match="stable non-secret identifier"):
        normalize_creator_stable_id(raw)


def test_capability_lookup_fails_closed_without_echoing_invalid_input() -> None:
    invalid = "private-platform-sentinel"

    with pytest.raises(MediaCrawlerCapabilityError) as raised:
        capability_for(invalid)  # type: ignore[arg-type]

    assert invalid not in str(raised.value)


def test_public_payload_is_fresh_json_and_contains_no_runtime_or_authority_examples() -> None:
    first = platform_capabilities_payload()
    second = platform_capabilities_payload()
    first_platforms = first["platforms"]
    second_platforms = second["platforms"]
    assert isinstance(first_platforms, list)
    assert isinstance(second_platforms, list)
    first_platforms.clear()
    assert len(second_platforms) == len(Platform)

    serialized = json.dumps(second, ensure_ascii=False).lower()
    for forbidden in (
        "://",
        "xsec_",
        "signature=",
        "authorization",
        "bearer ",
        "set-cookie",
        "c:\\\\",
        "/home/",
        "/users/",
    ):
        assert forbidden not in serialized


def test_payload_rows_have_only_the_closed_public_fields_and_canonical_examples() -> None:
    payload = platform_capabilities_payload()
    platforms = payload["platforms"]
    assert isinstance(platforms, list)

    for row in platforms:
        assert isinstance(row, dict)
        assert set(row) == {
            "platform",
            "display_name",
            "login_methods",
            "qr_login",
            "pasted_cookie_login",
            "creator_input",
            "requires_full_history_acknowledgement",
            "offline_shapes",
            "limitations",
            "live_qualification",
        }
        creator_input = row["creator_input"]
        assert row["pasted_cookie_login"] is (row["platform"] in {"bili", "wb", "xhs", "zhihu"})
        assert isinstance(creator_input, dict)
        assert set(creator_input) == {
            "kind",
            "label",
            "placeholder",
            "examples",
            "allows_secret_reference",
        }
        examples = creator_input["examples"]
        assert isinstance(examples, list)
        assert all(normalize_creator_stable_id(example) == example for example in examples)
