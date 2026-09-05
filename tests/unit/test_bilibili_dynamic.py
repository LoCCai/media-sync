"""Original synthetic protocol examples; no copied remote responses or traffic."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from media_sync.domain import AssetKind, ContentKind, Platform
from media_sync.integrations.mediacrawler.bilibili_dynamic import (
    BILI_DYNAMIC_FIELD,
    BILI_DYNAMIC_SOURCE_FIELD,
    BiliDynamicError,
    BiliDynamicIdentity,
    BiliDynamicIdentityError,
    BiliDynamicImage,
    BiliDynamicPayload,
    BiliDynamicSource,
    BiliDynamicUnsupportedError,
    bili_dynamic_image_remote_ids,
    bili_dynamic_image_remote_ids_from_identities,
    parse_bili_dynamic_detail,
    parse_dynamic_identity,
    validate_bili_dynamic_image_url,
)
from media_sync.integrations.mediacrawler.normalizers import (
    NormalizationContext,
    RecordNormalizationError,
    normalize_record,
)
from media_sync.media.locator import MediaRequestProfile


def _image(name: str = "synthetic_a", *, key: str = "src") -> dict:
    return {key: f"https://i0.hdslb.com/bfs/new_dyn/{name}.jpg?token=synthetic-private", "width": 640, "height": 480}


def _item(kind: str = "WORD", *, opus: bool = False) -> dict:
    major = None
    if kind == "DRAW":
        major = {"type": "MAJOR_TYPE_DRAW", "draw": {"id": 7, "items": [_image(), _image("synthetic_b")]}}
    elif kind == "AV":
        major = {
            "type": "MAJOR_TYPE_ARCHIVE",
            "archive": {"aid": "456", "bvid": "BV1234567890", "title": "Owned video", "type": 1},
        }
    if opus:
        major = {"type": "MAJOR_TYPE_OPUS", "opus": {"summary": {"text": "TRUNCATED SUMMARY"}, "pics": []}}
    return {
        "id_str": "123456789012345",
        "type": f"DYNAMIC_TYPE_{kind}",
        "visible": True,
        "modules": {
            "module_author": {"mid": 123, "pub_ts": 1767225600, "type": "AUTHOR_TYPE_NORMAL"},
            "module_dynamic": {
                "desc": {"text": "  Original text\n第二行  "},
                "major": major,
                "additional": None,
                "topic": None,
            },
        },
    }


def _opus(kind: str = "WORD") -> dict:
    paragraphs = [
        {
            "para_type": 1,
            "align": 0,
            "text": {
                "nodes": [
                    {"type": "TEXT_NODE_TYPE_WORD", "word": {"words": "Complete "}},
                    {
                        "type": "TEXT_NODE_TYPE_RICH",
                        "rich": {"text": "@author", "jump_url": "https://example.invalid/ignored"},
                    },
                ]
            },
        },
        {
            "para_type": 1,
            "align": 0,
            "text": {"nodes": [{"type": "TEXT_NODE_TYPE_WORD", "word": {"words": "正文第二段"}}]},
        },
    ]
    if kind == "DRAW":
        paragraphs.append(
            {"para_type": 2, "align": 0, "pic": {"pics": [_image(key="url"), _image("synthetic_b", key="url")]}}
        )
    return {
        "id_str": "123456789012345",
        "basic": {"uid": 123, "comment_type": 11 if kind == "DRAW" else 17},
        "type": 1,
        "modules": [
            {"module_type": "MODULE_TYPE_TITLE", "module_title": {"text": "Full title"}},
            {"module_type": "MODULE_TYPE_AUTHOR", "module_author": {"mid": 123, "pub_ts": 1767225600}},
            {"module_type": "MODULE_TYPE_CONTENT", "module_content": {"paragraphs": paragraphs}},
        ],
    }


def _context() -> NormalizationContext:
    return NormalizationContext(Platform.BILI, "123", "Creator", "a" * 40, datetime(2026, 1, 1, tzinfo=UTC))


@pytest.mark.parametrize("kind", ["WORD", "DRAW", "AV"])
def test_owned_legacy_shapes_are_closed_immutable_payloads(kind: str) -> None:
    item = _item(kind)
    original = deepcopy(item)
    identity = parse_dynamic_identity(item, creator_id=123)
    payload = parse_bili_dynamic_detail(item, creator_id=123, expected_identity=identity)
    assert item == original
    assert payload.identity == BiliDynamicIdentity.from_mapping(identity.as_mapping())
    assert payload.text == "  Original text\n第二行  "
    assert len(payload.images) == (2 if kind == "DRAW" else 0)
    assert (payload.video_reference is not None) == (kind == "AV")
    assert BiliDynamicPayload.from_mapping(payload.as_mapping()) == payload
    with pytest.raises(FrozenInstanceError):
        payload.text = "changed"
    assert "synthetic-private" not in repr(payload)


@pytest.mark.parametrize("kind", ["WORD", "DRAW"])
def test_opus_requires_same_identity_full_body_and_ordered_images(kind: str) -> None:
    item = _item(kind, opus=True)
    with pytest.raises(BiliDynamicUnsupportedError):
        parse_bili_dynamic_detail(item, creator_id=123)
    payload = parse_bili_dynamic_detail(item, creator_id=123, opus_item=_opus(kind))
    assert payload.text == "Complete @author\n\n正文第二段"
    assert payload.title == "Full title" and "SUMMARY" not in payload.text
    assert len(payload.images) == (2 if kind == "DRAW" else 0)


@pytest.mark.parametrize("mutation", ["did", "author", "author_type", "bool_author", "timestamp", "type"])
def test_identity_drift_and_foreign_authors_do_not_gain_ownership(mutation: str) -> None:
    original = _item()
    identity = parse_dynamic_identity(original, creator_id=123)
    item = deepcopy(original)
    author = item["modules"]["module_author"]
    if mutation == "did":
        item["id_str"] = "987"
    elif mutation == "author":
        author["mid"] = 456
    elif mutation == "author_type":
        author["type"] = "AUTHOR_TYPE_PGC"
    elif mutation == "bool_author":
        author["mid"] = True
    elif mutation == "timestamp":
        author["pub_ts"] += 1
    else:
        item["type"] = "DYNAMIC_TYPE_DRAW"
    with pytest.raises(BiliDynamicError):
        parse_bili_dynamic_detail(item, creator_id=123, expected_identity=identity)


@pytest.mark.parametrize(
    "mutation",
    [
        "did",
        "basic_author",
        "module_author",
        "timestamp",
        "article",
        "fallback",
        "paragraph",
        "node",
        "module",
        "missing_content",
    ],
)
def test_opus_drift_or_unsupported_components_never_claim_complete_text(mutation: str) -> None:
    opus = _opus()
    if mutation == "did":
        opus["id_str"] = "456"
    elif mutation == "basic_author":
        opus["basic"]["uid"] = 456
    elif mutation == "module_author":
        opus["modules"][1]["module_author"]["mid"] = 456
    elif mutation == "timestamp":
        opus["modules"][1]["module_author"]["pub_ts"] += 1
    elif mutation == "article":
        opus["basic"]["comment_type"] = 12
    elif mutation == "fallback":
        opus["fallback"] = 1
    elif mutation == "paragraph":
        opus["modules"][2]["module_content"]["paragraphs"].append(
            {"para_type": 6, "link_card": {"text": "secret-private-omitted"}}
        )
    elif mutation == "node":
        opus["modules"][2]["module_content"]["paragraphs"][0]["text"]["nodes"].append(
            {"type": "TEXT_NODE_TYPE_UNKNOWN", "secret": "private"}
        )
    elif mutation == "module":
        opus["modules"].append({"module_type": "MODULE_TYPE_UNKNOWN", "private": "omitted"})
    else:
        opus["modules"].pop()
    with pytest.raises(BiliDynamicError) as rejected:
        parse_bili_dynamic_detail(_item(opus=True), creator_id=123, opus_item=opus)
    assert str(rejected.value) in {
        "bili_dynamic_schema_invalid",
        "bili_dynamic_unsupported",
        "bili_dynamic_identity_mismatch",
    }
    assert "private" not in str(rejected.value)


@pytest.mark.parametrize(
    "mutation", ["forward", "orig", "paid", "article", "hidden", "additional", "unknown_type", "live_image"]
)
def test_unsupported_original_or_media_shapes_remain_unconsumed(mutation: str) -> None:
    item = _item("DRAW")
    dynamic = item["modules"]["module_dynamic"]
    if mutation in {"forward", "article", "unknown_type"}:
        item["type"] = {
            "forward": "DYNAMIC_TYPE_FORWARD",
            "article": "DYNAMIC_TYPE_ARTICLE",
            "unknown_type": "DYNAMIC_TYPE_FUTURE",
        }[mutation]
        # Unsupported identities can remain in a snapshot; parsing is not a skip.
        assert parse_dynamic_identity(item, creator_id=123).dynamic_type == item["type"]
    elif mutation == "orig":
        item["orig"] = _item()
    elif mutation == "paid":
        dynamic["major"] = {"type": "MAJOR_TYPE_UPOWER_COMMON"}
    elif mutation == "hidden":
        item["visible"] = False
    elif mutation == "additional":
        dynamic["additional"] = {"type": "ADDITIONAL_TYPE_VOTE"}
    else:
        dynamic["major"]["draw"]["items"][0]["live_url"] = "https://private.invalid/video.mp4"
    with pytest.raises(BiliDynamicUnsupportedError):
        parse_bili_dynamic_detail(item, creator_id=123)


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.invalid/bfs/new_dyn/a.jpg",
        "https://i0.hdslb.com.evil.invalid/bfs/new_dyn/a.jpg",
        "https://i0.hdslb.com@evil.invalid/bfs/new_dyn/a.jpg",
        "https://i0.hdslb.com:443/bfs/new_dyn/a.jpg",
        "https://i0.hdslb.com/bfs/new_dyn/../a.jpg",
        "https://i0.hdslb.com/bfs/new_dyn/%61.jpg",
        "https://i0.hdslb.com/bfs/new_dyn/a.gif",
        "https://i0.hdslb.com/bfs/new_dyn/a.jpg#private",
        "https://i0.hdslb.com/bfs/new_dyn/a.jpg\n",
        "file:///bfs/new_dyn/a.jpg",
    ],
)
def test_image_authority_rejects_non_original_or_ambiguous_urls(url: str) -> None:
    with pytest.raises(BiliDynamicError):
        validate_bili_dynamic_image_url(url)


def test_complete_ordered_image_set_binds_every_slot_and_survives_only_locator_rotation() -> None:
    payload = parse_bili_dynamic_detail(_item("DRAW"), creator_id=123)
    ids = bili_dynamic_image_remote_ids(payload.identity.did, payload.images)
    assert all(remote_id.startswith(f"dynamic:{payload.identity.did}:image:") for remote_id in ids)
    rotated = tuple(
        replace(image, url=image.url.replace("i0.", "i1.").replace("synthetic-private", "rotated"))
        for image in payload.images
    )
    assert bili_dynamic_image_remote_ids(payload.identity.did, rotated) == ids
    assert bili_dynamic_image_remote_ids(payload.identity.did, payload.images[::-1]) != ids
    assert bili_dynamic_image_remote_ids(payload.identity.did, payload.images[:1]) != ids[:1]
    assert bili_dynamic_image_remote_ids("456", payload.images) != ids
    source = BiliDynamicSource.from_mapping(payload.source_mapping())
    assert (
        source.image_remote_ids
        == ids
        == bili_dynamic_image_remote_ids_from_identities(payload.identity.did, source.image_identities)
    )
    assert "http" not in json.dumps(source.as_mapping()) and "synthetic-private" not in json.dumps(source.as_mapping())
    tampered = payload.source_mapping()
    tampered["image_identities"] = list(reversed(tampered["image_identities"]))
    with pytest.raises(BiliDynamicIdentityError):
        BiliDynamicSource.from_mapping(tampered)


@pytest.mark.parametrize("kind", ["WORD", "DRAW", "AV"])
def test_private_normalizer_keeps_dynamic_namespace_and_private_urls_out_of_durable_raw(kind: str) -> None:
    payload = parse_bili_dynamic_detail(_item(kind), creator_id=123)
    record = payload.to_record()
    record["arbitrary_echo"] = "https://private.invalid/?token=must-not-persist"
    normalized = normalize_record(record, _context())
    assert normalized.content.remote_id == payload.identity.did and normalized.content.remote_type == "dynamic"
    assert normalized.content.kind is ContentKind.DYNAMIC and normalized.content.body == payload.text.strip()
    assert normalized.content.author_remote_id == "123"
    raw = dict(normalized.content.raw["record"])
    assert raw["text"] == payload.text
    assert BiliDynamicSource.from_mapping(raw[BILI_DYNAMIC_SOURCE_FIELD]).as_mapping() == payload.source_mapping()
    assert BILI_DYNAMIC_FIELD not in raw and "arbitrary_echo" not in raw
    assert "synthetic-private" not in repr(normalized.content.raw)
    assert tuple(asset.remote_id for asset in normalized.assets) == bili_dynamic_image_remote_ids(
        payload.identity.did, payload.images
    )
    assert all(asset.kind is AssetKind.IMAGE for asset in normalized.assets)
    assert [asset.position for asset in normalized.assets] == list(range(len(payload.images)))
    for asset in normalized.assets:
        assert normalized.runtime_asset_targets[asset.remote_id].request_profile is MediaRequestProfile.BILIBILI_MEDIA
    if kind == "AV":
        assert normalized.assets == () and raw[BILI_DYNAMIC_SOURCE_FIELD]["video_reference"]["aid"] == "456"


@pytest.mark.parametrize(
    "mutation", ["schema", "author", "did", "text", "timestamp", "type", "video_id", "image_identity", "extra_field"]
)
def test_private_payload_and_outer_record_must_agree(mutation: str) -> None:
    record = parse_bili_dynamic_detail(_item("DRAW"), creator_id=123).to_record()
    payload = record[BILI_DYNAMIC_FIELD]
    if mutation == "schema":
        payload["schema_version"] = True
    elif mutation == "author":
        payload["identity"]["author_mid"] = 456
    elif mutation == "did":
        record["dynamic_id"] = "456"
    elif mutation == "text":
        record["text"] = "changed"
    elif mutation == "timestamp":
        record["pub_ts"] = True
    elif mutation == "type":
        record["type"] = "DYNAMIC_TYPE_WORD"
    elif mutation == "video_id":
        record["video_id"] = "456"
    elif mutation == "image_identity":
        payload["images"][0]["identity"] = "a" * 64
    else:
        payload["unknown"] = True
    with pytest.raises(RecordNormalizationError):
        normalize_record(record, _context())


def test_legacy_text_only_dynamic_does_not_gain_forged_refresh_authority() -> None:
    normalized = normalize_record(
        {
            "dynamic_id": "legacy-nonnumeric-id",
            "text": "Legacy text",
            "pub_ts": 1767225600,
            BILI_DYNAMIC_SOURCE_FIELD: {"identity": {"did": "123"}, "forged": True},
        },
        _context(),
    )
    assert normalized.content.remote_id == "legacy-nonnumeric-id"
    assert normalized.assets == () and BILI_DYNAMIC_SOURCE_FIELD not in normalized.content.raw["record"]


def test_duplicate_or_overbudget_gallery_rejected_as_a_whole() -> None:
    image = BiliDynamicImage("https://i0.hdslb.com/bfs/new_dyn/a.jpg", 640, 480)
    with pytest.raises(BiliDynamicError):
        bili_dynamic_image_remote_ids("123", (image, image))
    with pytest.raises(BiliDynamicError):
        bili_dynamic_image_remote_ids(
            "123", tuple(replace(image, url=f"https://i0.hdslb.com/bfs/new_dyn/a{i}.jpg") for i in range(31))
        )


@pytest.mark.parametrize("target", ["major", "module", "content", "paragraph", "text", "node", "pic"])
def test_known_opus_shape_cannot_hide_a_future_content_component(target: str) -> None:
    item, opus = _item("DRAW", opus=True), _opus("DRAW")
    content = opus["modules"][2]["module_content"]
    paragraph = content["paragraphs"][0]
    selected = {
        "major": item["modules"]["module_dynamic"]["major"],
        "module": opus["modules"][2],
        "content": content,
        "paragraph": paragraph,
        "text": paragraph["text"],
        "node": paragraph["text"]["nodes"][0],
        "pic": content["paragraphs"][2]["pic"],
    }[target]
    selected["unsupported_card"] = {"text": "must not silently omit"}
    with pytest.raises(BiliDynamicUnsupportedError):
        parse_bili_dynamic_detail(item, creator_id=123, opus_item=opus)


@pytest.mark.parametrize("kind", ["WORD", "DRAW"])
def test_full_opus_text_and_gallery_normalize_without_summary_promotion(kind: str) -> None:
    payload = parse_bili_dynamic_detail(_item(kind, opus=True), creator_id=123, opus_item=_opus(kind))
    normalized = normalize_record(payload.to_record(), _context())
    assert normalized.content.body == "Complete @author\n\n正文第二段"
    assert normalized.content.title == "Full title"
    assert len(normalized.assets) == (2 if kind == "DRAW" else 0)
    assert "TRUNCATED" not in repr(normalized.content.raw)


@pytest.mark.parametrize("mutation", ["text", "paragraphs", "nodes", "width", "bool_timestamp", "bool_comment"])
def test_size_bounds_and_boolean_schema_drift_reject_whole_payload(mutation: str) -> None:
    item, opus = _item("DRAW", opus=True), _opus("DRAW")
    paragraphs = opus["modules"][2]["module_content"]["paragraphs"]
    if mutation == "text":
        paragraphs[0]["text"]["nodes"][0]["word"]["words"] = "a" * 100_001
    elif mutation == "paragraphs":
        paragraphs.extend([deepcopy(paragraphs[0]) for _ in range(1001)])
    elif mutation == "nodes":
        paragraphs[0]["text"]["nodes"] *= 501
    elif mutation == "width":
        paragraphs[2]["pic"]["pics"][0]["width"] = True
    elif mutation == "bool_timestamp":
        item["modules"]["module_author"]["pub_ts"] = True
    else:
        opus["basic"]["comment_type"] = True
    with pytest.raises(BiliDynamicError):
        parse_bili_dynamic_detail(item, creator_id=123, opus_item=opus)
