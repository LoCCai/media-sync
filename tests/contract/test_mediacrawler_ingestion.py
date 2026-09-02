"""Contracts for bounded ingestion of the pinned MediaCrawler JSONL schemas."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from media_sync.domain import AssetKind, ContentKind, Platform
from media_sync.integrations.mediacrawler.bilibili_media import (
    BILIBILI_PAGES_FIELD,
    BILIBILI_PROGRESSIVE_PAGE_FIELD,
)
from media_sync.integrations.mediacrawler.envelope import (
    ADAPTER_NAME,
    ENVELOPE_SCHEMA,
    ENVELOPE_VERSION,
)
from media_sync.integrations.mediacrawler.jsonl import (
    JsonlLimitError,
    JsonlRecord,
    JsonlSourceError,
    QuarantineReason,
    read_jsonl,
)
from media_sync.integrations.mediacrawler.normalizers import (
    NormalizationContext,
    NormalizedMediaRecord,
    RecordNormalizationError,
    normalize_jsonl,
    normalize_record,
)
from media_sync.integrations.mediacrawler.tieba_media import (
    TIEBA_GALLERY_FIELD,
    TIEBA_IMAGE_FIELD,
    TIEBA_IMAGES_FIELD,
    TIEBA_MAX_GALLERY_IMAGES,
)
from media_sync.integrations.mediacrawler.weibo_media import WEIBO_IMAGES_FIELD, WEIBO_VIDEO_FIELD
from media_sync.integrations.mediacrawler.zhihu_media import ZHIHU_IMAGE_FIELD

PINNED_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "mediacrawler"
CHINA_TZ = timezone(timedelta(hours=8))
INGESTED_AT = datetime(2026, 1, 2, 8, tzinfo=CHINA_TZ)
PUBLISHED_AT = datetime(2026, 1, 1, tzinfo=UTC)

SOURCES = (
    (Platform.XHS, "xhs/contents.v1.jsonl"),
    (Platform.DY, "dy/contents.v1.jsonl"),
    (Platform.KS, "ks/contents.v1.jsonl"),
    (Platform.BILI, "bili/contents.v1.jsonl"),
    (Platform.BILI, "bili/dynamics.v1.jsonl"),
    (Platform.WB, "wb/contents.v1.jsonl"),
    (Platform.TIEBA, "tieba/contents.v1.jsonl"),
    (Platform.ZHIHU, "zhihu/contents.v1.jsonl"),
)

EXPECTED_FIELDS = {
    "xhs/contents.v1.jsonl": frozenset(
        [
            "note_id",
            "type",
            "title",
            "desc",
            "video_url",
            "time",
            "last_update_time",
            "creator_hash",
            "nickname",
            "liked_count",
            "collected_count",
            "comment_count",
            "share_count",
            "image_list",
            "tag_list",
            "last_modify_ts",
            "note_url",
            "source_keyword",
            "xsec_token",
        ]
    ),
    "dy/contents.v1.jsonl": frozenset(
        [
            "aweme_id",
            "aweme_type",
            "title",
            "desc",
            "create_time",
            "creator_hash",
            "nickname",
            "liked_count",
            "collected_count",
            "comment_count",
            "share_count",
            "last_modify_ts",
            "aweme_url",
            "cover_url",
            "video_download_url",
            "music_download_url",
            "note_download_url",
            "source_keyword",
        ]
    ),
    "ks/contents.v1.jsonl": frozenset(
        [
            "video_id",
            "video_type",
            "title",
            "desc",
            "create_time",
            "creator_hash",
            "nickname",
            "liked_count",
            "viewd_count",
            "last_modify_ts",
            "video_url",
            "video_cover_url",
            "video_play_url",
            "source_keyword",
        ]
    ),
    "bili/contents.v1.jsonl": frozenset(
        [
            "video_id",
            "video_type",
            "title",
            "desc",
            "create_time",
            "creator_hash",
            "nickname",
            "liked_count",
            "disliked_count",
            "video_play_count",
            "video_favorite_count",
            "video_share_count",
            "video_coin_count",
            "video_danmaku",
            "video_comment",
            "last_modify_ts",
            "video_url",
            "video_cover_url",
            "source_keyword",
        ]
    ),
    "bili/dynamics.v1.jsonl": frozenset(
        [
            "dynamic_id",
            "creator_hash",
            "user_name",
            "text",
            "type",
            "pub_ts",
            "total_comments",
            "total_forwards",
            "total_liked",
            "last_modify_ts",
        ]
    ),
    "wb/contents.v1.jsonl": frozenset(
        [
            "note_id",
            "content",
            "create_time",
            "create_date_time",
            "liked_count",
            "comments_count",
            "shared_count",
            "last_modify_ts",
            "note_url",
            "creator_hash",
            "nickname",
            "source_keyword",
        ]
    ),
    "tieba/contents.v1.jsonl": frozenset(
        [
            "note_id",
            "title",
            "desc",
            "note_url",
            "publish_time",
            "creator_hash",
            "user_nickname",
            "tieba_name",
            "tieba_link",
            "total_replay_num",
            "total_replay_page",
            "source_keyword",
            "last_modify_ts",
        ]
    ),
    "zhihu/contents.v1.jsonl": frozenset(
        [
            "content_id",
            "content_type",
            "content_text",
            "content_url",
            "question_id",
            "title",
            "desc",
            "created_time",
            "updated_time",
            "voteup_count",
            "comment_count",
            "source_keyword",
            "creator_hash",
            "user_nickname",
            "last_modify_ts",
        ]
    ),
}


def fixture_path(relative_path: str) -> Path:
    return FIXTURE_ROOT / relative_path


def context(platform: Platform, *, allow_bili_progressive_detail: bool = False) -> NormalizationContext:
    return NormalizationContext(
        platform=platform,
        creator_remote_id=f"trusted-{platform.value}-author",
        creator_display_name=f"可信作者-{platform.value}",
        upstream_sha=PINNED_SHA.upper(),
        ingested_at=INGESTED_AT,
        allow_bili_progressive_detail=allow_bili_progressive_detail,
    )


def all_records() -> dict[str, NormalizedMediaRecord]:
    records: dict[str, NormalizedMediaRecord] = {}
    for platform, relative_path in SOURCES:
        batch = normalize_jsonl(fixture_path(relative_path), context(platform))
        assert not batch.quarantined
        records.update({item.content.remote_id: item for item in batch.records})
    return records


def source_record(relative_path: str, index: int = 0) -> dict[str, object]:
    lines = fixture_path(relative_path).read_text(encoding="utf-8").splitlines()
    loaded = json.loads(lines[index])
    assert isinstance(loaded, dict)
    return loaded


def zhihu_answer_record() -> dict[str, object]:
    payload = source_record("zhihu/contents.v1.jsonl")
    payload.update(
        {
            "content_id": "456",
            "content_type": "answer",
            "content_url": "https://www.zhihu.com/question/123/answer/456",
            "question_id": "123",
        }
    )
    return payload


@pytest.mark.parametrize(("platform", "relative_path"), SOURCES)
def test_fixture_fields_match_the_pinned_store_shapes(platform: Platform, relative_path: str) -> None:
    del platform
    lines = fixture_path(relative_path).read_text(encoding="utf-8").splitlines()

    assert lines
    assert all(set(json.loads(line)) == EXPECTED_FIELDS[relative_path] for line in lines)


@pytest.mark.parametrize(("platform", "relative_path"), SOURCES)
def test_actual_seven_platform_fixtures_normalize_with_trusted_author_identity(
    platform: Platform,
    relative_path: str,
) -> None:
    batch = normalize_jsonl(fixture_path(relative_path), context(platform))

    assert batch.records
    assert not batch.quarantined
    assert not batch.truncated_tail
    for item in batch.records:
        assert item.author.platform is platform
        assert item.author.remote_id == f"trusted-{platform.value}-author"
        assert item.author.display_name == f"可信作者-{platform.value}"
        assert item.content.author_remote_id == item.author.remote_id
        envelope_record = item.content.raw["record"]
        assert isinstance(envelope_record, Mapping)
        assert str(envelope_record["creator_hash"]).startswith("untrusted-")


def test_combined_fixtures_cover_every_normalized_content_kind() -> None:
    kinds = {item.content.kind for item in all_records().values()}

    assert kinds == set(ContentKind)


def test_complete_versioned_envelope_is_attached_to_the_aggregate() -> None:
    item = normalize_jsonl(fixture_path("xhs/contents.v1.jsonl"), context(Platform.XHS)).records[0]
    raw = item.content.raw

    assert raw["schema"] == ENVELOPE_SCHEMA
    assert raw["version"] == ENVELOPE_VERSION
    assert raw["adapter"] == ADAPTER_NAME
    assert raw["platform"] == Platform.XHS.value
    assert raw["upstream_sha"] == PINNED_SHA
    assert raw["ingested_at"] == "2026-01-02T00:00:00+00:00"
    assert raw["record"] == source_record("xhs/contents.v1.jsonl")
    envelope_record = raw["record"]
    assert isinstance(envelope_record, Mapping)
    # The envelope is deliberately replay-complete, not persistence-safe. The
    # repository sink must redact it before storage.
    assert envelope_record["xsec_token"] == "secret-token"
    assert item.author.raw == raw
    assert all(asset.raw == raw for asset in item.assets)
    assert item.content.canonical_url == "https://www.xiaohongshu.com/explore/xhs-mixed-001"
    assert "xsec_token" not in (item.content.canonical_url or "")


def test_asset_order_ids_and_media_semantics_are_deterministic() -> None:
    records = all_records()

    xhs_assets = records["xhs-mixed-001"].assets
    assert tuple(asset.kind for asset in xhs_assets) == (
        AssetKind.IMAGE,
        AssetKind.IMAGE,
        AssetKind.VIDEO,
    )
    assert tuple(asset.position for asset in xhs_assets) == (0, 1, 0)
    assert tuple(asset.remote_id for asset in xhs_assets) == (
        "xhs-mixed-001:image:0",
        "xhs-mixed-001:image:1",
        "xhs-mixed-001:video:0",
    )

    dy_assets = records["dy-gallery-001"].assets
    assert tuple(asset.kind for asset in dy_assets) == (
        AssetKind.IMAGE,
        AssetKind.IMAGE,
        AssetKind.AUDIO,
        AssetKind.COVER,
    )
    assert all("not-playable" not in asset.source_url for asset in dy_assets)
    assert tuple(asset.mime_type for asset in dy_assets) == (
        "image/jpeg",
        "image/jpeg",
        "audio/mpeg",
        "image/jpeg",
    )

    ks_record = records["ks-video-001"]
    ks_assets = ks_record.assets
    assert ks_record.content.kind is ContentKind.VIDEO
    assert ks_record.content.remote_type == "content"
    assert ks_record.content.canonical_url == "https://www.kuaishou.com/short-video/ks-video-001"
    assert tuple(asset.kind for asset in ks_assets) == (
        AssetKind.VIDEO,
        AssetKind.COVER,
    )
    assert tuple(asset.position for asset in ks_assets) == (0, 0)
    assert tuple(asset.remote_id for asset in ks_assets) == (
        "ks-video-001:video:0",
        "ks-video-001:cover:0",
    )
    assert tuple(asset.source_url for asset in ks_assets) == (
        "https://cdn.example.invalid/ks/video.mp4",
        "https://cdn.example.invalid/ks/cover.jpg",
    )
    assert tuple(asset.mime_type for asset in ks_assets) == ("video/mp4", "image/jpeg")

    bili_assets = records["987654321"].assets
    assert tuple(asset.kind for asset in bili_assets) == (AssetKind.VIDEO, AssetKind.COVER)
    assert bili_assets[0].remote_id == "987654321:video:0"
    assert bili_assets[0].position == 0
    assert bili_assets[0].source_url is None
    assert bili_assets[1].remote_id == "987654321:cover:0"


def test_pinned_jsonl_asset_omissions_are_explicit_not_inferred_as_downloads() -> None:
    records = all_records()

    assert records["wb-text-001"].content.kind is ContentKind.TEXT
    assert records["tieba-article-001"].content.kind is ContentKind.ARTICLE
    assert records["bili-dynamic-001"].content.kind is ContentKind.DYNAMIC
    assert records["bili-dynamic-001"].content.remote_type == "dynamic"
    assert records["zhihu-article-001"].content.kind is ContentKind.ARTICLE
    assert records["zhihu-video-002"].content.kind is ContentKind.VIDEO
    for remote_id in (
        "wb-text-001",
        "tieba-article-001",
        "bili-dynamic-001",
        "zhihu-article-001",
        "zhihu-video-002",
    ):
        assert records[remote_id].assets == ()


def test_tieba_private_first_floor_image_materializes_one_article_owned_asset_and_is_stripped() -> None:
    note_id = "10376710029"
    identity = "489c9a3df8dcd1009420153b348b4710b8122fc3"
    signed = f"https://tiebapic.baidu.com/forum/pic/item/{identity}.jpg?tbpicau=2026-09-02-17_contract"
    payload = source_record("tieba/contents.v1.jsonl")
    payload.update(
        {
            "note_id": note_id,
            "note_url": f"https://tieba.baidu.com/p/{note_id}",
            TIEBA_IMAGE_FIELD: signed,
            "nested": [{TIEBA_IMAGE_FIELD: signed}],
        }
    )

    item = normalize_record(payload, context(Platform.TIEBA))

    assert item.content.kind is ContentKind.ARTICLE
    assert item.content.canonical_url == f"https://tieba.baidu.com/p/{note_id}"
    assert len(item.assets) == 1
    assert item.assets[0].kind is AssetKind.IMAGE
    assert item.assets[0].position == 0
    assert item.assets[0].remote_id == f"{note_id}:image:0"
    assert item.assets[0].source_url == signed
    assert item.assets[0].mime_type == "image/jpeg"
    assert TIEBA_IMAGE_FIELD not in item.content.raw["record"]
    assert TIEBA_IMAGE_FIELD not in item.content.raw["record"]["nested"][0]
    assert all(TIEBA_IMAGE_FIELD not in asset.raw["record"] for asset in item.assets)


def test_tieba_private_two_image_gallery_materializes_ordered_article_assets_and_is_stripped() -> None:
    note_id = "10376710029"
    identities = (
        "489c9a3df8dcd1009420153b348b4710b8122fc3",
        "0123456789abcdef0123456789abcdef01234567",
    )
    signed = [
        f"https://tiebapic.baidu.com/forum/pic/item/{identity}.jpg?tbpicau=2026-09-02-17_contract_{position}"
        for position, identity in enumerate(identities)
    ]
    payload = source_record("tieba/contents.v1.jsonl")
    payload.update(
        {
            "note_id": note_id,
            "note_url": f"https://tieba.baidu.com/p/{note_id}",
            TIEBA_IMAGES_FIELD: signed,
            "nested": [{TIEBA_IMAGES_FIELD: list(reversed(signed)), TIEBA_IMAGE_FIELD: signed[0]}],
        }
    )

    item = normalize_record(payload, context(Platform.TIEBA))

    assert item.content.kind is ContentKind.ARTICLE
    assert [(asset.kind, asset.position, asset.remote_id, asset.source_url) for asset in item.assets] == [
        (AssetKind.IMAGE, 0, f"{note_id}:image:0", signed[0]),
        (AssetKind.IMAGE, 1, f"{note_id}:image:1", signed[1]),
    ]
    assert TIEBA_IMAGES_FIELD not in item.content.raw["record"]
    assert TIEBA_IMAGES_FIELD not in item.content.raw["record"]["nested"][0]
    assert TIEBA_IMAGE_FIELD not in item.content.raw["record"]["nested"][0]
    assert all(TIEBA_IMAGES_FIELD not in asset.raw["record"] for asset in item.assets)


def test_tieba_private_v3_gallery_materializes_ordered_article_assets_and_is_stripped() -> None:
    note_id = "10376710029"
    signed = [
        (f"https://tiebapic.baidu.com/forum/pic/item/{position + 1:040x}.jpg?tbpicau=2026-09-02-17_v3_{position}")
        for position in range(3)
    ]
    payload = source_record("tieba/contents.v1.jsonl")
    payload.update(
        {
            "note_id": note_id,
            "note_url": f"https://tieba.baidu.com/p/{note_id}",
            TIEBA_GALLERY_FIELD: signed,
            "nested": [
                {
                    TIEBA_GALLERY_FIELD: list(reversed(signed)),
                    TIEBA_IMAGES_FIELD: signed[:2],
                    TIEBA_IMAGE_FIELD: signed[0],
                }
            ],
        }
    )

    item = normalize_record(payload, context(Platform.TIEBA))

    assert item.content.kind is ContentKind.ARTICLE
    assert [(asset.kind, asset.position, asset.remote_id, asset.source_url) for asset in item.assets] == [
        (AssetKind.IMAGE, position, f"{note_id}:image:{position}", url) for position, url in enumerate(signed)
    ]
    retained = repr(item.content.raw)
    assert all(field not in retained for field in (TIEBA_IMAGE_FIELD, TIEBA_IMAGES_FIELD, TIEBA_GALLERY_FIELD))
    assert all(
        all(field not in repr(asset.raw) for field in (TIEBA_IMAGE_FIELD, TIEBA_IMAGES_FIELD, TIEBA_GALLERY_FIELD))
        for asset in item.assets
    )


def test_tieba_two_image_claim_rejects_cardinality_duplicates_and_dual_fields() -> None:
    note_id = "10376710029"
    first = (
        "https://tiebapic.baidu.com/forum/pic/item/"
        "489c9a3df8dcd1009420153b348b4710b8122fc3.jpg?tbpicau=2026-09-02-17_first"
    )
    second = (
        "https://tiebapic.baidu.com/forum/pic/item/"
        "0123456789abcdef0123456789abcdef01234567.jpg?tbpicau=2026-09-02-17_second"
    )
    third = (
        "https://tiebapic.baidu.com/forum/pic/item/"
        "abcdef0123456789abcdef0123456789abcdef01.jpg?tbpicau=2026-09-02-17_third"
    )
    duplicate_hint = first.replace("17_first", "17_changed")
    claims = (
        {TIEBA_IMAGES_FIELD: []},
        {TIEBA_IMAGES_FIELD: [first]},
        {TIEBA_IMAGES_FIELD: [first, second, third]},
        {TIEBA_IMAGES_FIELD: [first, duplicate_hint]},
        {TIEBA_IMAGES_FIELD: [first, second], TIEBA_IMAGE_FIELD: first},
    )
    for claim in claims:
        payload = source_record("tieba/contents.v1.jsonl")
        payload.update(
            {
                "note_id": note_id,
                "note_url": f"https://tieba.baidu.com/p/{note_id}",
                **claim,
            }
        )

        with pytest.raises(RecordNormalizationError) as caught:
            normalize_record(payload, context(Platform.TIEBA))

        assert caught.value.reason is QuarantineReason.INVALID_RECORD


def test_tieba_v3_gallery_rejects_cardinality_duplicates_and_version_conflicts() -> None:
    note_id = "10376710029"
    signed = [
        (f"https://tiebapic.baidu.com/forum/pic/item/{position + 1:040x}.jpg?tbpicau=2026-09-02-17_v3_{position}")
        for position in range(TIEBA_MAX_GALLERY_IMAGES + 1)
    ]
    duplicate_hint = signed[0].replace("17_v3_0", "17_v3_duplicate")
    claims = (
        {TIEBA_GALLERY_FIELD: []},
        {TIEBA_GALLERY_FIELD: signed[:2]},
        {TIEBA_GALLERY_FIELD: [*signed[:2], duplicate_hint]},
        {TIEBA_GALLERY_FIELD: signed},
        {TIEBA_GALLERY_FIELD: signed[:3], TIEBA_IMAGE_FIELD: signed[0]},
        {TIEBA_GALLERY_FIELD: signed[:3], TIEBA_IMAGES_FIELD: signed[:2]},
    )
    for claim in claims:
        payload = source_record("tieba/contents.v1.jsonl")
        payload.update(
            {
                "note_id": note_id,
                "note_url": f"https://tieba.baidu.com/p/{note_id}",
                **claim,
            }
        )

        with pytest.raises(RecordNormalizationError) as caught:
            normalize_record(payload, context(Platform.TIEBA))

        assert caught.value.reason is QuarantineReason.INVALID_RECORD


def test_tieba_v3_gallery_accepts_the_64_image_boundary() -> None:
    note_id = "10376710029"
    signed = [
        (f"https://tiebapic.baidu.com/forum/pic/item/{position + 1:040x}.jpg?tbpicau=2026-09-02-17_v3_{position}")
        for position in range(TIEBA_MAX_GALLERY_IMAGES)
    ]
    payload = source_record("tieba/contents.v1.jsonl")
    payload.update(
        {
            "note_id": note_id,
            "note_url": f"https://tieba.baidu.com/p/{note_id}",
            TIEBA_GALLERY_FIELD: signed,
        }
    )

    item = normalize_record(payload, context(Platform.TIEBA))

    assert len(item.assets) == TIEBA_MAX_GALLERY_IMAGES
    assert tuple(asset.position for asset in item.assets) == tuple(range(TIEBA_MAX_GALLERY_IMAGES))
    assert tuple(asset.remote_id for asset in item.assets) == tuple(
        f"{note_id}:image:{position}" for position in range(TIEBA_MAX_GALLERY_IMAGES)
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"note_id": "01"},
        {"note_url": "https://tieba.baidu.com/p/10376710030"},
        {"note_url": "https://tieba.baidu.com/p/10376710029?pn=1"},
        {TIEBA_IMAGE_FIELD: ("https://tiebapic.baidu.com/forum/pic/item/489c9a3df8dcd1009420153b348b4710b8122fc3.jpg")},
    ],
)
def test_tieba_claimed_image_schema_drift_is_quarantined(changes: dict[str, object]) -> None:
    note_id = "10376710029"
    payload = source_record("tieba/contents.v1.jsonl")
    payload.update(
        {
            "note_id": note_id,
            "note_url": f"https://tieba.baidu.com/p/{note_id}",
            TIEBA_IMAGE_FIELD: (
                "https://tiebapic.baidu.com/forum/pic/item/"
                "489c9a3df8dcd1009420153b348b4710b8122fc3.jpg?tbpicau=2026-09-02-17_contract"
            ),
        }
    )
    payload.update(changes)

    with pytest.raises(RecordNormalizationError) as caught:
        normalize_record(payload, context(Platform.TIEBA))

    assert caught.value.reason is QuarantineReason.INVALID_RECORD


def test_bili_video_and_dynamic_ids_use_distinct_persistence_namespaces() -> None:
    video_payload = source_record("bili/contents.v1.jsonl")
    dynamic_payload = source_record("bili/dynamics.v1.jsonl")
    dynamic_payload["dynamic_id"] = video_payload["video_id"]

    video = normalize_record(video_payload, context(Platform.BILI)).content
    dynamic = normalize_record(dynamic_payload, context(Platform.BILI)).content

    assert video.remote_id == dynamic.remote_id
    assert (video.remote_type, dynamic.remote_type) == ("content", "dynamic")


def test_bili_progressive_detail_field_is_closed_and_detail_gated() -> None:
    payload = source_record("bili/contents.v1.jsonl")
    progressive_url = "https://cdn.example.test/bili/video.mp4?signature=ephemeral"
    payload["__media_sync_bili_progressive_url"] = progressive_url

    ordinary = normalize_record(payload, context(Platform.BILI))
    assert ordinary.assets[0].remote_id == "987654321:video:0"
    assert ordinary.assets[0].source_url is None
    assert "__media_sync_bili_progressive_url" not in ordinary.content.raw["record"]
    assert all("__media_sync_bili_progressive_url" not in asset.raw["record"] for asset in ordinary.assets)

    detail = normalize_record(
        payload,
        context(Platform.BILI, allow_bili_progressive_detail=True),
    )
    assert detail.assets[0].remote_id == "987654321:video:0"
    assert detail.assets[0].source_url == progressive_url
    assert "__media_sync_bili_progressive_url" not in detail.content.raw["record"]
    assert all("__media_sync_bili_progressive_url" not in asset.raw["record"] for asset in detail.assets)


def test_bili_multipart_pages_materialize_ordered_cid_bound_locator_only_assets() -> None:
    payload = source_record("bili/contents.v1.jsonl")
    payload[BILIBILI_PAGES_FIELD] = [
        {"page": 1, "cid": 24680},
        {"page": 2, "cid": 97531},
        {"page": 3, "cid": 86420},
    ]
    payload["nested_private_copy"] = {BILIBILI_PAGES_FIELD: [{"page": 1, "cid": 11111}]}

    item = normalize_record(payload, context(Platform.BILI))

    assert [(asset.kind, asset.position, asset.remote_id, asset.source_url) for asset in item.assets[:3]] == [
        (AssetKind.VIDEO, 0, "987654321:video:cid:24680", None),
        (AssetKind.VIDEO, 1, "987654321:video:cid:97531", None),
        (AssetKind.VIDEO, 2, "987654321:video:cid:86420", None),
    ]
    assert BILIBILI_PAGES_FIELD not in item.content.raw["record"]
    assert BILIBILI_PAGES_FIELD not in item.content.raw["record"]["nested_private_copy"]


def test_bili_captured_single_page_keeps_the_delivered_legacy_asset_identity() -> None:
    payload = source_record("bili/contents.v1.jsonl")
    progressive_url = "https://cdn.example.test/bili/single.mp4?signature=ephemeral-single"
    payload[BILIBILI_PAGES_FIELD] = [{"page": 1, "cid": 24680}]
    payload["__media_sync_bili_progressive_url"] = progressive_url

    ordinary = normalize_record(payload, context(Platform.BILI))
    detail = normalize_record(payload, context(Platform.BILI, allow_bili_progressive_detail=True))

    assert [(asset.remote_id, asset.position, asset.source_url) for asset in ordinary.assets[:1]] == [
        ("987654321:video:0", 0, None)
    ]
    assert [(asset.remote_id, asset.position, asset.source_url) for asset in detail.assets[:1]] == [
        ("987654321:video:0", 0, progressive_url)
    ]


def test_bili_sixty_four_page_capture_materializes_every_ordered_video_slot() -> None:
    payload = source_record("bili/contents.v1.jsonl")
    payload[BILIBILI_PAGES_FIELD] = [{"page": index, "cid": 20_000 + index} for index in range(1, 65)]

    item = normalize_record(payload, context(Platform.BILI))
    videos = tuple(asset for asset in item.assets if asset.kind is AssetKind.VIDEO)

    assert len(videos) == 64
    assert videos[0].remote_id == "987654321:video:cid:20001"
    assert videos[-1].remote_id == "987654321:video:cid:20064"
    assert [asset.position for asset in videos] == list(range(64))


def test_bili_multipart_detail_materializes_only_the_requested_ephemeral_page_url() -> None:
    payload = source_record("bili/contents.v1.jsonl")
    target_url = "https://cdn.example.test/bili/p2.mp4?signature=ephemeral-p2"
    payload[BILIBILI_PAGES_FIELD] = [
        {"page": 1, "cid": 24680},
        {"page": 2, "cid": 97531},
        {"page": 3, "cid": 86420},
    ]
    payload[BILIBILI_PROGRESSIVE_PAGE_FIELD] = {"cid": 97531, "url": target_url}

    ordinary = normalize_record(payload, context(Platform.BILI))
    detail = normalize_record(payload, context(Platform.BILI, allow_bili_progressive_detail=True))

    assert [asset.source_url for asset in ordinary.assets[:3]] == [None, None, None]
    assert [asset.source_url for asset in detail.assets[:3]] == [None, target_url, None]
    assert BILIBILI_PROGRESSIVE_PAGE_FIELD not in detail.content.raw["record"]


@pytest.mark.parametrize(
    "pages",
    [
        [],
        [{"page": 1, "cid": 24680}, {"page": 2, "cid": 24680}],
        [{"page": 2, "cid": 24680}],
        [{"page": index, "cid": 10_000 + index} for index in range(1, 66)],
    ],
)
def test_bili_invalid_or_unsupported_page_claims_never_fall_back_to_the_legacy_video_slot(
    pages: list[dict[str, int]],
) -> None:
    payload = source_record("bili/contents.v1.jsonl")
    payload[BILIBILI_PAGES_FIELD] = pages

    item = normalize_record(payload, context(Platform.BILI))

    assert all(asset.kind is not AssetKind.VIDEO for asset in item.assets)


def test_bili_dynamic_never_materializes_progressive_detail_asset() -> None:
    payload = source_record("bili/dynamics.v1.jsonl")
    payload["__media_sync_bili_progressive_url"] = "https://cdn.example.test/bili/dynamic.mp4"

    item = normalize_record(payload, context(Platform.BILI, allow_bili_progressive_detail=True))
    assert item.assets == ()
    assert "__media_sync_bili_progressive_url" not in item.content.raw["record"]


@pytest.mark.parametrize(
    ("images", "expected_kind"),
    [
        (
            [{"pid": "single-pid", "url": "https://i1.wp.com/wx1.sinaimg.cn/large/single-pid.JpEg"}],
            ContentKind.IMAGE,
        ),
        (
            [
                {"pid": "first-pid", "url": "https://i1.wp.com/wx1.sinaimg.cn/large/first-pid.jpg"},
                {"pid": "second-pid", "url": "https://i1.wp.com/wx2.sinaimg.cn/large/second-pid.png"},
            ],
            ContentKind.GALLERY,
        ),
    ],
)
def test_weibo_private_capture_materializes_ordered_images_without_persisting_the_shim_field(
    images: list[dict[str, str]],
    expected_kind: ContentKind,
) -> None:
    payload = source_record("wb/contents.v1.jsonl")
    payload["note_id"] = "5123456789012345"
    payload[WEIBO_IMAGES_FIELD] = images
    payload["future_nested_shape"] = {WEIBO_IMAGES_FIELD: images}

    item = normalize_record(payload, context(Platform.WB))

    expected_urls = tuple(image["url"] for image in images)
    assert item.content.kind is expected_kind
    assert tuple(asset.kind for asset in item.assets) == (AssetKind.IMAGE,) * len(images)
    assert tuple(asset.position for asset in item.assets) == tuple(range(len(images)))
    assert tuple(asset.remote_id for asset in item.assets) == tuple(
        f"5123456789012345:image:{position}" for position in range(len(images))
    )
    assert tuple(asset.source_url for asset in item.assets) == expected_urls
    assert tuple(asset.mime_type for asset in item.assets) == tuple(
        "image/png" if url.endswith(".png") else "image/jpeg" for url in expected_urls
    )
    durable_record = item.content.raw["record"]
    assert isinstance(durable_record, Mapping)
    assert WEIBO_IMAGES_FIELD not in durable_record
    nested = durable_record["future_nested_shape"]
    assert isinstance(nested, Mapping)
    assert WEIBO_IMAGES_FIELD not in nested
    assert all(asset.raw == item.content.raw for asset in item.assets)


@pytest.mark.parametrize(
    "images",
    [
        pytest.param("https://i1.wp.com/wx1.sinaimg.cn/large/not-a-list.jpg", id="scalar"),
        pytest.param([[{"pid": "nested", "url": "https://i1.wp.com/wx1.sinaimg.cn/large/nested.jpg"}]], id="nested"),
        pytest.param([{"pid": "missing-url"}], id="missing-key"),
        pytest.param(
            [
                {
                    "pid": "extra-key",
                    "url": "https://i1.wp.com/wx1.sinaimg.cn/large/extra-key.jpg",
                    "future": "drift",
                }
            ],
            id="extra-key",
        ),
        pytest.param(
            [
                {"pid": "duplicate", "url": "https://i1.wp.com/wx1.sinaimg.cn/large/first.jpg"},
                {"pid": "duplicate", "url": "https://i1.wp.com/wx2.sinaimg.cn/large/second.jpg"},
            ],
            id="duplicate-pid",
        ),
        pytest.param(
            [
                {"pid": "first", "url": "https://i1.wp.com/wx1.sinaimg.cn/large/duplicate.jpg"},
                {"pid": "second", "url": "https://i1.wp.com/wx1.sinaimg.cn/large/duplicate.jpg"},
            ],
            id="duplicate-url",
        ),
        pytest.param(
            [{"pid": "http", "url": "http://i1.wp.com/wx1.sinaimg.cn/large/http.jpg"}],
            id="not-https",
        ),
        pytest.param(
            [{"pid": "direct", "url": "https://wx1.sinaimg.cn/large/direct.jpg"}],
            id="not-proxy",
        ),
        pytest.param(
            [{"pid": "query", "url": "https://i1.wp.com/wx1.sinaimg.cn/large/query.jpg?token=private"}],
            id="query",
        ),
        pytest.param(
            [{"pid": "fragment", "url": "https://i1.wp.com/wx1.sinaimg.cn/large/fragment.jpg#private"}],
            id="fragment",
        ),
        pytest.param(
            [{"pid": "wrong-path", "url": "https://i1.wp.com/wx1.sinaimg.cn/original/wrong-path.jpg"}],
            id="wrong-size-path",
        ),
        pytest.param(
            [{"pid": "gif", "url": "https://i1.wp.com/wx1.sinaimg.cn/large/animated.gif"}],
            id="gif",
        ),
        pytest.param(
            [{"pid": "mp4", "url": "https://i1.wp.com/wx1.sinaimg.cn/large/video.mp4"}],
            id="mp4",
        ),
        pytest.param(
            [{"pid": "no-extension", "url": "https://i1.wp.com/wx1.sinaimg.cn/large/no-extension"}],
            id="no-extension",
        ),
        pytest.param(
            [{"pid": "avif", "url": "https://i1.wp.com/wx1.sinaimg.cn/large/image.avif"}],
            id="unsupported-extension",
        ),
        pytest.param(
            [{"pid": "foreign", "url": "https://i1.wp.com/evil.example/large/foreign.jpg"}],
            id="foreign-embedded-host",
        ),
    ],
)
def test_weibo_capture_drift_and_duplicates_fail_closed_to_text_without_assets(images: object) -> None:
    payload = source_record("wb/contents.v1.jsonl")
    payload["note_id"] = "5123456789012345"
    payload[WEIBO_IMAGES_FIELD] = images

    item = normalize_record(payload, context(Platform.WB))

    assert item.content.kind is ContentKind.TEXT
    assert item.assets == ()
    durable_record = item.content.raw["record"]
    assert isinstance(durable_record, Mapping)
    assert WEIBO_IMAGES_FIELD not in durable_record


@pytest.mark.parametrize(
    "eligibility_drift",
    [
        pytest.param({"note_id": "wb-text-001"}, id="non-numeric-id"),
        pytest.param({"note_id": "05123456789012345"}, id="non-canonical-numeric-id"),
        pytest.param({"retweeted_status": {}}, id="retweet"),
        pytest.param({"page_info": {"type": "video"}}, id="page-info"),
    ],
)
def test_weibo_nonordinary_or_noncanonical_posts_cannot_materialize_forged_images(
    eligibility_drift: dict[str, object],
) -> None:
    payload = source_record("wb/contents.v1.jsonl")
    payload["note_id"] = "5123456789012345"
    payload.update(eligibility_drift)
    payload[WEIBO_IMAGES_FIELD] = [{"pid": "forged", "url": "https://i1.wp.com/wx1.sinaimg.cn/large/forged.jpg"}]

    item = normalize_record(payload, context(Platform.WB))

    assert item.content.kind is ContentKind.TEXT
    assert item.assets == ()
    durable_record = item.content.raw["record"]
    assert isinstance(durable_record, Mapping)
    assert WEIBO_IMAGES_FIELD not in durable_record


def test_weibo_private_video_capture_materializes_one_video_asset_without_persisting_the_shim_field() -> None:
    video_url = "https://f.us.sinaimg.cn/o0/wb-ingest-video.mp4?KID=unistore,video&Expires=4102444800"
    payload = source_record("wb/contents.v1.jsonl")
    payload["note_id"] = "5123456789012345"
    payload[WEIBO_VIDEO_FIELD] = {"url": video_url}
    payload["future_nested_shape"] = {WEIBO_VIDEO_FIELD: {"url": video_url}}

    item = normalize_record(payload, context(Platform.WB))

    assert item.content.kind is ContentKind.VIDEO
    assert len(item.assets) == 1
    asset = item.assets[0]
    assert asset.kind is AssetKind.VIDEO
    assert asset.position == 0
    assert asset.remote_id == "5123456789012345:video:0"
    assert asset.source_url == video_url
    assert asset.mime_type == "video/mp4"
    durable_record = item.content.raw["record"]
    assert isinstance(durable_record, Mapping)
    assert WEIBO_VIDEO_FIELD not in durable_record
    nested = durable_record["future_nested_shape"]
    assert isinstance(nested, Mapping)
    assert WEIBO_VIDEO_FIELD not in nested
    assert asset.raw == item.content.raw


@pytest.mark.parametrize(
    "drift",
    [
        pytest.param("https://f.us.sinaimg.cn/o0/scalar.mp4?KID=unistore", id="scalar"),
        pytest.param({"url": "https://f.us.sinaimg.cn/o0/extra.mp4", "future": "drift"}, id="extra-key"),
        pytest.param({"url": "https://evil.example.test/o0/foreign.mp4?KID=unistore"}, id="foreign-host"),
        pytest.param({"url": "https://f.us.sinaimg.cn/o0/not-mp4.flv?KID=unistore"}, id="not-mp4"),
        pytest.param({"url": 42}, id="url-type"),
        pytest.param({}, id="missing-url"),
    ],
)
def test_weibo_private_video_capture_fails_closed_on_payload_drift(drift: object) -> None:
    payload = source_record("wb/contents.v1.jsonl")
    payload["note_id"] = "5123456789012345"
    payload[WEIBO_VIDEO_FIELD] = drift

    with pytest.raises(RecordNormalizationError):
        normalize_record(payload, context(Platform.WB))


@pytest.mark.parametrize(
    "eligibility_drift",
    [
        pytest.param({"note_id": "wb-text-001"}, id="non-numeric-id"),
        pytest.param({"note_id": "05123456789012345"}, id="non-canonical-numeric-id"),
        pytest.param({"retweeted_status": {}}, id="retweet"),
        pytest.param({"page_info": {"type": "video"}}, id="page-info"),
    ],
)
def test_weibo_video_capture_rejects_ineligible_or_dual_field_posts(eligibility_drift: dict[str, object]) -> None:
    payload = source_record("wb/contents.v1.jsonl")
    payload["note_id"] = "5123456789012345"
    payload.update(eligibility_drift)
    payload[WEIBO_VIDEO_FIELD] = {"url": "https://f.us.sinaimg.cn/o0/forged.mp4?KID=unistore"}

    with pytest.raises(RecordNormalizationError):
        normalize_record(payload, context(Platform.WB))


def test_weibo_video_and_image_private_fields_cannot_coexist() -> None:
    payload = source_record("wb/contents.v1.jsonl")
    payload["note_id"] = "5123456789012345"
    payload[WEIBO_VIDEO_FIELD] = {"url": "https://f.us.sinaimg.cn/o0/both.mp4?KID=unistore"}
    payload[WEIBO_IMAGES_FIELD] = [{"pid": "both", "url": "https://i1.wp.com/wx1.sinaimg.cn/large/both.jpg"}]

    with pytest.raises(RecordNormalizationError):
        normalize_record(payload, context(Platform.WB))


@pytest.mark.parametrize(
    ("image_url", "expected_mime"),
    [
        pytest.param("https://picx.zhimg.com/v2-a1b2c3.jpg?token=transient-one", "image/jpeg", id="jpeg-query"),
        pytest.param("https://pic1.zhimg.com/80/v2-deadbeef.jpeg", "image/jpeg", id="jpeg"),
        pytest.param("https://cdn-a.zhimg.com/path/image.png?token=transient-two", "image/png", id="png-query"),
        pytest.param("https://pic2.zhimg.com/v2-feed.webp", "image/webp", id="webp"),
    ],
)
def test_zhihu_private_answer_image_materializes_one_stable_asset_without_durable_locator(
    image_url: str,
    expected_mime: str,
) -> None:
    payload = zhihu_answer_record()
    payload[ZHIHU_IMAGE_FIELD] = image_url
    payload["future_nested_shape"] = {
        "items": [{ZHIHU_IMAGE_FIELD: "https://pic3.zhimg.com/nested.jpg?token=nested-private"}]
    }

    item = normalize_record(payload, context(Platform.ZHIHU))

    assert item.content.kind is ContentKind.ARTICLE
    assert item.content.remote_type == "content"
    assert item.content.remote_id == "456"
    assert item.content.canonical_url == "https://www.zhihu.com/question/123/answer/456"
    assert len(item.assets) == 1
    asset = item.assets[0]
    assert asset.kind is AssetKind.IMAGE
    assert asset.remote_id == "456:image:0"
    assert asset.content_remote_id == "456"
    assert asset.position == 0
    assert asset.source_url == image_url
    assert asset.mime_type == expected_mime
    assert item.author.raw == item.content.raw == asset.raw
    for raw in (item.author.raw, item.content.raw, asset.raw):
        retained = repr(raw)
        assert ZHIHU_IMAGE_FIELD not in retained
        assert "token=transient" not in retained
        assert "token=nested-private" not in retained


def test_zhihu_image_query_changes_do_not_change_content_or_asset_identity() -> None:
    first_payload = zhihu_answer_record()
    first_payload[ZHIHU_IMAGE_FIELD] = "https://picx.zhimg.com/v2-stable.jpg?token=first"
    second_payload = zhihu_answer_record()
    second_payload[ZHIHU_IMAGE_FIELD] = "https://picx.zhimg.com/v2-stable.jpg?token=second"

    first = normalize_record(first_payload, context(Platform.ZHIHU))
    second = normalize_record(second_payload, context(Platform.ZHIHU))

    assert first.content.remote_id == second.content.remote_id == "456"
    assert first.assets[0].remote_id == second.assets[0].remote_id == "456:image:0"
    assert first.assets[0].position == second.assets[0].position == 0
    assert first.assets[0].source_url != second.assets[0].source_url


def test_zhihu_answer_without_private_image_field_preserves_assetless_compatibility() -> None:
    item = normalize_record(zhihu_answer_record(), context(Platform.ZHIHU))

    assert item.content.kind is ContentKind.ARTICLE
    assert item.content.remote_id == "456"
    assert item.assets == ()


@pytest.mark.parametrize(
    "drift",
    [
        pytest.param({ZHIHU_IMAGE_FIELD: None}, id="none"),
        pytest.param(
            {ZHIHU_IMAGE_FIELD: ["https://picx.zhimg.com/v2-list.jpg"]},
            id="sequence",
        ),
        pytest.param({ZHIHU_IMAGE_FIELD: ""}, id="blank"),
        pytest.param(
            {ZHIHU_IMAGE_FIELD: "https://example.com/v2-foreign.jpg"},
            id="foreign-image-host",
        ),
        pytest.param(
            {ZHIHU_IMAGE_FIELD: "https://picx.zhimg.com/v2-empty-query.jpg?"},
            id="image-empty-query-delimiter",
        ),
        pytest.param({"content_type": "article"}, id="article"),
        pytest.param({"content_type": "zvideo"}, id="zvideo"),
        pytest.param({"content_type": "ANSWER"}, id="answer-case"),
        pytest.param({"content_id": "0"}, id="zero-answer-id"),
        pytest.param({"content_id": "0456"}, id="leading-zero-answer-id"),
        pytest.param({"content_id": 456}, id="non-string-answer-id"),
        pytest.param({"question_id": "0"}, id="zero-question-id"),
        pytest.param({"question_id": "0123"}, id="leading-zero-question-id"),
        pytest.param({"question_id": 123}, id="non-string-question-id"),
        pytest.param(
            {"content_url": "https://www.zhihu.com/question/999/answer/456"},
            id="question-id-drift",
        ),
        pytest.param(
            {"content_url": "https://www.zhihu.com/question/123/answer/999"},
            id="answer-id-drift",
        ),
        pytest.param(
            {"content_url": "https://www.zhihu.com/question/123/answer/456?token=not-canonical"},
            id="answer-url-query",
        ),
    ],
)
def test_zhihu_private_image_schema_and_identity_drift_are_quarantined(drift: dict[str, object]) -> None:
    payload = zhihu_answer_record()
    payload[ZHIHU_IMAGE_FIELD] = "https://picx.zhimg.com/v2-valid.jpg?token=transient"
    payload.update(drift)

    with pytest.raises(RecordNormalizationError) as raised:
        normalize_record(payload, context(Platform.ZHIHU))

    assert raised.value.reason is QuarantineReason.INVALID_RECORD
    assert "token=transient" not in repr(raised.value)


def test_replay_is_equal_and_mixed_timestamp_inputs_normalize_to_utc() -> None:
    first = all_records()
    replay = all_records()

    assert replay == first
    for item in first.values():
        assert item.content.published_at == PUBLISHED_AT


def test_valid_utf8_and_valid_final_json_without_newline_are_accepted(tmp_path: Path) -> None:
    payload = source_record("wb/contents.v1.jsonl")
    target = tmp_path / "valid-final.jsonl"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = read_jsonl(target)

    assert not result.truncated_tail
    assert not result.quarantined
    assert len(result.records) == 1
    assert result.records[0].value["content"] == "微博纯文本内容"


def test_initial_utf8_bom_is_accepted(tmp_path: Path) -> None:
    payload = json.dumps(source_record("xhs/contents.v1.jsonl"), ensure_ascii=False).encode()
    target = tmp_path / "bom.jsonl"
    target.write_bytes(b"\xef\xbb\xbf" + payload + b"\n")

    result = read_jsonl(target)

    assert len(result.records) == 1
    assert not result.quarantined


def test_invalid_unterminated_tail_is_tolerated_without_retaining_raw_data(tmp_path: Path) -> None:
    first = json.dumps(source_record("xhs/contents.v1.jsonl"), ensure_ascii=False).encode()
    secret = b"cookie=must-not-appear"
    target = tmp_path / "truncated.jsonl"
    target.write_bytes(first + b"\n" + b'{"note_id":"' + secret)

    batch = normalize_jsonl(target, context(Platform.XHS))

    assert len(batch.records) == 1
    assert batch.records_seen == 2
    assert batch.truncated_tail
    assert not batch.quarantined
    assert secret.decode() not in repr(batch)


def test_malformed_middle_line_is_quarantined_and_later_record_is_accepted(tmp_path: Path) -> None:
    first = source_record("xhs/contents.v1.jsonl")
    second = source_record("xhs/contents.v1.jsonl", 1)
    secret = "cookie=must-not-appear"
    target = tmp_path / "middle-error.jsonl"
    target.write_text(
        "\n".join(
            (json.dumps(first, ensure_ascii=False), f'{{"broken":"{secret}"', json.dumps(second, ensure_ascii=False))
        )
        + "\n",
        encoding="utf-8",
    )

    batch = normalize_jsonl(target, context(Platform.XHS))

    assert tuple(item.content.remote_id for item in batch.records) == ("xhs-mixed-001", "xhs-image-002")
    assert tuple(item.reason for item in batch.quarantined) == (QuarantineReason.INVALID_JSON,)
    assert batch.quarantined[0].line_number == 2
    assert secret not in repr(batch.quarantined[0])


def test_comments_and_unknown_zhihu_types_are_safely_quarantined(tmp_path: Path) -> None:
    target = tmp_path / "unknown.jsonl"
    target.write_text(
        json.dumps({"comment_id": "sensitive-comment", "content": "secret"}) + "\n",
        encoding="utf-8",
    )

    comment_batch = normalize_jsonl(target, context(Platform.WB))
    assert tuple(item.reason for item in comment_batch.quarantined) == (QuarantineReason.UNKNOWN_RECORD,)
    assert "sensitive-comment" not in repr(comment_batch.quarantined)

    with pytest.raises(RecordNormalizationError) as raised:
        normalize_record(
            {"content_id": "sensitive-id", "content_type": "comment", "content_text": "secret"},
            context(Platform.ZHIHU),
        )
    assert raised.value.reason is QuarantineReason.UNKNOWN_RECORD
    assert "sensitive-id" not in repr(raised.value)


def test_invalid_utf8_non_object_and_nonstandard_numbers_are_quarantined(tmp_path: Path) -> None:
    valid = json.dumps(source_record("wb/contents.v1.jsonl"), ensure_ascii=False).encode()
    target = tmp_path / "quarantine.jsonl"
    target.write_bytes(b'\xff\n[]\n{"value":NaN}\n' + valid + b"\n")

    result = read_jsonl(target)

    assert tuple(item.reason for item in result.quarantined) == (
        QuarantineReason.INVALID_UTF8,
        QuarantineReason.NON_OBJECT,
        QuarantineReason.INVALID_JSON,
    )
    assert len(result.records) == 1


def test_jsonl_records_and_errors_do_not_expose_raw_input_in_repr(tmp_path: Path) -> None:
    secret = "cookie=must-not-appear"
    target = tmp_path / "secret.jsonl"
    target.write_text(json.dumps({"note_id": "xhs-id", "desc": secret}) + "\n", encoding="utf-8")

    result = read_jsonl(target)
    record = result.records[0]

    assert isinstance(record, JsonlRecord)
    assert secret not in repr(record)
    with pytest.raises(RecordNormalizationError) as raised:
        normalize_record({"note_id": "", "desc": secret}, context(Platform.XHS))
    assert secret not in repr(raised.value)


def test_byte_and_record_caps_fail_with_stable_safe_codes(tmp_path: Path) -> None:
    line = fixture_path("xhs/contents.v1.jsonl").read_bytes().splitlines(keepends=True)[0]
    target = tmp_path / "limits.jsonl"
    target.write_bytes(line + line)

    with pytest.raises(JsonlLimitError) as byte_error:
        read_jsonl(target, max_bytes=len(line) - 1)
    assert byte_error.value.code == "byte_limit_exceeded"

    with pytest.raises(JsonlLimitError) as record_error:
        read_jsonl(target, max_records=1)
    assert record_error.value.code == "record_limit_exceeded"
    assert "上海清晨" not in repr(byte_error.value)
    assert "上海清晨" not in repr(record_error.value)


def test_line_length_cap_fails_before_materializing_an_oversized_record(tmp_path: Path) -> None:
    line = fixture_path("xhs/contents.v1.jsonl").read_bytes().splitlines(keepends=True)[0]
    target = tmp_path / "long-line.jsonl"
    target.write_bytes(line)

    with pytest.raises(JsonlLimitError) as raised:
        read_jsonl(target, max_line_bytes=len(line) - 1)

    assert raised.value.code == "line_limit_exceeded"
    assert "上海清晨" not in repr(raised.value)


def test_reader_rejects_overlong_paths_and_non_regular_sources(tmp_path: Path) -> None:
    with pytest.raises(JsonlSourceError) as path_error:
        read_jsonl(tmp_path / "input.jsonl", max_path_chars=1)
    assert path_error.value.code == "path_too_long"

    with pytest.raises(JsonlSourceError) as directory_error:
        read_jsonl(tmp_path)
    assert directory_error.value.code == "source_not_regular_file"
    assert str(tmp_path) not in repr(directory_error.value)


def test_reader_rejects_symbolic_link_sources(tmp_path: Path) -> None:
    target = tmp_path / "target.jsonl"
    target.write_text("{}\n", encoding="utf-8")
    link = tmp_path / "link.jsonl"
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError):
        pytest.skip("symbolic links are unavailable on this host")

    with pytest.raises(JsonlSourceError) as raised:
        read_jsonl(link)
    assert raised.value.code == "symlink_not_allowed"
