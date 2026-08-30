"""Contracts for bounded ingestion of the pinned MediaCrawler JSONL schemas."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from media_sync.domain import AssetKind, ContentKind, Platform
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


def test_bili_dynamic_never_materializes_progressive_detail_asset() -> None:
    payload = source_record("bili/dynamics.v1.jsonl")
    payload["__media_sync_bili_progressive_url"] = "https://cdn.example.test/bili/dynamic.mp4"

    item = normalize_record(payload, context(Platform.BILI, allow_bili_progressive_detail=True))
    assert item.assets == ()
    assert "__media_sync_bili_progressive_url" not in item.content.raw["record"]


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
