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
from media_sync.integrations.mediacrawler.detail_runner import (
    MediaCrawlerDetailProcessRunner,
    MediaCrawlerDetailRequest,
    MediaCrawlerDetailResult,
)
from media_sync.integrations.mediacrawler.policies import WatchdogLimits
from media_sync.integrations.mediacrawler.refresh import (
    MediaCrawlerLocatorRefresher,
    MediaCrawlerRefreshContext,
)
from media_sync.integrations.mediacrawler.weibo_media import WEIBO_IMAGES_FIELD
from media_sync.media import AdapterRefreshLocator, MediaDownloadError, MediaRequestProfile
from media_sync.security import SecretValue

UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
ACCOUNT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SUBSCRIPTION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
ASSET_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
COOKIE_SENTINEL = "DETAIL-COOKIE-SENTINEL-91d4b7"
CONTENT_ID = "7525082444551310602"
DY_VIDEO_URL = f"https://video.example.test/douyin/main.mp4?sign={COOKIE_SENTINEL}"
DY_COVER_SENTINEL = "DETAIL-COVER-SENTINEL-a8f2c1"
DY_COVER_URL = f"https://image.example.test/douyin/cover.jpg?sign={DY_COVER_SENTINEL}"
BILI_COVER = "https://image.example.test/bili/cover.jpg?token=bili-detail-sentinel"
BILI_VIDEO_URL = "https://video.example.test/bili/first.mp4?" + "deadline=4102444800&sig=ephemeral-sentinel"
KS_VIDEO_ID = "3x3zxz4mjrsc8ke"
KS_VIDEO_URL = "https://video.example.test/ks/main.mp4?auth=ks-video-sentinel"
KS_COVER_URL = "https://image.example.test/ks/cover.jpg?auth=ks-cover-sentinel"
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
        assert config.ENABLE_GET_SUB_COMMENTS is False
        assert config.ENABLE_GET_MEIDAS is False
        assert config.ENABLE_GET_MEDIAS is False
        assert config.SAVE_LOGIN_STATE is True
        assert config.CRAWLER_MAX_SLEEP_SEC == 0.25
        profile = Path(
            os.path.join(os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM)
        ).resolve()
        assert profile.name == "dy_user_data_dir"
        assert profile.parent.name == "browser_data"
        profile.mkdir(parents=True, exist_ok=True)
        (profile / "session.marker").write_text("stable fixture profile", encoding="utf-8")
        print("upstream stdout must not contaminate the detail frame")
        os.write(2, b"upstream stderr must not contaminate the detail frame\n")
        target = Path(config.SAVE_DATA_PATH) / "douyin" / "jsonl" / "detail_contents_fixture.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "aweme_id": "7525082444551310602",
            "title": "fixture",
            "desc": "fixture",
            "video_download_url": "https://video.example.test/douyin/main.mp4?sign=" + config.COOKIES,
            "cover_url": __DY_COVER_URL__,
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

_KS_MAIN = r"""
import json
import os
from pathlib import Path

import config

crawler = None
RECORDS = __KS_RECORDS__


class FakeCrawler:
    async def start(self):
        assert config.PLATFORM == "ks"
        assert config.LOGIN_TYPE == "qrcode"
        assert config.CRAWLER_TYPE == "detail"
        assert config.KS_SPECIFIED_ID_LIST == ["3x3zxz4mjrsc8ke"]
        assert config.SAVE_DATA_OPTION == "jsonl"
        assert config.ENABLE_GET_COMMENTS is False
        assert config.ENABLE_GET_MEIDAS is False
        assert config.ENABLE_GET_MEDIAS is False
        assert config.MAX_CONCURRENCY_NUM == 1
        assert config.SAVE_LOGIN_STATE is True
        profile = Path(
            os.path.join(os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM)
        ).resolve()
        assert profile.name == "ks_user_data_dir"
        assert profile.parent.name == "browser_data"
        profile.mkdir(parents=True, exist_ok=True)
        (profile / "session.marker").write_text("stable fixture profile", encoding="utf-8")
        target = Path(config.SAVE_DATA_PATH) / "kuaishou" / "jsonl" / "detail_contents_fixture.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(
            json.dumps(record, separators=(",", ":")) + "\n"
            for record in RECORDS
        )
        target.write_text(payload, encoding="utf-8")


class CrawlerFactory:
    @staticmethod
    def create_crawler(platform):
        assert platform == "ks"
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

_WB_STORE = r"""
import asyncio
import json
from pathlib import Path

import config


class WeiboJsonlStoreImplement:
    async def store_content(self, content_item):
        target = Path(config.SAVE_DATA_PATH) / "wb" / "jsonl" / "detail_contents_fixture.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(content_item, separators=(",", ":")) + "\n")


async def update_weibo_note(note_item):
    mblog = note_item["mblog"]
    await asyncio.sleep(0)
    await WeiboJsonlStoreImplement().store_content(
        {
            "note_id": mblog["id"],
            "content": mblog["text"],
            "note_url": "https://m.weibo.cn/detail/" + mblog["id"],
        }
    )
"""

_WB_MAIN = r"""
import json
import os
from pathlib import Path

import config
from store import weibo as weibo_store

crawler = None


def _profile():
    return Path(
        os.path.join(os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM)
    ).resolve()


class FakeCrawler:
    async def start(self):
        assert config.PLATFORM == "wb"
        assert config.LOGIN_TYPE == "qrcode"
        assert config.CRAWLER_TYPE == "detail"
        assert config.WEIBO_SPECIFIED_ID_LIST == ["7525082444551310602"]
        assert config.SAVE_DATA_OPTION == "jsonl"
        assert config.CREATOR_MODE is False
        assert config.ENABLE_GET_COMMENTS is False
        assert config.ENABLE_GET_MEIDAS is False
        assert config.ENABLE_GET_MEDIAS is False
        assert config.MAX_CONCURRENCY_NUM == 1
        profile = _profile()
        assert profile.name == "wb_user_data_dir"
        profile.mkdir(parents=True, exist_ok=True)
        await weibo_store.update_weibo_note(
            {
                "mblog": {
                    "id": "7525082444551310602",
                    "text": "fixture image note",
                    "pics": [
                        {"pid": "firstPid", "url": "https://wx1.sinaimg.cn/orj360/first.jpg"},
                        {"pid": "secondPid", "url": "https://wx2.sinaimg.cn/mw690/second.png"},
                    ],
                }
            }
        )


class CrawlerFactory:
    @staticmethod
    def create_crawler(platform):
        assert platform == "wb"
        return FakeCrawler()


async def main():
    global crawler
    crawler = CrawlerFactory.create_crawler(config.PLATFORM)
    await crawler.start()


async def async_cleanup():
    assert config.COOKIES == ""
    (_profile() / "cleanup.json").write_text(
        json.dumps({"called": True, "cookie_cleared": True}),
        encoding="utf-8",
    )
"""


def _fake_checkout(root: Path) -> Path:
    checkout = root / "fake-mediacrawler"
    (checkout / "config").mkdir(parents=True)
    (checkout / "config" / "__init__.py").write_text(textwrap.dedent(_CONFIG).lstrip(), encoding="utf-8")
    main_source = textwrap.dedent(_MAIN).lstrip().replace("__DY_COVER_URL__", repr(DY_COVER_URL))
    (checkout / "main.py").write_text(main_source, encoding="utf-8")
    return checkout.resolve()


def _dy_context(kind: AssetKind, signed_url: str) -> MediaCrawlerRefreshContext:
    remote_id = f"{CONTENT_ID}:{kind.value}:0"
    locator = AdapterRefreshLocator(
        adapter="mediacrawler",
        asset_key=stable_asset_key(
            platform="dy",
            content_remote_type="content",
            content_remote_id=CONTENT_ID,
            kind=kind.value,
            position=0,
            remote_id=remote_id,
        ),
    )
    source_hint = asset_source_hint(signed_url)
    assert source_hint is not None
    return MediaCrawlerRefreshContext(
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
        asset_kind=kind,
        asset_position=0,
        source_hint=source_hint,
        locator=locator,
        cookie=SecretValue(COOKIE_SENTINEL),
        request_delay_seconds=0.25,
        watchdogs=WatchdogLimits(
            max_seconds=10,
            max_output_bytes=64 * 1024,
            max_output_items=5,
            max_output_files=2,
            max_line_bytes=16 * 1024,
            poll_seconds=0.01,
        ),
    )


def _ks_record(*, video_id: str = KS_VIDEO_ID) -> dict[str, str]:
    return {
        "video_id": video_id,
        "video_type": "video",
        "title": "fixture",
        "desc": "fixture",
        "video_url": f"https://www.kuaishou.com/short-video/{video_id}",
        "video_cover_url": KS_COVER_URL,
        "video_play_url": KS_VIDEO_URL,
    }


def _fake_ks_checkout(root: Path, *, records: list[dict[str, str]] | None = None) -> Path:
    checkout = root / "fake-mediacrawler-ks"
    (checkout / "config").mkdir(parents=True)
    (checkout / "config" / "__init__.py").write_text(textwrap.dedent(_CONFIG).lstrip(), encoding="utf-8")
    active_records = [_ks_record()] if records is None else records
    main_source = textwrap.dedent(_KS_MAIN).lstrip().replace("__KS_RECORDS__", repr(active_records))
    (checkout / "main.py").write_text(main_source, encoding="utf-8")
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


def _fake_wb_checkout(
    root: Path,
    *,
    first_url: str = "https://wx1.sinaimg.cn/orj360/first.jpg",
) -> Path:
    checkout = root / "fake-mediacrawler-wb"
    (checkout / "config").mkdir(parents=True)
    (checkout / "store" / "weibo").mkdir(parents=True)
    (checkout / "config" / "__init__.py").write_text(textwrap.dedent(_CONFIG).lstrip(), encoding="utf-8")
    (checkout / "store" / "weibo" / "__init__.py").write_text(
        textwrap.dedent(_WB_STORE).lstrip(),
        encoding="utf-8",
    )
    main_source = (
        textwrap.dedent(_WB_MAIN)
        .lstrip()
        .replace(
            "https://wx1.sinaimg.cn/orj360/first.jpg",
            first_url,
        )
    )
    (checkout / "main.py").write_text(main_source, encoding="utf-8")
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


def _wb_process_runner(tmp_path: Path, checkout: Path) -> MediaCrawlerDetailProcessRunner:
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


def _ks_process_runner(tmp_path: Path, checkout: Path) -> MediaCrawlerDetailProcessRunner:
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


def _ks_context(kind: AssetKind, signed_url: str) -> MediaCrawlerRefreshContext:
    remote_id = f"{KS_VIDEO_ID}:{kind.value}:0"
    locator = AdapterRefreshLocator(
        adapter="mediacrawler",
        asset_key=stable_asset_key(
            platform="ks",
            content_remote_type="content",
            content_remote_id=KS_VIDEO_ID,
            kind=kind.value,
            position=0,
            remote_id=remote_id,
        ),
    )
    source_hint = asset_source_hint(signed_url)
    assert source_hint is not None
    return MediaCrawlerRefreshContext(
        asset_id=ASSET_ID,
        account_id=ACCOUNT_ID,
        subscription_id=SUBSCRIPTION_ID,
        platform=Platform.KS,
        login_method=LoginMethod.QR,
        content_remote_type="content",
        content_remote_id=KS_VIDEO_ID,
        author_remote_id="creator-42",
        author_display_name="Fixture creator",
        asset_remote_id=remote_id,
        asset_kind=kind,
        asset_position=0,
        source_hint=source_hint,
        locator=locator,
        watchdogs=WatchdogLimits(
            max_seconds=10,
            max_output_bytes=64 * 1024,
            max_output_items=5,
            max_output_files=2,
            max_line_bytes=16 * 1024,
            poll_seconds=0.01,
        ),
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
    requests: list[MediaCrawlerDetailRequest] = []
    results: list[MediaCrawlerDetailResult] = []

    class RecordingRunner:
        def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
            requests.append(request)
            result = runner.run(request)
            results.append(result)
            return result

    video_context = _dy_context(AssetKind.VIDEO, DY_VIDEO_URL)
    cover_context = _dy_context(AssetKind.COVER, DY_COVER_URL)
    recording_runner = RecordingRunner()

    video = MediaCrawlerLocatorRefresher(video_context, recording_runner).resolve(video_context.locator)
    cover = MediaCrawlerLocatorRefresher(cover_context, recording_runner).resolve(cover_context.locator)

    assert video.url == DY_VIDEO_URL
    assert cover.url == DY_COVER_URL
    assert video.request_profile is MediaRequestProfile.DEFAULT
    assert cover.request_profile is MediaRequestProfile.DEFAULT
    assert len(requests) == len(results) == 2
    for value in (video_context, cover_context, *requests, *results, video, cover):
        assert COOKIE_SENTINEL not in repr(value)
        assert DY_COVER_SENTINEL not in repr(value)
    jobs_root = integration_root / "jobs"
    assert jobs_root.is_dir()
    assert list(jobs_root.iterdir()) == []
    retained = b"".join(path.read_bytes() for path in integration_root.rglob("*") if path.is_file())
    assert COOKIE_SENTINEL.encode() not in retained
    assert DY_COVER_SENTINEL.encode() not in retained
    profile = integration_root / "accounts" / "dy" / str(ACCOUNT_ID) / "browser_data" / "dy_user_data_dir"
    assert profile.is_dir()
    assert (profile / "session.marker").read_text(encoding="utf-8") == "stable fixture profile"


def test_weibo_numeric_detail_installs_media_shim_and_runs_cleanup(tmp_path: Path) -> None:
    checkout = _fake_wb_checkout(tmp_path)
    lock_path = tmp_path / "upstreams.lock.json"
    lock_path.write_text("{}", encoding="utf-8")
    integration_root = tmp_path / "runtime"
    runner = MediaCrawlerDetailProcessRunner(
        lock_path=lock_path,
        integration_root=integration_root,
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

    result = runner.run(
        MediaCrawlerDetailRequest(
            account_id=ACCOUNT_ID,
            subscription_id=SUBSCRIPTION_ID,
            platform=Platform.WB,
            login_method=LoginMethod.QR,
            content_remote_id=CONTENT_ID,
            request_delay_seconds=0.25,
            watchdogs=WatchdogLimits(max_seconds=10, poll_seconds=0.01),
        )
    )

    assert result.upstream_sha == UPSTREAM_SHA
    records = [json.loads(line) for line in result.jsonl.splitlines()]
    assert records == [
        {
            "note_id": CONTENT_ID,
            "content": "fixture image note",
            "note_url": f"https://m.weibo.cn/detail/{CONTENT_ID}",
            WEIBO_IMAGES_FIELD: [
                {"pid": "firstPid", "url": "https://i1.wp.com/wx1.sinaimg.cn/large/first.jpg"},
                {"pid": "secondPid", "url": "https://i1.wp.com/wx2.sinaimg.cn/large/second.png"},
            ],
        }
    ]
    assert list((integration_root / "jobs").iterdir()) == []
    profile = integration_root / "accounts" / "wb" / str(ACCOUNT_ID) / "browser_data" / "wb_user_data_dir"
    assert json.loads((profile / "cleanup.json").read_text(encoding="utf-8")) == {
        "called": True,
        "cookie_cleared": True,
    }
    retained = b"".join(path.read_bytes() for path in integration_root.rglob("*") if path.is_file())
    assert WEIBO_IMAGES_FIELD.encode("utf-8") not in retained


@pytest.mark.parametrize(
    "first_url",
    [
        pytest.param("https://wx1.sinaimg.cn/orj360/animated.gif", id="gif"),
        pytest.param("https://evil.example/orj360/foreign.jpg", id="foreign-host"),
    ],
)
def test_weibo_detail_capture_rejects_nonstatic_or_foreign_source(
    tmp_path: Path,
    first_url: str,
) -> None:
    checkout = _fake_wb_checkout(tmp_path, first_url=first_url)
    result = _wb_process_runner(tmp_path, checkout).run(
        MediaCrawlerDetailRequest(
            account_id=ACCOUNT_ID,
            subscription_id=SUBSCRIPTION_ID,
            platform=Platform.WB,
            login_method=LoginMethod.QR,
            content_remote_id=CONTENT_ID,
            watchdogs=WatchdogLimits(max_seconds=10, poll_seconds=0.01),
        )
    )

    records = [json.loads(line) for line in result.jsonl.splitlines()]
    assert len(records) == 1
    assert records[0]["note_id"] == CONTENT_ID
    assert WEIBO_IMAGES_FIELD not in records[0]
    assert list((tmp_path / "runtime" / "jobs").iterdir()) == []


@pytest.mark.parametrize(
    ("content_remote_id", "detail_reference"),
    [
        ("not-numeric", None),
        ("07525082444551310602", None),
        (CONTENT_ID, "https://m.weibo.cn/detail/7525082444551310602"),
        (CONTENT_ID, "7525082444551310603"),
        (CONTENT_ID, SecretValue(CONTENT_ID)),
    ],
)
def test_weibo_detail_rejects_noncanonical_or_nonmatching_references(
    content_remote_id: str,
    detail_reference: str | SecretValue | None,
) -> None:
    with pytest.raises(MediaDownloadError, match="locator_refresh_configuration_invalid"):
        MediaCrawlerDetailRequest(
            account_id=ACCOUNT_ID,
            subscription_id=SUBSCRIPTION_ID,
            platform=Platform.WB,
            login_method=LoginMethod.QR,
            content_remote_id=content_remote_id,
            detail_reference=detail_reference,
        )


@pytest.mark.parametrize("detail_reference", [None, CONTENT_ID])
def test_weibo_detail_accepts_implicit_or_exact_plain_reference(detail_reference: str | None) -> None:
    request = MediaCrawlerDetailRequest(
        account_id=ACCOUNT_ID,
        subscription_id=SUBSCRIPTION_ID,
        platform=Platform.WB,
        login_method=LoginMethod.QR,
        content_remote_id=CONTENT_ID,
        detail_reference=detail_reference,
    )

    assert request.resolved_detail_reference() == CONTENT_ID


def test_weibo_detail_child_rejects_mismatched_numeric_reference(tmp_path: Path) -> None:
    account_root = tmp_path / "accounts" / "wb" / str(ACCOUNT_ID)
    profile_root = account_root / "browser_data" / "wb_user_data_dir"
    job_root = tmp_path / "jobs" / "attempt"
    output_root = job_root / "output"
    limits = WatchdogLimits()
    payload = json.dumps(
        {
            "schema_version": detail_runner_module.DETAIL_RUNNER_SCHEMA_VERSION,
            "checkout_root": str(Path.cwd().resolve()),
            "account_root": str(account_root),
            "profile_root": str(profile_root),
            "job_root": str(job_root),
            "output_root": str(output_root),
            "platform": Platform.WB.value,
            "login_method": LoginMethod.QR.value,
            "content_remote_id": CONTENT_ID,
            "detail_reference": "7525082444551310603",
            "cookie": None,
            "headless": True,
            "request_delay_seconds": 0.25,
            "bili_progressive_detail": False,
            "watchdogs": {
                "max_seconds": limits.max_seconds,
                "max_output_bytes": limits.max_output_bytes,
                "max_output_items": limits.max_output_items,
                "max_output_files": limits.max_output_files,
                "max_line_bytes": limits.max_line_bytes,
                "poll_seconds": limits.poll_seconds,
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")

    with pytest.raises(detail_runner_module._ChildConfigurationError):
        detail_runner_module._ChildRequest.load(payload)


def test_kuaishou_detail_refresh_resolves_video_and_cover_without_retaining_signed_urls(tmp_path: Path) -> None:
    checkout = _fake_ks_checkout(tmp_path)
    runner = _ks_process_runner(tmp_path, checkout)
    video_context = _ks_context(AssetKind.VIDEO, KS_VIDEO_URL)
    cover_context = _ks_context(AssetKind.COVER, KS_COVER_URL)

    video = MediaCrawlerLocatorRefresher(video_context, runner).resolve(video_context.locator)
    cover = MediaCrawlerLocatorRefresher(cover_context, runner).resolve(cover_context.locator)

    assert video.url == KS_VIDEO_URL
    assert cover.url == KS_COVER_URL
    assert video.request_profile is MediaRequestProfile.DEFAULT
    assert cover.request_profile is MediaRequestProfile.DEFAULT
    for value in (repr(video_context), repr(cover_context), repr(video), repr(cover)):
        assert "ks-video-sentinel" not in value
        assert "ks-cover-sentinel" not in value
    jobs_root = tmp_path / "runtime" / "jobs"
    assert jobs_root.is_dir()
    assert list(jobs_root.iterdir()) == []
    retained = b"".join(path.read_bytes() for path in (tmp_path / "runtime").rglob("*") if path.is_file())
    assert KS_VIDEO_URL.encode("utf-8") not in retained
    assert KS_COVER_URL.encode("utf-8") not in retained
    profile = tmp_path / "runtime" / "accounts" / "ks" / str(ACCOUNT_ID) / "browser_data" / "ks_user_data_dir"
    assert profile.is_dir()
    assert (profile / "session.marker").read_text(encoding="utf-8") == "stable fixture profile"


@pytest.mark.parametrize(
    ("case", "records", "expected"),
    [
        ("missing", [], "locator_refresh_asset_not_found"),
        ("content-id-drift", [_ks_record(video_id="different-video-id")], "locator_refresh_asset_not_found"),
        ("duplicate", [_ks_record(), _ks_record()], "locator_refresh_asset_mismatch"),
    ],
)
def test_kuaishou_detail_refresh_rejects_missing_drifted_and_duplicate_records(
    tmp_path: Path,
    case: str,
    records: list[dict[str, str]],
    expected: str,
) -> None:
    del case
    checkout = _fake_ks_checkout(tmp_path, records=records)
    context = _ks_context(AssetKind.VIDEO, KS_VIDEO_URL)

    with pytest.raises(MediaDownloadError) as caught:
        MediaCrawlerLocatorRefresher(context, _ks_process_runner(tmp_path, checkout)).resolve(context.locator)

    assert caught.value.code == expected
    error = str(caught.value)
    assert "ks-video-sentinel" not in error
    assert "ks-cover-sentinel" not in error
    jobs_root = tmp_path / "runtime" / "jobs"
    assert jobs_root.is_dir()
    assert list(jobs_root.iterdir()) == []
    retained = b"".join(path.read_bytes() for path in (tmp_path / "runtime").rglob("*") if path.is_file())
    assert KS_VIDEO_URL.encode("utf-8") not in retained
    assert KS_COVER_URL.encode("utf-8") not in retained


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
