"""Kuaishou bounded creator-work shim: parse privacy, coverage sealing, restriction.

The signing fixture follows the goal's capture-replay posture: every list
exchange is replayed verbatim from a captured signed exchange — each carrying
its own ``__NS_hxfalcon`` query on the ``/rest/v/profile/feed`` request URL,
never re-derived — while details ride the unsigned GraphQL channel and never
receive signature material.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import UUID

import pytest

from media_sync.domain import Platform
from media_sync.integrations.mediacrawler.kuaishou_creator_capture import (
    install_kuaishou_creator_capture_shim,
    parse_kuaishou_creator_page,
)
from media_sync.integrations.mediacrawler.kuaishou_creator_work import (
    KUAISHOU_SCAN_COVERAGE_FILENAME,
    KUAISHOU_SCAN_IDENTITY_FIELD,
    KuaishouScanCoverage,
    KuaishouScanState,
)

ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000081")
USER_ID = "3x4sm73aye7jq7i"
CREATOR_REFERENCE = f"https://www.kuaishou.com/profile/{USER_ID}"
UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"


class IPBlockError(RuntimeError):
    pass


class DataFetchError(RuntimeError):
    pass


def _module(name: str, checkout: Path) -> ModuleType:
    module = ModuleType(name)
    module.__file__ = str(checkout / (name.replace(".", "/") + ".py"))
    return module


def _photo_id(index: int) -> str:
    return f"3x{index:013x}"


def _captured_exchange(
    pcursor_in: str,
    pcursor_next: str,
    indexes: list[int],
    signature: str,
) -> dict[str, object]:
    """One captured ``/rest/v/profile/feed`` exchange, replayed verbatim."""

    return {
        "request_url": f"https://www.kuaishou.com/rest/v/profile/feed?__NS_hxfalcon={signature}&caver=2",
        "request_body": {"user_id": USER_ID, "pcursor": pcursor_in, "page": "profile"},
        "response": {
            "result": 1,
            "pcursor": pcursor_next,
            "feeds": [{"photo": {"id": _photo_id(index), "caption": f"work-{index}"}, "type": 1} for index in indexes],
        },
    }


def _install_modules(
    monkeypatch: pytest.MonkeyPatch,
    checkout: Path,
    output_root: Path,
    exchanges: list[dict[str, object]],
    *,
    detail_failure: str | None = None,
    normalization_failure: str | None = None,
) -> tuple[type, list[dict[str, object]], list[str], list[str]]:
    checkout.mkdir(parents=True, exist_ok=True)
    stored: list[dict[str, object]] = []
    detail_calls: list[str] = []
    signed_urls: list[str] = []
    replayed = list(exchanges)

    class KuaishouJsonlStoreImplement:
        async def store_content(self, content_item: dict[str, object]) -> None:
            stored.append(content_item)

    class KuaiShouClient:
        async def get_video_by_creater_v2(self, user_id: str, pcursor: str = "") -> object:
            # The signature realm lives inside the client: the captured
            # request URL with its own __NS_hxfalcon query is replayed
            # verbatim and never re-derived.
            assert user_id == USER_ID
            exchange = replayed.pop(0)
            body = exchange["request_body"]
            assert isinstance(body, dict) and body["pcursor"] == pcursor
            signed_urls.append(exchange["request_url"])
            response = exchange["response"]
            if isinstance(response, BaseException):
                raise response
            return response

        async def get_video_info(self, photo_id: str) -> dict[str, object]:
            # Unsigned GraphQL channel: the call carries a bare photo id and
            # no signature material of any kind.
            assert "hxfalcon" not in photo_id
            detail_calls.append(photo_id)
            if detail_failure is not None and photo_id == detail_failure:
                raise DataFetchError
            return {
                "visionVideoDetail": {
                    "photo": {"id": photo_id, "caption": f"work-{photo_id}", "timestamp": 1_788_235_200_000},
                    "author": {"id": USER_ID},
                }
            }

    class KuaishouCrawler:
        def __init__(self) -> None:
            self.ks_client = KuaiShouClient()

        async def get_creators_and_videos(self) -> None:
            raise AssertionError("unbounded creator helper must be replaced")

    core = _module("media_platform.kuaishou.core", checkout)
    core.KuaishouCrawler = KuaishouCrawler
    client = _module("media_platform.kuaishou.client", checkout)
    client.KuaiShouClient = KuaiShouClient
    store = _module("store.kuaishou", checkout)
    logger = SimpleNamespace(
        debug=lambda *_args, **_kwargs: None,
        info=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
        exception=lambda *_args, **_kwargs: None,
    )
    store.utils = SimpleNamespace(logger=logger)
    core.utils = SimpleNamespace(logger=logger)

    async def update_kuaishou_video(*, video_item: dict[str, object]) -> None:
        photo = video_item["photo"]
        assert isinstance(photo, dict)
        if normalization_failure is not None and photo["id"] == normalization_failure:
            raise ValueError("synthetic quarantine")
        await KuaishouJsonlStoreImplement().store_content(
            {
                "video_id": photo["id"],
                "title": photo.get("caption"),
                "desc": photo.get("caption"),
                "create_time": photo.get("timestamp"),
                "liked_count": "0",
                "viewd_count": "0",
                "video_url": f"https://www.kuaishou.com/short-video/{photo['id']}",
                "video_cover_url": "",
                "video_play_url": "",
            }
        )

    store.update_kuaishou_video = update_kuaishou_video
    store_impl = _module("store.kuaishou._store_impl", checkout)
    store_impl.KuaishouJsonlStoreImplement = KuaishouJsonlStoreImplement
    helper = _module("media_platform.kuaishou.help", checkout)
    helper.parse_creator_info_from_url = lambda value: SimpleNamespace(user_id=USER_ID)
    errors = _module("media_platform.kuaishou.exception", checkout)
    errors.IPBlockError = IPBlockError
    errors.DataFetchError = DataFetchError
    config = _module("config", checkout)
    config.KS_CREATOR_ID_LIST = [CREATOR_REFERENCE]
    config.SAVE_DATA_OPTION = "jsonl"
    config.ENABLE_GET_COMMENTS = False
    config.ENABLE_GET_MEIDAS = False
    config.ENABLE_IP_PROXY = False
    config.MAX_CONCURRENCY_NUM = 1
    modules = {
        "media_platform.kuaishou.core": core,
        "media_platform.kuaishou.client": client,
        "media_platform.kuaishou.help": helper,
        "media_platform.kuaishou.exception": errors,
        "store.kuaishou": store,
        "store.kuaishou._store_impl": store_impl,
        "config": config,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return KuaishouCrawler, stored, detail_calls, signed_urls


def _manifest(output_root: Path, state: KuaishouScanState | None = None) -> SimpleNamespace:
    author_sha = hashlib.sha256(USER_ID.encode()).hexdigest()
    creator_sha = hashlib.sha256(CREATOR_REFERENCE.encode()).hexdigest()
    return SimpleNamespace(
        kuaishou_scan=state or KuaishouScanState.initial(ACCOUNT_ID, author_sha, creator_sha, UPSTREAM_SHA),
        platform=Platform.KS,
        account_id=ACCOUNT_ID,
        author_remote_id_fingerprint_sha256=author_sha,
        creator_fingerprint_sha256=creator_sha,
        upstream_sha=UPSTREAM_SHA,
        max_items=18,
        request_delay_seconds=0.001,
        output_root=output_root,
    )


def _run_shim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    output_root: Path,
    exchanges: list[dict[str, object]],
    state: KuaishouScanState | None = None,
    **failure_kwargs: str,
) -> tuple[list[dict[str, object]], list[str], list[str]]:
    checkout = tmp_path / "checkout"
    crawler_type, stored, detail_calls, signed_urls = _install_modules(
        monkeypatch,
        checkout,
        output_root,
        exchanges,
        **failure_kwargs,
    )
    manifest = _manifest(output_root, state)
    previous = os.getcwd()
    os.chdir(checkout)
    try:
        install_kuaishou_creator_capture_shim(manifest)  # type: ignore[arg-type]
    finally:
        os.chdir(previous)
    asyncio.run(crawler_type().get_creators_and_videos())
    return stored, detail_calls, signed_urls


def test_page_parser_reduces_listings_to_bounded_identities() -> None:
    exchange = _captured_exchange("", "echo-next", [1, 2], "sig-a")
    page = parse_kuaishou_creator_page(exchange["response"], input_cursor="")
    assert [identity.photo_id for identity in page.identities] == [_photo_id(1), _photo_id(2)]
    serialized = json.dumps(page.as_mapping(), sort_keys=True)
    assert "caption" not in serialized and "work-" not in serialized
    assert page.next_cursor == "echo-next"


@pytest.mark.parametrize(
    "payload",
    [
        {"result": "1", "pcursor": "next", "feeds": []},
        {"result": 50, "pcursor": "next", "feeds": []},
        {"result": 1, "feeds": []},
        {"result": 1, "pcursor": "next", "feeds": {}},
        {"result": 1, "pcursor": "next", "feeds": [{"caption": "no-photo"}]},
        {"result": 1, "pcursor": "next", "feeds": [{"photo": {"id": "bad id"}}]},
        {
            "result": 1,
            "pcursor": "next",
            "feeds": [
                {"photo": {"id": _photo_id(1)}},
                {"photo": {"id": _photo_id(1)}},
            ],
        },
    ],
)
def test_page_parser_rejects_ambiguous_progress(payload: object) -> None:
    with pytest.raises(RuntimeError, match="Kuaishou bounded"):
        parse_kuaishou_creator_page(payload, input_cursor="")


def test_installed_shim_seals_coverage_and_isolates_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    exchange = _captured_exchange("", "echo-0", [1, 2, 3], "sig-one")
    stored, detail_calls, signed_urls = _run_shim(
        monkeypatch,
        tmp_path,
        output_root,
        [exchange],
        detail_failure=_photo_id(2),
    )

    assert [item["video_id"] for item in stored] == [_photo_id(1), _photo_id(3)]
    assert sorted(detail_calls) == sorted([_photo_id(1), _photo_id(2), _photo_id(3)])
    assert signed_urls == [exchange["request_url"]]
    assert all(KUAISHOU_SCAN_IDENTITY_FIELD in item for item in stored)
    coverage_text = (output_root / KUAISHOU_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8")
    coverage = KuaishouScanCoverage.from_json_line(coverage_text)
    coverage.validate(
        _manifest(output_root).kuaishou_scan,
        18,
        normalized_remote_ids=(_photo_id(1), _photo_id(3)),
    )
    assert coverage.stop_reason == "unit_cap_reached"
    assert coverage.summary.page_complete is False
    assert coverage.summary.failed_count == 1
    assert coverage.public_summary()["source_end_observed"] is False


def test_one_rejected_store_write_does_not_hide_unrelated_works(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    exchange = _captured_exchange("", "echo-0", [1, 2, 3], "sig-one")
    stored, _detail_calls, _signed_urls = _run_shim(
        monkeypatch,
        tmp_path,
        output_root,
        [exchange],
        normalization_failure=_photo_id(2),
    )

    assert [item["video_id"] for item in stored] == [_photo_id(1), _photo_id(3)]
    coverage = KuaishouScanCoverage.from_json_line(
        (output_root / KUAISHOU_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8")
    )
    coverage.validate(
        _manifest(output_root).kuaishou_scan,
        18,
        normalized_remote_ids=(_photo_id(1), _photo_id(3)),
    )
    assert coverage.summary.failed_count == 1
    assert coverage.summary.page_complete is False


def test_list_access_restriction_is_not_source_end(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    banned = _captured_exchange("", "", [], "sig-one")
    banned["response"] = IPBlockError("restricted")
    _stored, _calls, signed_urls = _run_shim(monkeypatch, tmp_path, output_root, [banned])

    coverage = KuaishouScanCoverage.from_json_line(
        (output_root / KUAISHOU_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8")
    )
    assert coverage.stop_reason == "access_restricted"
    assert coverage.page is None
    assert coverage.public_summary()["source_end_observed"] is False
    assert signed_urls == [banned["request_url"]]
    coverage_text = (output_root / KUAISHOU_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8")
    assert "hxfalcon" not in coverage_text and USER_ID not in coverage_text


def test_banned_body_and_transport_failure_are_restricted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    rejected = _captured_exchange("", "", [], "sig-one")
    rejected["response"] = {"result": 50, "pcursor": "", "feeds": []}
    _stored, _calls, _urls = _run_shim(monkeypatch, tmp_path, output_root, [rejected])

    coverage = KuaishouScanCoverage.from_json_line(
        (output_root / KUAISHOU_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8")
    )
    assert coverage.stop_reason == "access_restricted"
    assert coverage.page is None
    assert coverage.public_summary()["source_end_observed"] is False


def test_three_signed_exchanges_replay_verbatim_to_sentinel_end(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    exchanges = [
        _captured_exchange("", "echo-1", [1, 2], "sig-alpha-0"),
        _captured_exchange("echo-1", "echo-2", [3, 4], "sig-beta-1"),
        _captured_exchange("echo-2", "no_more", [5, 6], "sig-gamma-2"),
    ]
    manifest = _manifest(output_root)
    cursor: str | None = None
    stored: list[dict[str, object]] = []
    signed_urls: list[str] = []
    coverage: KuaishouScanCoverage | None = None
    for exchange in exchanges:
        step_stored, _detail_calls, step_urls = _run_shim(
            monkeypatch,
            tmp_path,
            output_root,
            [exchange],
            state=KuaishouScanState.for_cursor(
                cursor,
                account_id=ACCOUNT_ID,
                author_fingerprint_sha256=manifest.author_remote_id_fingerprint_sha256,
                creator_fingerprint_sha256=manifest.creator_fingerprint_sha256,
                upstream_sha=UPSTREAM_SHA,
            ),
        )
        stored.extend(step_stored)
        signed_urls.extend(step_urls)
        coverage = KuaishouScanCoverage.from_json_line(
            (output_root / KUAISHOU_SCAN_COVERAGE_FILENAME).read_text(encoding="utf-8")
        )
        output_root.joinpath(KUAISHOU_SCAN_COVERAGE_FILENAME).unlink()
        cursor = coverage.next_state.to_cursor()

    # Each captured exchange was replayed verbatim: the captured signed URL
    # with its own signature, and the echoed pcursor carried into the next
    # unit unchanged.  No signature was ever re-derived.
    assert signed_urls == [exchange["request_url"] for exchange in exchanges]
    assert len({exchange["request_url"] for exchange in exchanges}) == 3
    assert [item["video_id"] for item in stored] == [_photo_id(index) for index in range(1, 7)]
    assert coverage is not None
    assert coverage.stop_reason == "no_more_echoed"
    assert coverage.next_state.page_cursor == "no_more"
    assert coverage.public_summary()["source_end_observed"] is True
