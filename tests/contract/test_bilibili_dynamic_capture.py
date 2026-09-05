"""Original dynamic examples through the real locked client/signer/video store.

Only HTTP transport and unrelated browser/database paths are stubbed. These
offline contracts do not qualify current platform behavior or account access.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from dataclasses import replace
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from media_sync.integrations.mediacrawler import bilibili_capture
from media_sync.integrations.mediacrawler.bilibili_dynamic import (
    BILI_DYNAMIC_DETAIL_FEATURES,
    BILI_DYNAMIC_FIELD,
    BILI_OPUS_DETAIL_FEATURES,
    BiliDynamicError,
    BiliDynamicIdentityError,
)
from media_sync.integrations.mediacrawler.bilibili_dynamic_capture import capture_dynamic_unit
from media_sync.integrations.mediacrawler.bilibili_media import BILIBILI_PAGES_FIELD
from media_sync.integrations.mediacrawler.bilibili_multifeed import (
    BiliDynamicLane,
    BiliDynamicSnapshotStore,
    BiliMultiFeedCoverage,
    BiliMultiFeedState,
)
from media_sync.integrations.mediacrawler.bilibili_scan import BILI_SCAN_COVERAGE_FILENAME, BILI_SCAN_IDENTITY_FIELD
from tests.contract.test_bilibili_bounded_capture import checkout as checkout
from tests.contract.test_bilibili_bounded_capture import runtime as runtime
from tests.unit.test_bilibili_dynamic import _item, _opus

_FEED = "/x/polymer/web-dynamic/v1/feed/space"
_DETAIL = "/x/polymer/web-dynamic/v1/detail"
_OPUS = "/x/polymer/web-dynamic/v1/opus/detail"
_NAV = "/x/web-interface/nav"
_VIEW = "/x/web-interface/view/detail"


def item(kind: str = "WORD", *, did: str = "123456789012345", opus: bool = False) -> dict:
    result = _item(kind, opus=opus)
    result["id_str"] = did
    result["modules"]["module_author"]["mid"] = 42
    if kind == "AV":
        result["modules"]["module_dynamic"]["major"]["archive"].update(aid="1", bvid="BV0000000001")
    return result


def opus_item(kind: str = "WORD", *, did: str = "123456789012345") -> dict:
    result = _opus(kind)
    result["id_str"] = did
    result["basic"]["uid"] = 42
    result["modules"][1]["module_author"]["mid"] = 42
    return result


def configure(runtime: Any, rows: list[dict], *, maximum: int = 2, resume: bool = False) -> dict:
    manifest = runtime.manifest
    manifest.max_items = maximum
    manifest.bili_scan = BiliMultiFeedState(manifest.bili_scan, "dynamics", "dynamics")
    runtime.crawler.bili_client.cookie_dict["buvid3"] = "offline-device-cookie"
    data = {"items": deepcopy(rows), "offset": "next-page", "has_more": 1}
    responses = {row["id_str"]: deepcopy(row) for row in rows}
    settings: dict[str, Any] = {"data": data, "details": responses, "opus": {}, "failure": None}
    if resume:
        store = BiliDynamicSnapshotStore(
            manifest.account_root,
            account_id=manifest.account_id,
            author_fingerprint_sha256=manifest.author_remote_id_fingerprint_sha256,
            upstream_sha=manifest.upstream_sha,
            creator_id=42,
        )
        page = store.persist(offset="", data=data)
        manifest.bili_scan = replace(
            manifest.bili_scan,
            dynamics=replace(manifest.bili_scan.dynamics, head=BiliDynamicLane(snapshot=page.ref)),
        )

    def transport(request: httpx.Request) -> httpx.Response | None:
        path = request.url.path
        if path not in {_FEED, _DETAIL, _OPUS}:
            return None
        query = parse_qs(request.url.query.decode(), keep_blank_values=True)
        assert all(len(values) == 1 for values in query.values())
        plain = {key: values[0] for key, values in query.items() if key not in {"wts", "w_rid"}}
        signer = sys.modules["media_platform.bilibili.help"].BilibiliSign("a" * 32, "b" * 32)
        assert query == {key: [value] for key, value in signer.sign(plain.copy()).items()}
        if settings["failure"] == path:
            return httpx.Response(200, json={"code": -404, "message": "synthetic-private-error"})
        if path == _FEED:
            assert plain == {
                "offset": "",
                "host_mid": "42",
                "platform": "web",
                "features": BILI_DYNAMIC_DETAIL_FEATURES,
            }
            response = settings["data"]
        elif path == _DETAIL:
            assert plain == {
                "id": plain["id"],
                "timezone_offset": "-480",
                "platform": "web",
                "gaia_source": "main_web",
                "features": BILI_DYNAMIC_DETAIL_FEATURES,
            }
            response = {"item": settings["details"][plain["id"]]}
        else:
            assert plain == {"id": plain["id"], "features": BILI_OPUS_DETAIL_FEATURES}
            response = {"item": settings["opus"][plain["id"]]}
        return httpx.Response(200, json={"code": 0, "data": response})

    runtime.behavior["dynamic_transport"] = transport
    return settings


def paths(runtime: Any) -> list[str]:
    return [request.url.path for request in runtime.requests]


def coverage(runtime: Any) -> BiliMultiFeedCoverage:
    value = (runtime.manifest.output_root / BILI_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8")
    assert "PRIVATE_TEST_ONLY" not in value and "synthetic-private" not in value
    result = BiliMultiFeedCoverage.from_json_line(value)
    result.validate(runtime.manifest.bili_scan, runtime.manifest.max_items)
    return result


def dynamics(runtime: Any) -> list[dict]:
    path = runtime.manifest.output_root / "media-sync-dynamics.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


@pytest.mark.parametrize("cached", [False, True])
async def test_discovery_is_signed_durable_and_does_not_fetch_details(runtime: Any, cached: bool) -> None:
    configure(runtime, [item("WORD"), item("DRAW", did="123456789012346")])
    runtime.behavior["cached_wbi"] = cached
    client = runtime.crawler.bili_client
    original_request, original_keys = client.request, client.get_wbi_keys
    bilibili_capture.install_bilibili_capture_shim(runtime.manifest)
    await runtime.crawler.get_creator_videos(42)
    result = coverage(runtime)
    assert result.stop_reason == "snapshot_saved" and result.record_keys == ()
    assert result.next_state.dynamics.head.snapshot is not None
    assert result.next_state.dynamics.head.index == 0
    assert paths(runtime) == ([] if cached else [_NAV]) + [_FEED]
    assert not runtime.rows and not dynamics(runtime)
    assert client.request == original_request and client.get_wbi_keys == original_keys
    assert len(list(runtime.manifest.account_root.rglob("*.json"))) == 1


@pytest.mark.parametrize("kind,full", [("WORD", False), ("DRAW", False), ("WORD", True), ("DRAW", True), ("AV", False)])
async def test_snapshot_resume_exact_details_and_real_owned_av_store(runtime: Any, kind: str, full: bool) -> None:
    row = item(kind, opus=full)
    settings = configure(runtime, [row], resume=True)
    settings["opus"][row["id_str"]] = opus_item(kind)
    client = runtime.crawler.bili_client
    original_request, original_keys = client.request, client.get_wbi_keys
    bilibili_capture.install_bilibili_capture_shim(runtime.manifest)
    await runtime.crawler.get_creator_videos(42)
    result = coverage(runtime)
    assert result.stop_reason == "page_end" and result.next_state.dynamics.head.offset == "next-page"
    assert result.next_state.dynamics.head.snapshot is None
    assert paths(runtime) == [_NAV, _DETAIL] + ([_OPUS] if full else []) + ([_VIEW] if kind == "AV" else [])
    assert runtime.sleeps == [0.01] * (len(paths(runtime)) - 1)
    assert client.request == original_request and client.get_wbi_keys == original_keys
    records = dynamics(runtime)
    assert len(records) == 1 and records[0]["dynamic_id"] == row["id_str"]
    private = records[0][BILI_DYNAMIC_FIELD]
    assert private["text"] == (
        "Complete @author\n\n正文第二段" if full else row["modules"]["module_dynamic"]["desc"]["text"]
    )
    assert len(private["images"]) == (2 if kind == "DRAW" else 0)
    if kind == "AV":
        assert result.record_keys == (("dynamic", row["id_str"]), ("content", "1"))
        assert len(runtime.rows) == 1
        stored = runtime.rows[0]
        assert stored["video_id"] == "1" and stored["create_time"] == 99999
        assert stored[BILI_SCAN_IDENTITY_FIELD]["pubdate"] == 99999
        assert stored[BILIBILI_PAGES_FIELD] == [{"page": 1, "cid": 101}]
        assert private["identity"]["pub_ts"] != stored["create_time"]
    else:
        assert not runtime.rows and result.record_keys == (("dynamic", row["id_str"]),)


@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "foreign",
        "did",
        "timestamp",
        "type",
        "forward",
        "paid",
        "shape",
        "opus_foreign",
        "opus_changed",
        "opus_missing",
        "opus_no_cookie",
        "av_owner",
        "av_pages",
        "av_aid",
        "av_bvid",
    ],
)
async def test_detail_failure_never_emits_coverage_or_advances_pending(runtime: Any, failure: str) -> None:
    full = failure.startswith("opus_")
    kind = "AV" if failure.startswith("av_") else "WORD"
    row = item(kind, opus=full)
    settings = configure(runtime, [row], resume=True)
    initial = runtime.manifest.bili_scan.to_cursor()
    detail = settings["details"][row["id_str"]]
    settings["opus"][row["id_str"]] = opus_item(kind)
    if failure == "missing":
        settings["failure"] = _DETAIL
    elif failure == "foreign":
        detail["modules"]["module_author"]["mid"] = 43
    elif failure == "did":
        detail["id_str"] = "987654321"
    elif failure == "timestamp":
        detail["modules"]["module_author"]["pub_ts"] += 1
    elif failure == "type":
        detail["type"] = "DYNAMIC_TYPE_DRAW"
    elif failure == "forward":
        detail["orig"] = item()
    elif failure == "paid":
        detail["modules"]["module_dynamic"]["major"] = {"type": "MAJOR_TYPE_UPOWER_COMMON"}
    elif failure == "shape":
        detail["modules"] = None
    elif failure == "opus_foreign":
        settings["opus"][row["id_str"]]["basic"]["uid"] = 43
    elif failure == "opus_changed":
        settings["opus"][row["id_str"]]["modules"][1]["module_author"]["pub_ts"] += 1
    elif failure == "opus_missing":
        settings["failure"] = _OPUS
    elif failure == "opus_no_cookie":
        runtime.crawler.bili_client.cookie_dict.pop("buvid3")
    else:
        runtime.behavior["failure"] = failure.removeprefix("av_")
    client = runtime.crawler.bili_client
    original_request, original_keys = client.request, client.get_wbi_keys
    bilibili_capture.install_bilibili_capture_shim(runtime.manifest)
    fetch_error = sys.modules["media_platform.bilibili.exception"].DataFetchError
    with pytest.raises((BiliDynamicError, fetch_error)):
        await runtime.crawler.get_creator_videos(42)
    assert client.request == original_request and client.get_wbi_keys == original_keys
    assert runtime.manifest.bili_scan.to_cursor() == initial
    assert not (runtime.manifest.output_root / BILI_SCAN_COVERAGE_FILENAME).exists()
    assert not dynamics(runtime) and not runtime.rows
    assert paths(runtime).count(_DETAIL) == 1 and _FEED not in paths(runtime)


@pytest.mark.parametrize("failure", ["upstream", "foreign", "unknown_schema"])
async def test_discovery_failure_is_not_empty_success(runtime: Any, failure: str) -> None:
    settings = configure(runtime, [item()])
    if failure == "upstream":
        settings["failure"] = _FEED
    elif failure == "foreign":
        settings["data"]["items"][0]["modules"]["module_author"]["mid"] = 43
    else:
        settings["data"]["has_more"] = "1"
    bilibili_capture.install_bilibili_capture_shim(runtime.manifest)
    fetch_error = sys.modules["media_platform.bilibili.exception"].DataFetchError
    with pytest.raises((BiliDynamicError, fetch_error)):
        await runtime.crawler.get_creator_videos(42)
    assert not (runtime.manifest.output_root / BILI_SCAN_COVERAGE_FILENAME).exists()
    assert not list(runtime.manifest.account_root.rglob("*.json"))
    assert paths(runtime) == [_NAV, _FEED]


@pytest.mark.parametrize("maximum,consumed", [(2, 1), (3, 2)])
async def test_av_two_record_cost_preserves_unconsumed_snapshot_tail(runtime: Any, maximum: int, consumed: int) -> None:
    configure(runtime, [item(did="101"), item("AV", did="102"), item(did="103")], maximum=maximum, resume=True)
    bilibili_capture.install_bilibili_capture_shim(runtime.manifest)
    await runtime.crawler.get_creator_videos(42)
    result = coverage(runtime)
    assert result.stop_reason == "item_limit"
    assert result.next_state.dynamics.head.index == consumed
    assert result.next_state.dynamics.head.snapshot == runtime.manifest.bili_scan.dynamics.head.snapshot
    assert result.next_state.dynamics.head.offset == ""
    assert paths(runtime).count(_DETAIL) == consumed
    assert len(result.record_keys) == (1 if maximum == 2 else 3)


async def test_multiple_details_share_one_locked_wbi_key_read_and_hard_thirty_cap(runtime: Any) -> None:
    configure(runtime, [item(did=str(index)) for index in range(1, 31)], maximum=100, resume=True)
    bilibili_capture.install_bilibili_capture_shim(runtime.manifest)
    await runtime.crawler.get_creator_videos(42)
    assert paths(runtime) == [_NAV] + [_DETAIL] * 30
    assert len(dynamics(runtime)) == 30 and len(coverage(runtime).record_keys) == 30


async def test_foreign_opus_summary_fails_before_optional_opus_request(runtime: Any) -> None:
    settings = configure(runtime, [item(opus=True)], resume=True)
    settings["details"]["123456789012345"]["modules"]["module_author"]["mid"] = 43
    bilibili_capture.install_bilibili_capture_shim(runtime.manifest)
    with pytest.raises(BiliDynamicIdentityError):
        await runtime.crawler.get_creator_videos(42)
    assert paths(runtime) == [_NAV, _DETAIL]


async def test_discovery_then_fair_history_then_exact_head_resume_without_relisting(runtime: Any) -> None:
    configure(runtime, [item(did="101"), item(did="102"), item(did="103")], maximum=2)
    client = runtime.crawler.bili_client

    async def forbidden_video(*args: object) -> None:
        pytest.fail("text-only unit must not store a video")

    first = await capture_dynamic_unit(runtime.manifest, client, 42, forbidden_video)
    assert first.stop_reason == "snapshot_saved" and first.next_state.dynamics.next_lane == "history"
    runtime.manifest.bili_scan = first.next_state
    second = await capture_dynamic_unit(runtime.manifest, client, 42, forbidden_video)
    assert second.stop_reason == "snapshot_saved" and second.next_state.dynamics.next_lane == "head"
    runtime.manifest.bili_scan = second.next_state
    third = await capture_dynamic_unit(runtime.manifest, client, 42, forbidden_video)
    assert third.stop_reason == "item_limit" and third.next_state.dynamics.head.index == 2
    assert third.next_state.dynamics.head.snapshot == first.next_state.dynamics.head.snapshot
    assert third.next_state.dynamics.history.index == 0
    assert paths(runtime) == [_NAV, _FEED, _NAV, _FEED, _NAV, _DETAIL, _DETAIL]
    assert [row["dynamic_id"] for row in dynamics(runtime)] == ["101", "102"]


@pytest.mark.parametrize("mutation", ["forward", "hidden", "additional", "unsupported_identity"])
async def test_unsupported_opus_summary_never_requests_full_opus(runtime: Any, mutation: str) -> None:
    row = item(opus=True)
    if mutation == "unsupported_identity":
        row["type"] = "DYNAMIC_TYPE_FORWARD"
    settings = configure(runtime, [row], resume=True)
    detail = settings["details"][row["id_str"]]
    if mutation == "forward":
        detail["orig"] = item()
    elif mutation == "hidden":
        detail["visible"] = False
    elif mutation == "additional":
        detail["modules"]["module_dynamic"]["additional"] = {"type": "ADDITIONAL_TYPE_VOTE"}
    bilibili_capture.install_bilibili_capture_shim(runtime.manifest)
    with pytest.raises(BiliDynamicError, match=r"^bili_dynamic_unsupported$"):
        await runtime.crawler.get_creator_videos(42)
    assert paths(runtime) == [_NAV, _DETAIL]
    assert not (runtime.manifest.output_root / BILI_SCAN_COVERAGE_FILENAME).exists()


async def test_corrupt_snapshot_is_rejected_before_http_without_leaking_path(runtime: Any) -> None:
    configure(runtime, [item()], resume=True)
    snapshot = next(runtime.manifest.account_root.rglob("*.json"))
    snapshot.write_bytes(snapshot.read_bytes() + b" ")
    client = runtime.crawler.bili_client
    original_request, original_keys = client.request, client.get_wbi_keys
    bilibili_capture.install_bilibili_capture_shim(runtime.manifest)
    with pytest.raises(BiliDynamicError, match=r"^bili_dynamic_schema_invalid$"):
        await runtime.crawler.get_creator_videos(42)
    assert not paths(runtime) and not dynamics(runtime)
    assert client.request == original_request and client.get_wbi_keys == original_keys


async def test_duplicate_av_reference_has_two_distinct_dynamics_and_one_owned_video(runtime: Any) -> None:
    configure(runtime, [item("AV", did="101"), item("AV", did="102")], maximum=4, resume=True)
    bilibili_capture.install_bilibili_capture_shim(runtime.manifest)
    await runtime.crawler.get_creator_videos(42)
    result = coverage(runtime)
    assert set(result.record_keys) == {("dynamic", "101"), ("dynamic", "102"), ("content", "1")}
    assert len(dynamics(runtime)) == 2 and len(runtime.rows) == 1
    assert paths(runtime) == [_NAV, _DETAIL, _VIEW, _DETAIL, _VIEW]


async def test_later_detail_failure_does_not_commit_earlier_successful_identity(runtime: Any) -> None:
    settings = configure(runtime, [item(did="101"), item(did="102")], resume=True)
    settings["details"]["102"]["id_str"] = "103"
    initial = runtime.manifest.bili_scan.to_cursor()
    bilibili_capture.install_bilibili_capture_shim(runtime.manifest)
    with pytest.raises(BiliDynamicIdentityError):
        await runtime.crawler.get_creator_videos(42)
    assert paths(runtime) == [_NAV, _DETAIL, _DETAIL]
    assert runtime.manifest.bili_scan.to_cursor() == initial
    assert not dynamics(runtime) and not (runtime.manifest.output_root / BILI_SCAN_COVERAGE_FILENAME).exists()
