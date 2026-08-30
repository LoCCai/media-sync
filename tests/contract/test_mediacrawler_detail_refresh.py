from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path
from uuid import UUID

import pytest

from media_sync.domain import AssetKind, LoginMethod, Platform
from media_sync.infrastructure.db.asset_identity import asset_source_hint, stable_asset_key
from media_sync.integrations.mediacrawler import detail_runner as detail_runner_module
from media_sync.integrations.mediacrawler.checkout import VerifiedCheckout, VerifiedPython
from media_sync.integrations.mediacrawler.detail_runner import MediaCrawlerDetailProcessRunner
from media_sync.integrations.mediacrawler.policies import WatchdogLimits
from media_sync.integrations.mediacrawler.refresh import (
    MediaCrawlerLocatorRefresher,
    MediaCrawlerRefreshContext,
)
from media_sync.media import AdapterRefreshLocator, MediaDownloadError, MediaRequestProfile
from media_sync.security import SecretValue

UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
ACCOUNT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SUBSCRIPTION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
ASSET_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
COOKIE_SENTINEL = "DETAIL-COOKIE-SENTINEL-91d4b7"
CONTENT_ID = "7525082444551310602"
SIGNED_URL = f"https://video.example.test/douyin/main.mp4?sign={COOKIE_SENTINEL}"
BILI_COVER = "https://image.example.test/bili/cover.jpg?token=bili-detail-sentinel"
BILI_VIDEO_URL = "https://video.example.test/bili/first.mp4?" + "deadline=4102444800&sig=ephemeral-sentinel"
_DEFAULT_BILI_VIEW = object()
_DEFAULT_BILI_PLAY = object()

_CONFIG = """
PLATFORM = "xhs"
LOGIN_TYPE = "qrcode"
CRAWLER_TYPE = "search"
COOKIES = "fixture-default"
"""

_MAIN = r"""
import json
import os
from pathlib import Path

import config

crawler = None


class FakeCrawler:
    async def start(self):
        assert config.PLATFORM == "dy"
        assert config.LOGIN_TYPE == "cookie"
        assert config.CRAWLER_TYPE == "detail"
        assert config.DY_SPECIFIED_ID_LIST == ["7525082444551310602"]
        assert config.SAVE_DATA_OPTION == "jsonl"
        assert config.MAX_CONCURRENCY_NUM == 1
        assert config.ENABLE_GET_COMMENTS is False
        assert config.ENABLE_GET_MEDIAS is False
        profile = Path(
            os.path.join(os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM)
        ).resolve()
        assert profile.name == "dy_user_data_dir"
        print("upstream stdout must not contaminate the detail frame")
        os.write(2, b"upstream stderr must not contaminate the detail frame\n")
        target = Path(config.SAVE_DATA_PATH) / "douyin" / "jsonl" / "detail_contents_fixture.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "aweme_id": "7525082444551310602",
            "title": "fixture",
            "desc": "fixture",
            "video_download_url": "https://video.example.test/douyin/main.mp4?sign=" + config.COOKIES,
        }
        target.write_text(json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8")


class CrawlerFactory:
    @staticmethod
    def create_crawler(platform):
        assert platform == "dy"
        return FakeCrawler()


async def main():
    global crawler
    crawler = CrawlerFactory.create_crawler(config.PLATFORM)
    await crawler.start()


async def async_cleanup():
    return None
"""

_BILI_MAIN = r"""
import config
from pathlib import Path

crawler = None
VIEW_RESPONSE = __BILI_VIEW_RESPONSE__
PLAY_RESPONSE = __BILI_PLAY_RESPONSE__
PLAY_RAISES = __BILI_PLAY_RAISES__
EXPECTED_CID = __BILI_EXPECTED_CID__
FORBIDDEN_URL = __BILI_FORBIDDEN_URL__


class FakeCrawler:
    async def get_video_info_task(self, aid, bvid, semaphore):
        assert aid == 987654321
        assert bvid == ""
        assert semaphore is not None
        if VIEW_RESPONSE is None:
            return None
        return {"View": VIEW_RESPONSE}

    async def get_video_play_url_task(self, aid, cid, semaphore):
        assert aid == 987654321
        assert cid == EXPECTED_CID
        assert semaphore is not None
        for path in Path(config.SAVE_DATA_PATH).rglob("*.jsonl"):
            retained = path.read_bytes()
            assert b"__media_sync_bili_progressive_url" not in retained
            if FORBIDDEN_URL:
                assert FORBIDDEN_URL.encode("utf-8") not in retained
        if PLAY_RAISES:
            raise RuntimeError("private play failure must be classified without echo")
        return PLAY_RESPONSE

    async def start(self):
        assert config.PLATFORM == "bili"
        assert config.CRAWLER_TYPE == "detail"
        await self.get_specified_videos(config.BILI_SPECIFIED_ID_LIST)


class CrawlerFactory:
    @staticmethod
    def create_crawler(platform):
        assert platform == "bili"
        return FakeCrawler()


async def main():
    raise AssertionError("numeric aid must use the pinned client's aid detail entry")


async def async_cleanup():
    return None
"""

_BILI_STORE = r"""
import json
from pathlib import Path

import config


async def update_bilibili_video(detail):
    view = detail["View"]
    target = Path(config.SAVE_DATA_PATH) / "bili" / "jsonl" / "detail_contents_fixture.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "video_id": str(view["aid"]),
        "video_type": "video",
        "title": view["title"],
        "desc": view["desc"],
        "video_url": "https://www.bilibili.com/video/av" + str(view["aid"]),
        "video_cover_url": view["pic"],
    }
    target.write_text(json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8")


async def update_up_info(detail):
    assert detail["View"]["aid"] == 987654321
"""


def _fake_checkout(root: Path) -> Path:
    checkout = root / "fake-mediacrawler"
    (checkout / "config").mkdir(parents=True)
    (checkout / "config" / "__init__.py").write_text(textwrap.dedent(_CONFIG).lstrip(), encoding="utf-8")
    (checkout / "main.py").write_text(textwrap.dedent(_MAIN).lstrip(), encoding="utf-8")
    return checkout.resolve()


def _fake_bili_checkout(
    root: Path,
    *,
    view: object = _DEFAULT_BILI_VIEW,
    play_response: object = _DEFAULT_BILI_PLAY,
    play_raises: bool = False,
    expected_cid: int | None = None,
) -> Path:
    checkout = root / "fake-mediacrawler-bili"
    (checkout / "config").mkdir(parents=True)
    (checkout / "store" / "bilibili").mkdir(parents=True)
    (checkout / "config" / "__init__.py").write_text(textwrap.dedent(_CONFIG).lstrip(), encoding="utf-8")
    active_view = view
    if active_view is _DEFAULT_BILI_VIEW:
        active_view = {
            "aid": 987654321,
            "cid": 24680,
            "title": "fixture",
            "desc": "fixture",
            "pic": BILI_COVER,
            "owner": {"mid": 42, "name": "fixture"},
            "stat": {},
        }
    active_play = (
        {"durl": [{"url": BILI_VIDEO_URL, "backup_url": ["https://unused.example.test/backup"]}]}
        if play_response is _DEFAULT_BILI_PLAY
        else play_response
    )
    inferred_cid = expected_cid
    if inferred_cid is None and isinstance(active_view, dict):
        pages = active_view.get("pages")
        if isinstance(pages, list) and pages and isinstance(pages[0], dict):
            inferred_cid = pages[0].get("cid") if isinstance(pages[0].get("cid"), int) else None
        elif isinstance(active_view.get("cid"), int):
            inferred_cid = active_view["cid"]
    forbidden_url = ""
    if isinstance(active_play, dict):
        durl = active_play.get("durl")
        if isinstance(durl, list) and durl and isinstance(durl[0], dict) and isinstance(durl[0].get("url"), str):
            forbidden_url = durl[0]["url"]
    main_source = (
        textwrap.dedent(_BILI_MAIN)
        .lstrip()
        .replace("__BILI_VIEW_RESPONSE__", repr(active_view))
        .replace("__BILI_PLAY_RESPONSE__", repr(active_play))
        .replace("__BILI_PLAY_RAISES__", repr(play_raises))
        .replace("__BILI_EXPECTED_CID__", repr(inferred_cid))
        .replace("__BILI_FORBIDDEN_URL__", repr(forbidden_url))
    )
    (checkout / "main.py").write_text(main_source, encoding="utf-8")
    (checkout / "store" / "__init__.py").write_text("", encoding="utf-8")
    (checkout / "store" / "bilibili" / "__init__.py").write_text(
        textwrap.dedent(_BILI_STORE).lstrip(),
        encoding="utf-8",
    )
    return checkout.resolve()


def _bili_process_runner(tmp_path: Path, checkout: Path) -> MediaCrawlerDetailProcessRunner:
    lock_path = tmp_path / "upstreams.lock.json"
    lock_path.write_text("{}", encoding="utf-8")
    return MediaCrawlerDetailProcessRunner(
        lock_path=lock_path,
        integration_root=tmp_path / "runtime",
        python_executable=Path(sys.executable),
        license_acknowledged=True,
        checkout_verifier=lambda _path, _accepted: VerifiedCheckout(
            root=checkout,
            commit=UPSTREAM_SHA,
            repository="https://github.com/NanmiCoder/MediaCrawler.git",
            license_name="NON-COMMERCIAL LEARNING LICENSE 1.1",
            lock_path=lock_path,
        ),
        python_verifier=lambda path: VerifiedPython(path),
    )


def _bili_video_context() -> MediaCrawlerRefreshContext:
    remote_id = "987654321:video:0"
    locator = AdapterRefreshLocator(
        adapter="mediacrawler",
        asset_key=stable_asset_key(
            platform="bili",
            content_remote_type="content",
            content_remote_id="987654321",
            kind="video",
            position=0,
            remote_id=remote_id,
        ),
    )
    return MediaCrawlerRefreshContext(
        asset_id=ASSET_ID,
        account_id=ACCOUNT_ID,
        subscription_id=SUBSCRIPTION_ID,
        platform=Platform.BILI,
        login_method=LoginMethod.QR,
        content_remote_type="content",
        content_remote_id="987654321",
        author_remote_id="creator-42",
        author_display_name="Fixture creator",
        asset_remote_id=remote_id,
        asset_kind=AssetKind.VIDEO,
        asset_position=0,
        source_hint=None,
        locator=locator,
        watchdogs=WatchdogLimits(max_seconds=10, poll_seconds=0.01),
    )


def test_detail_process_runner_uses_detail_mode_and_cleans_signed_jsonl(tmp_path: Path) -> None:
    checkout = _fake_checkout(tmp_path)
    lock_path = tmp_path / "upstreams.lock.json"
    lock_path.write_text(json.dumps({"fake": True}), encoding="utf-8")
    integration_root = tmp_path / "runtime"

    def verify_checkout(_path: Path, acknowledged: bool) -> VerifiedCheckout:
        assert acknowledged is True
        return VerifiedCheckout(
            root=checkout,
            commit=UPSTREAM_SHA,
            repository="https://github.com/NanmiCoder/MediaCrawler.git",
            license_name="NON-COMMERCIAL LEARNING LICENSE 1.1",
            lock_path=lock_path,
        )

    def verify_python(path: Path) -> VerifiedPython:
        assert path == Path(sys.executable).resolve()
        return VerifiedPython(path)

    runner = MediaCrawlerDetailProcessRunner(
        lock_path=lock_path,
        integration_root=integration_root,
        python_executable=Path(sys.executable),
        license_acknowledged=True,
        checkout_verifier=verify_checkout,
        python_verifier=verify_python,
    )
    remote_id = f"{CONTENT_ID}:video:0"
    locator = AdapterRefreshLocator(
        adapter="mediacrawler",
        asset_key=stable_asset_key(
            platform="dy",
            content_remote_type="content",
            content_remote_id=CONTENT_ID,
            kind="video",
            position=0,
            remote_id=remote_id,
        ),
    )
    source_hint = asset_source_hint(SIGNED_URL)
    assert source_hint is not None
    context = MediaCrawlerRefreshContext(
        asset_id=ASSET_ID,
        account_id=ACCOUNT_ID,
        subscription_id=SUBSCRIPTION_ID,
        platform=Platform.DY,
        login_method=LoginMethod.COOKIE,
        content_remote_type="content",
        content_remote_id=CONTENT_ID,
        author_remote_id="creator-42",
        author_display_name="Fixture creator",
        asset_remote_id=remote_id,
        asset_kind=AssetKind.VIDEO,
        asset_position=0,
        source_hint=source_hint,
        locator=locator,
        cookie=SecretValue(COOKIE_SENTINEL),
        watchdogs=WatchdogLimits(
            max_seconds=10,
            max_output_bytes=64 * 1024,
            max_output_items=5,
            max_output_files=2,
            max_line_bytes=16 * 1024,
            poll_seconds=0.01,
        ),
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner).resolve(locator)

    assert resolved.url == SIGNED_URL
    jobs_root = integration_root / "jobs"
    assert jobs_root.is_dir()
    assert list(jobs_root.iterdir()) == []
    retained = b"".join(path.read_bytes() for path in integration_root.rglob("*") if path.is_file())
    assert COOKIE_SENTINEL.encode() not in retained
    profile = integration_root / "accounts" / "dy" / str(ACCOUNT_ID) / "browser_data" / "dy_user_data_dir"
    assert profile.parent.is_dir()


def test_bilibili_numeric_aid_uses_pinned_client_detail_entry(tmp_path: Path) -> None:
    checkout = _fake_bili_checkout(tmp_path)
    lock_path = tmp_path / "upstreams.lock.json"
    lock_path.write_text("{}", encoding="utf-8")

    runner = MediaCrawlerDetailProcessRunner(
        lock_path=lock_path,
        integration_root=tmp_path / "runtime",
        python_executable=Path(sys.executable),
        license_acknowledged=True,
        checkout_verifier=lambda _path, _accepted: VerifiedCheckout(
            root=checkout,
            commit=UPSTREAM_SHA,
            repository="https://github.com/NanmiCoder/MediaCrawler.git",
            license_name="NON-COMMERCIAL LEARNING LICENSE 1.1",
            lock_path=lock_path,
        ),
        python_verifier=lambda path: VerifiedPython(path),
    )
    remote_id = "987654321:cover:0"
    locator = AdapterRefreshLocator(
        adapter="mediacrawler",
        asset_key=stable_asset_key(
            platform="bili",
            content_remote_type="content",
            content_remote_id="987654321",
            kind="cover",
            position=0,
            remote_id=remote_id,
        ),
    )
    source_hint = asset_source_hint(BILI_COVER)
    assert source_hint is not None
    context = MediaCrawlerRefreshContext(
        asset_id=ASSET_ID,
        account_id=ACCOUNT_ID,
        subscription_id=SUBSCRIPTION_ID,
        platform=Platform.BILI,
        login_method=LoginMethod.QR,
        content_remote_type="content",
        content_remote_id="987654321",
        author_remote_id="creator-42",
        author_display_name="Fixture creator",
        asset_remote_id=remote_id,
        asset_kind=AssetKind.COVER,
        asset_position=0,
        source_hint=source_hint,
        locator=locator,
        watchdogs=WatchdogLimits(max_seconds=10, poll_seconds=0.01),
    )

    resolved = MediaCrawlerLocatorRefresher(context, runner).resolve(locator)

    assert resolved.url == BILI_COVER
    assert list((tmp_path / "runtime" / "jobs").iterdir()) == []


def test_bilibili_first_page_single_durl_is_injected_only_in_memory(tmp_path: Path) -> None:
    view = {
        "aid": 987654321,
        "cid": 99999,
        "pages": [{"cid": 24680}, {"cid": 97531}],
        "title": "fixture",
        "desc": "fixture",
        "pic": BILI_COVER,
        "owner": {"mid": 42, "name": "fixture"},
        "stat": {},
    }
    checkout = _fake_bili_checkout(tmp_path, view=view)
    context = _bili_video_context()

    resolved = MediaCrawlerLocatorRefresher(context, _bili_process_runner(tmp_path, checkout)).resolve(context.locator)

    assert resolved.url == BILI_VIDEO_URL
    assert resolved.request_profile is MediaRequestProfile.BILIBILI_MEDIA
    assert "ephemeral-sentinel" not in repr(resolved)
    jobs_root = tmp_path / "runtime" / "jobs"
    assert jobs_root.is_dir()
    assert list(jobs_root.iterdir()) == []
    retained = b"".join(path.read_bytes() for path in (tmp_path / "runtime").rglob("*") if path.is_file())
    assert BILI_VIDEO_URL.encode("utf-8") not in retained
    assert b"__media_sync_bili_progressive_url" not in retained


def test_bilibili_empty_pages_falls_back_to_validated_view_cid(tmp_path: Path) -> None:
    view = {
        "aid": 987654321,
        "cid": 13579,
        "pages": [],
        "title": "fixture",
        "desc": "fixture",
        "pic": BILI_COVER,
        "owner": {"mid": 42, "name": "fixture"},
        "stat": {},
    }
    checkout = _fake_bili_checkout(tmp_path, view=view, expected_cid=13579)
    context = _bili_video_context()

    resolved = MediaCrawlerLocatorRefresher(context, _bili_process_runner(tmp_path, checkout)).resolve(context.locator)

    assert resolved.url == BILI_VIDEO_URL


def test_bilibili_private_jsonl_bridge_is_bounded_collision_safe_and_repr_safe() -> None:
    ordinary = json.dumps({"video_id": "987654321", "title": "fixture"}, separators=(",", ":")).encode() + b"\n"
    progressive = detail_runner_module._BiliProgressiveResult(987654321, 24680, BILI_VIDEO_URL)
    limits = WatchdogLimits(
        max_output_bytes=8 * 1024,
        max_output_items=2,
        max_line_bytes=4 * 1024,
    )

    enriched = detail_runner_module._augment_bili_progressive_jsonl(ordinary, progressive, limits)

    assert BILI_VIDEO_URL.encode() in enriched
    assert BILI_VIDEO_URL.encode() not in ordinary
    assert "ephemeral-sentinel" not in repr(progressive)

    collision = (
        json.dumps(
            {
                "video_id": "987654321",
                "nested": {"__media_sync_bili_progressive_url": "https://attacker.invalid/value"},
            },
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )
    duplicate = ordinary + ordinary
    with pytest.raises(ValueError, match="collision"):
        detail_runner_module._augment_bili_progressive_jsonl(collision, progressive, limits)
    with pytest.raises(ValueError, match="mismatch"):
        detail_runner_module._augment_bili_progressive_jsonl(duplicate, progressive, limits)
    with pytest.raises(ValueError, match="output limit"):
        detail_runner_module._augment_bili_progressive_jsonl(
            ordinary,
            progressive,
            WatchdogLimits(max_output_bytes=len(ordinary), max_line_bytes=4 * 1024),
        )
    with pytest.raises(ValueError, match="line limit"):
        detail_runner_module._augment_bili_progressive_jsonl(
            ordinary,
            progressive,
            WatchdogLimits(max_output_bytes=8 * 1024, max_line_bytes=len(ordinary)),
        )


@pytest.mark.parametrize(
    ("case", "play_response", "play_raises", "expected"),
    [
        ("none", None, False, "locator_refresh_temporary"),
        ("exception", {"durl": [{"url": BILI_VIDEO_URL}]}, True, "locator_refresh_temporary"),
        ("dash-only", {"dash": {"video": [], "audio": []}}, False, "locator_refresh_unsupported"),
        ("empty", {"durl": []}, False, "locator_refresh_unsupported"),
        (
            "multi-segment",
            {"durl": [{"url": BILI_VIDEO_URL}, {"url": "https://video.example.test/bili/second.mp4"}]},
            False,
            "locator_refresh_unsupported",
        ),
        ("durl-type", {"durl": {"url": BILI_VIDEO_URL}}, False, "locator_refresh_result_invalid"),
        ("item-type", {"durl": ["not-an-object"]}, False, "locator_refresh_result_invalid"),
        ("url-type", {"durl": [{"url": 42}]}, False, "locator_refresh_result_invalid"),
        ("url-invalid", {"durl": [{"url": "file:///private/video.mp4"}]}, False, "locator_refresh_result_invalid"),
    ],
)
def test_bilibili_play_response_shapes_have_fixed_outcomes(
    tmp_path: Path,
    case: str,
    play_response: object,
    play_raises: bool,
    expected: str,
) -> None:
    del case
    checkout = _fake_bili_checkout(
        tmp_path,
        play_response=play_response,
        play_raises=play_raises,
    )
    context = _bili_video_context()

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, _bili_process_runner(tmp_path, checkout)).resolve(context.locator)

    assert caught.value.code == expected
    assert "ephemeral-sentinel" not in str(caught.value)
    assert list((tmp_path / "runtime" / "jobs").iterdir()) == []


def test_bilibili_missing_detail_is_retryable_for_the_progressive_video_slot(tmp_path: Path) -> None:
    checkout = _fake_bili_checkout(tmp_path, view=None)
    context = _bili_video_context()

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, _bili_process_runner(tmp_path, checkout)).resolve(context.locator)

    assert caught.value.code == "locator_refresh_temporary"
    assert list((tmp_path / "runtime" / "jobs").iterdir()) == []


@pytest.mark.parametrize(
    "view",
    [
        {
            "aid": 123,
            "cid": 24680,
            "title": "fixture",
            "desc": "fixture",
            "pic": BILI_COVER,
            "owner": {"mid": 42, "name": "fixture"},
            "stat": {},
        },
        {
            "aid": 987654321,
            "title": "fixture",
            "desc": "fixture",
            "pic": BILI_COVER,
            "owner": {"mid": 42, "name": "fixture"},
            "stat": {},
        },
        {
            "aid": 987654321,
            "cid": 24680,
            "pages": "malformed",
            "title": "fixture",
            "desc": "fixture",
            "pic": BILI_COVER,
            "owner": {"mid": 42, "name": "fixture"},
            "stat": {},
        },
    ],
)
def test_bilibili_aid_and_cid_drift_fail_as_invalid_results(tmp_path: Path, view: dict[str, object]) -> None:
    checkout = _fake_bili_checkout(tmp_path, view=view)
    context = _bili_video_context()

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, _bili_process_runner(tmp_path, checkout)).resolve(context.locator)

    assert caught.value.code == "locator_refresh_result_invalid"
    assert list((tmp_path / "runtime" / "jobs").iterdir()) == []
