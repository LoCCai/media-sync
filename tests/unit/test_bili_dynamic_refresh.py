"""Explicit dynamic refresh identity never aliases a numeric video AID."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest

from media_sync.domain import AssetKind, LoginMethod, Platform
from media_sync.infrastructure.db.asset_identity import asset_source_hint, stable_asset_key
from media_sync.integrations.mediacrawler.bilibili_dynamic import (
    BiliDynamicIdentity,
    BiliDynamicImage,
    BiliDynamicPayload,
    bili_dynamic_image_remote_ids,
)
from media_sync.integrations.mediacrawler.detail_runner import MediaCrawlerDetailRequest, MediaCrawlerDetailResult
from media_sync.integrations.mediacrawler.refresh import MediaCrawlerLocatorRefresher, MediaCrawlerRefreshContext
from media_sync.media import AdapterRefreshLocator, MediaDownloadError, MediaRequestProfile
from media_sync.security import SecretValue

_DID = "123456789012345678"
_MID = "123456"
_PUB_TS = 1_783_296_000


def _request(**overrides: Any) -> MediaCrawlerDetailRequest:
    values: dict[str, Any] = {
        "account_id": UUID("11111111-1111-4111-8111-111111111111"),
        "subscription_id": UUID("22222222-2222-4222-8222-222222222222"),
        "platform": Platform.BILI,
        "login_method": LoginMethod.SAVED_SESSION,
        "content_remote_id": _DID,
        "author_remote_id": _MID,
        "bili_dynamic_detail": True,
        "bili_dynamic_type": "DYNAMIC_TYPE_DRAW",
        "bili_dynamic_pub_ts": _PUB_TS,
    }
    values.update(overrides)
    return MediaCrawlerDetailRequest(**values)


def test_dynamic_mode_is_explicit_and_exact_did_bound() -> None:
    request = _request()
    assert request.bili_dynamic_detail is True
    assert request.resolved_detail_reference() == _DID
    assert request.bili_progressive_detail is False and request.bili_video_cid is None
    assert replace(request, detail_reference=_DID).resolved_detail_reference() == _DID


@pytest.mark.parametrize(
    "overrides",
    [
        {"bili_dynamic_detail": 1},
        {"bili_dynamic_detail": False},
        {"platform": Platform.KS},
        {"bili_progressive_detail": True},
        {"bili_video_cid": 123},
        {"bili_dynamic_type": None},
        {"bili_dynamic_type": "DYNAMIC_TYPE_AV"},
        {"bili_dynamic_type": "DYNAMIC_TYPE_FORWARD"},
        {"bili_dynamic_pub_ts": None},
        {"bili_dynamic_pub_ts": True},
        {"bili_dynamic_pub_ts": 0},
        {"content_remote_id": "0123456789012345678"},
        {"content_remote_id": "BV1xx411c7mD"},
        {"author_remote_id": "another-author"},
        {"detail_reference": "987654321"},
        {"detail_reference": f"https://t.bilibili.com/{_DID}"},
        {"detail_reference": SecretValue(_DID)},
    ],
)
def test_dynamic_mode_rejects_ambiguous_or_unfenced_requests(overrides: dict[str, Any]) -> None:
    with pytest.raises(MediaDownloadError) as error:
        _request(**overrides)
    assert error.value.code == "locator_refresh_configuration_invalid"


def _payload() -> BiliDynamicPayload:
    return BiliDynamicPayload(
        BiliDynamicIdentity(_DID, "DYNAMIC_TYPE_DRAW", _PUB_TS, int(_MID)),
        "Original bounded gallery",
        None,
        (
            BiliDynamicImage("https://i0.hdslb.com/bfs/new_dyn/first.jpg?token=old", 640, 480),
            BiliDynamicImage("https://i0.hdslb.com/bfs/new_dyn/second.png?token=old", 720, 480),
        ),
    )


def _refresh_context(payload: BiliDynamicPayload | None = None, *, position: int = 0) -> MediaCrawlerRefreshContext:
    payload = payload or _payload()
    remote_ids = bili_dynamic_image_remote_ids(payload.identity.did, payload.images)
    remote_id = remote_ids[position]
    return MediaCrawlerRefreshContext(
        asset_id=UUID("33333333-3333-4333-8333-333333333333"),
        account_id=UUID("11111111-1111-4111-8111-111111111111"),
        subscription_id=UUID("22222222-2222-4222-8222-222222222222"),
        platform=Platform.BILI,
        login_method=LoginMethod.SAVED_SESSION,
        content_remote_type="dynamic",
        content_remote_id=payload.identity.did,
        author_remote_id=str(payload.identity.author_mid),
        author_display_name="Bound author",
        asset_remote_id=remote_id,
        asset_kind=AssetKind.IMAGE,
        asset_position=position,
        source_hint=asset_source_hint(payload.images[position].url),
        locator=AdapterRefreshLocator(
            "mediacrawler",
            stable_asset_key(
                platform="bili",
                content_remote_type="dynamic",
                content_remote_id=payload.identity.did,
                kind="image",
                position=position,
                remote_id=remote_id,
            ),
        ),
        bili_dynamic_type=payload.identity.dynamic_type,
        bili_dynamic_pub_ts=payload.identity.pub_ts,
        bili_dynamic_image_remote_ids=remote_ids,
    )


class _Runner:
    def __init__(self, *records: dict[str, object]) -> None:
        self.payload = b"".join((json.dumps(record) + "\n").encode() for record in records)
        self.requests: list[MediaCrawlerDetailRequest] = []

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        self.requests.append(request)
        return MediaCrawlerDetailResult(self.payload, "d6f7c5bb906b6dac40ddf343ef9e26438a3de092")


def test_refresh_allows_cdn_and_query_rotation_only_with_complete_image_identity() -> None:
    payload = _payload()
    context = _refresh_context(payload, position=1)
    rotated = replace(
        payload,
        images=tuple(
            replace(image, url=image.url.replace("i0.", "i2.").replace("old", "new")) for image in payload.images
        ),
    )
    runner = _Runner(rotated.to_record())
    result = MediaCrawlerLocatorRefresher(context, runner).resolve(context.locator)
    assert result.url == rotated.images[1].url
    assert result.request_profile is MediaRequestProfile.BILIBILI_MEDIA
    assert len(runner.requests) == 1
    request = runner.requests[0]
    assert request.bili_dynamic_detail and not request.bili_progressive_detail
    assert request.bili_dynamic_type == payload.identity.dynamic_type
    assert request.bili_dynamic_pub_ts == payload.identity.pub_ts
    assert request.content_remote_id == _DID and request.author_remote_id == _MID


@pytest.mark.parametrize(
    "change", ["did", "author", "timestamp", "tail", "order", "removed", "dimensions", "extra_view"]
)
def test_refresh_rejects_any_changed_dynamic_or_complete_ordered_attachment(change: str) -> None:
    payload = _payload()
    context = _refresh_context(payload)
    changed = payload
    if change == "did":
        changed = replace(payload, identity=replace(payload.identity, did="987654321012345678"))
    elif change == "author":
        changed = replace(payload, identity=replace(payload.identity, author_mid=654321))
    elif change == "timestamp":
        changed = replace(payload, identity=replace(payload.identity, pub_ts=_PUB_TS + 1))
    elif change == "tail":
        changed = replace(
            payload,
            images=(payload.images[0], replace(payload.images[1], url="https://i0.hdslb.com/bfs/new_dyn/other.png")),
        )
    elif change == "order":
        changed = replace(payload, images=tuple(reversed(payload.images)))
    elif change == "removed":
        changed = replace(payload, images=payload.images[:1])
    elif change == "dimensions":
        changed = replace(payload, images=(payload.images[0], replace(payload.images[1], width=999)))
    records = [changed.to_record()]
    if change == "extra_view":
        records.append({"video_id": _DID, "title": "unrequested ordinary video"})
    runner = _Runner(*records)
    with pytest.raises(MediaDownloadError) as error:
        MediaCrawlerLocatorRefresher(context, runner).resolve(context.locator)
    assert error.value.code in {
        "locator_refresh_schema_changed",
        "locator_refresh_asset_not_found",
        "locator_refresh_asset_mismatch",
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"bili_dynamic_type": None},
        {"bili_dynamic_pub_ts": None},
        {"bili_dynamic_image_remote_ids": ()},
        {"bili_dynamic_image_remote_ids": (f"{_DID}:image:0",)},
        {"bili_dynamic_image_remote_ids": ["wrong-type"]},
        {"bili_video_remote_ids": (f"{_DID}:video:0",)},
        {"detail_reference": "123"},
        {"asset_kind": AssetKind.VIDEO},
        {"content_remote_type": "content"},
        {"source_hint": "https://outside.invalid/first.jpg"},
    ],
)
def test_refresh_context_requires_a_closed_dynamic_image_slot(overrides: dict[str, Any]) -> None:
    with pytest.raises(MediaDownloadError) as error:
        replace(_refresh_context(), **overrides)
    assert error.value.code == "locator_refresh_configuration_invalid"
