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
from media_sync.integrations.mediacrawler.tieba_media import TIEBA_GALLERY_FIELD, TIEBA_IMAGE_FIELD, TIEBA_IMAGES_FIELD
from media_sync.integrations.mediacrawler.weibo_media import WEIBO_IMAGES_FIELD
from media_sync.integrations.mediacrawler.zhihu_media import ZHIHU_IMAGE_FIELD
from media_sync.media import (
    AdapterRefreshLocator,
    MediaDownloadError,
    MediaRequestProfile,
    ResolvedDashLocator,
    ResolvedLocator,
)
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
BILI_DASH_AVC_URL = "https://video.example.test/bili/avc.m4s?deadline=4102444800&sig=dash-avc-sentinel"
BILI_DASH_AVC_BACKUP = "https://backup.example.test/bili/avc.m4s?deadline=4102444800&sig=dash-backup-sentinel"
BILI_DASH_AUDIO_URL = "https://audio.example.test/bili/hires.m4s?deadline=4102444800&sig=dash-audio-sentinel"
KS_VIDEO_ID = "3x3zxz4mjrsc8ke"
KS_VIDEO_URL = "https://video.example.test/ks/main.mp4?auth=ks-video-sentinel"
KS_COVER_URL = "https://image.example.test/ks/cover.jpg?auth=ks-cover-sentinel"
XHS_NOTE_ID = "66fad51c000000001b0224b8"
XHS_AUTHOR_ID = "5f0123450000000001000001"
XHS_CREATOR_URL = (
    f"https://www.xiaohongshu.com/user/profile/{XHS_AUTHOR_ID}?"
    "xsec_token=xhs-creator-authority-sentinel&xsec_source=pc_user"
)
XHS_DETAIL_URL = (
    f"https://www.xiaohongshu.com/explore/{XHS_NOTE_ID}?xsec_token=xhs-detail-authority-sentinel&xsec_source=pc_feed"
)
XHS_IMAGE_URL = "https://image.example.test/xhs/target.jpg?sign=xhs-image-sentinel"
XHS_VIDEO_URL = "http://sns-video-bd.xhscdn.com/video-key.mp4?sign=xhs-video-sentinel"
XHS_COVER_URL = "https://sns-webpic-qc.xhscdn.com/cover.png?sign=xhs-cover-sentinel"
ZHIHU_ANSWER_ID = "987654321"
ZHIHU_QUESTION_ID = "246810"
ZHIHU_ANSWER_URL = f"https://www.zhihu.com/question/{ZHIHU_QUESTION_ID}/answer/{ZHIHU_ANSWER_ID}"
ZHIHU_IMAGE_URL = "https://picx.zhimg.com/v2-detail-fixture.jpg?source=zhihu-detail-sentinel"
TIEBA_NOTE_ID = "10376710029"
TIEBA_THREAD_URL = f"https://tieba.baidu.com/p/{TIEBA_NOTE_ID}"
TIEBA_IMAGE_ID = "489c9a3df8dcd1009420153b348b4710b8122fc3"
TIEBA_TOKEN = "tieba-detail-sentinel-2026-09-02"
TIEBA_IMAGE_URL = f"https://tiebapic.baidu.com/forum/pic/item/{TIEBA_IMAGE_ID}.jpg?tbpicau={TIEBA_TOKEN}"
TIEBA_IMAGE_HINT = f"https://tiebapic.baidu.com/forum/pic/item/{TIEBA_IMAGE_ID}.jpg"
TIEBA_SECOND_IMAGE_ID = "0123456789abcdef0123456789abcdef01234567"
TIEBA_SECOND_TOKEN = "tieba-detail-sentinel-second-2026-09-02"
TIEBA_SECOND_IMAGE_URL = (
    f"https://tiebapic.baidu.com/forum/pic/item/{TIEBA_SECOND_IMAGE_ID}.jpg?tbpicau={TIEBA_SECOND_TOKEN}"
)
TIEBA_SECOND_IMAGE_HINT = f"https://tiebapic.baidu.com/forum/pic/item/{TIEBA_SECOND_IMAGE_ID}.jpg"
TIEBA_THIRD_IMAGE_ID = "abcdef0123456789abcdef0123456789abcdef01"
TIEBA_THIRD_TOKEN = "tieba-detail-sentinel-third-2026-09-02"
TIEBA_THIRD_IMAGE_URL = (
    f"https://tiebapic.baidu.com/forum/pic/item/{TIEBA_THIRD_IMAGE_ID}.jpg?tbpicau={TIEBA_THIRD_TOKEN}"
)
TIEBA_THIRD_IMAGE_HINT = f"https://tiebapic.baidu.com/forum/pic/item/{TIEBA_THIRD_IMAGE_ID}.jpg"
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

_XHS_MAIN = r"""
import json
import os
from pathlib import Path

import config

crawler = None
CREATOR_MODE = __CREATOR_MODE__
CREATOR_URL = __CREATOR_URL__
DETAIL_URL = __DETAIL_URL__
RECORDS = __RECORDS__


class FakeCrawler:
    async def start(self):
        assert config.PLATFORM == "xhs"
        assert config.LOGIN_TYPE == "qrcode"
        assert config.SAVE_DATA_OPTION == "jsonl"
        assert config.MAX_CONCURRENCY_NUM == 1
        assert config.ENABLE_GET_COMMENTS is False
        assert config.ENABLE_GET_SUB_COMMENTS is False
        assert config.ENABLE_GET_MEIDAS is False
        assert config.ENABLE_GET_MEDIAS is False
        assert config.SAVE_LOGIN_STATE is True
        creator_names = (
            "XHS_CREATOR_ID_LIST", "DY_CREATOR_ID_LIST", "KS_CREATOR_ID_LIST",
            "BILI_CREATOR_ID_LIST", "WEIBO_CREATOR_ID_LIST", "TIEBA_CREATOR_URL_LIST",
            "ZHIHU_CREATOR_URL_LIST",
        )
        detail_names = (
            "XHS_SPECIFIED_NOTE_URL_LIST", "DY_SPECIFIED_ID_LIST", "KS_SPECIFIED_ID_LIST",
            "BILI_SPECIFIED_ID_LIST", "WEIBO_SPECIFIED_ID_LIST", "TIEBA_SPECIFIED_ID_LIST",
            "ZHIHU_SPECIFIED_ID_LIST",
        )
        if CREATOR_MODE:
            assert config.CRAWLER_TYPE == "creator"
            assert config.CREATOR_MODE is True
            assert config.CRAWLER_MAX_NOTES_COUNT == 2
            assert config.XHS_CREATOR_ID_LIST == [CREATOR_URL]
            for name in creator_names[1:]:
                assert getattr(config, name) == []
            for name in detail_names:
                assert getattr(config, name) == []
        else:
            assert config.CRAWLER_TYPE == "detail"
            assert config.CREATOR_MODE is False
            assert config.CRAWLER_MAX_NOTES_COUNT == 1
            assert config.XHS_SPECIFIED_NOTE_URL_LIST == [DETAIL_URL]
            for name in creator_names:
                assert getattr(config, name) == []
            for name in detail_names[1:]:
                assert getattr(config, name) == []
        profile = Path(
            os.path.join(os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM)
        ).resolve()
        profile.mkdir(parents=True, exist_ok=True)
        (profile / "session.marker").write_text("stable fixture profile", encoding="utf-8")
        root = Path(config.SAVE_DATA_PATH) / "xhs" / "jsonl"
        root.mkdir(parents=True, exist_ok=True)
        for index, record in enumerate(RECORDS):
            target = root / ("creator_contents_" + str(index) + ".jsonl")
            target.write_text(json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8")


class CrawlerFactory:
    @staticmethod
    def create_crawler(platform):
        assert platform == "xhs"
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


class FakeBiliClient:
    async def get(self, uri, params, enable_params_sign):
        assert uri == "/x/player/wbi/playurl"
        assert params == {
            "avid": 987654321,
            "cid": EXPECTED_CID,
            "qn": 127,
            "fourk": 1,
            "fnval": 4048,
            "platform": "pc",
        }
        assert enable_params_sign is True
        for path in Path(config.SAVE_DATA_PATH).rglob("*.jsonl"):
            retained = path.read_bytes()
            assert b"__media_sync_bili_progressive_url" not in retained
            assert b"__media_sync_bili_dash_page_v1" not in retained
            if FORBIDDEN_URL:
                assert FORBIDDEN_URL.encode("utf-8") not in retained
        if PLAY_RAISES:
            raise RuntimeError("private play failure must be classified without echo")
        return PLAY_RESPONSE


class FakeCrawler:
    def __init__(self):
        self.bili_client = FakeBiliClient()

    async def get_video_info_task(self, aid, bvid, semaphore):
        assert aid == 987654321
        assert bvid == ""
        assert semaphore is not None
        if VIEW_RESPONSE is None:
            return None
        return {"View": VIEW_RESPONSE}

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

_ZHIHU_HELP = r"""
class ZhihuContent:
    def model_dump(self):
        return {
            "content_id": self.content_id,
            "content_type": self.content_type,
            "content_text": self.content_text,
            "question_id": self.question_id,
            "content_url": self.content_url,
            "title": self.title,
        }


class ZhihuExtractor:
    def _extract_answer_content(self, answer):
        result = ZhihuContent()
        result.content_id = str(answer.get("id") or "")
        result.content_type = answer.get("type")
        result.content_text = "fixture answer body"
        result.question_id = str(answer.get("question", {}).get("id") or "")
        result.content_url = "https://www.zhihu.com/question/" + result.question_id + "/answer/" + result.content_id
        result.title = "Fixture answer"
        return result
"""

_ZHIHU_CLIENT = r"""
class ZhiHuClient:
    async def get_all_anwser_by_creator(self, url_token, crawl_interval=1.0, callback=None):
        return []
"""

_ZHIHU_STORE_IMPL = r"""
import json
from pathlib import Path

import config


class ZhihuJsonlStoreImplement:
    async def store_content(self, content_item):
        target = Path(config.SAVE_DATA_PATH) / "zhihu" / "jsonl" / "detail_contents_fixture.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(content_item, separators=(",", ":")) + "\n", encoding="utf-8")
"""

_ZHIHU_STORE = r"""
from ._store_impl import ZhihuJsonlStoreImplement


async def update_zhihu_content(content_item):
    await ZhihuJsonlStoreImplement().store_content(content_item.model_dump())
"""

_ZHIHU_MAIN = r"""
import asyncio
import os
from pathlib import Path

import config
from media_platform.zhihu.help import ZhihuExtractor
from store import zhihu as zhihu_store

crawler = None


class FakeCrawler:
    async def start(self):
        assert config.PLATFORM == "zhihu"
        assert config.LOGIN_TYPE == "qrcode"
        assert config.CRAWLER_TYPE == "detail"
        assert config.CREATOR_MODE is False
        assert config.CRAWLER_MAX_NOTES_COUNT == 1
        assert config.ZHIHU_SPECIFIED_ID_LIST == [__ZHIHU_ANSWER_URL__]
        assert config.SAVE_DATA_OPTION == "jsonl"
        assert config.MAX_CONCURRENCY_NUM == 1
        assert config.ENABLE_GET_COMMENTS is False
        assert config.ENABLE_GET_MEIDAS is False
        assert config.ENABLE_GET_MEDIAS is False
        profile = Path(
            os.path.join(os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM)
        ).resolve()
        profile.mkdir(parents=True, exist_ok=True)
        (profile / "session.marker").write_text("stable fixture profile", encoding="utf-8")
        answer = {
            "id": int(__ZHIHU_ANSWER_ID__),
            "type": "answer",
            "question": {"id": int(__ZHIHU_QUESTION_ID__)},
            "content": '<p>body</p><img src="' + __ZHIHU_IMAGE_URL__ + '">',
        }
        async def extract_in_detail_task():
            await asyncio.sleep(0)
            return ZhihuExtractor()._extract_answer_content(answer)

        content = (await asyncio.gather(extract_in_detail_task()))[0]
        await zhihu_store.update_zhihu_content(content)


async def main():
    global crawler
    crawler = FakeCrawler()
    await crawler.start()


async def async_cleanup():
    return None
"""

_TIEBA_HELP = r"""
class TiebaNote:
    def model_dump(self):
        return {
            "note_id": self.note_id,
            "note_url": self.note_url,
            "title": self.title,
            "desc": self.desc,
        }


class TieBaExtractor:
    def extract_note_detail_from_api(self, api_data):
        thread = api_data["thread"]
        result = TiebaNote()
        result.note_id = str(thread["id"])
        result.note_url = "https://tieba.baidu.com/p/" + result.note_id
        result.title = thread["title"]
        result.desc = "fixture first-floor body"
        return result
"""

_TIEBA_CLIENT = r"""
class BaiduTieBaClient:
    async def get_all_notes_by_creator_url(
        self,
        creator_url,
        crawl_interval=1.0,
        callback=None,
        max_note_count=0,
    ):
        return []
"""

_TIEBA_STORE_IMPL = r"""
import json
from pathlib import Path

import config


class TieBaJsonlStoreImplement:
    async def store_content(self, content_item):
        target = Path(config.SAVE_DATA_PATH) / "tieba" / "jsonl" / "detail_contents_fixture.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(content_item, separators=(",", ":")) + "\n", encoding="utf-8")
"""

_TIEBA_STORE = r"""
import asyncio

from ._store_impl import TieBaJsonlStoreImplement


async def update_tieba_note(note_item):
    await asyncio.sleep(0)
    await TieBaJsonlStoreImplement().store_content(note_item.model_dump())
"""

_TIEBA_MAIN = r"""
import asyncio
import os
from pathlib import Path

import config
from media_platform.tieba.help import TieBaExtractor
from store import tieba as tieba_store

crawler = None


class FakeCrawler:
    async def start(self):
        assert config.PLATFORM == "tieba"
        assert config.LOGIN_TYPE == "qrcode"
        assert config.CRAWLER_TYPE == "detail"
        assert config.CREATOR_MODE is False
        assert config.CRAWLER_MAX_NOTES_COUNT == 1
        assert config.TIEBA_SPECIFIED_ID_LIST == [__TIEBA_NOTE_ID__]
        assert config.SAVE_DATA_OPTION == "jsonl"
        assert config.MAX_CONCURRENCY_NUM == 1
        assert config.ENABLE_GET_COMMENTS is False
        assert config.ENABLE_GET_MEIDAS is False
        assert config.ENABLE_GET_MEDIAS is False
        profile = Path(
            os.path.join(os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM)
        ).resolve()
        profile.mkdir(parents=True, exist_ok=True)
        (profile / "session.marker").write_text("stable fixture profile", encoding="utf-8")
        api_data = {
            "thread": {
                "id": __TIEBA_NOTE_ID__,
                "tid": __TIEBA_NOTE_ID__,
                "title": "Fixture Tieba thread",
            },
            "first_floor": {
                "tid": __TIEBA_NOTE_ID__,
                "content": [
                    {"type": 0, "text": "fixture first-floor body"},
                    {
                        "type": 3,
                        "origin_src": __TIEBA_IMAGE_URL__,
                        "cdn_src": __TIEBA_CDN_URL__,
                        "big_cdn_src": __TIEBA_BIG_CDN_URL__,
                        "cdn_src_active": __TIEBA_ACTIVE_CDN_URL__,
                        "pic_id": 300933013320,
                        "bsize": "560,303",
                        "origin_size": 65144,
                        "is_long_pic": 0,
                        "show_original_btn": 1,
                    },
                    __TIEBA_SECOND_IMAGE_ITEM__
                ],
            },
        }

        async def extract_in_detail_task():
            await asyncio.sleep(0)
            return TieBaExtractor().extract_note_detail_from_api(api_data)

        note = (await asyncio.gather(extract_in_detail_task()))[0]
        await tieba_store.update_tieba_note(note)


async def main():
    global crawler
    crawler = FakeCrawler()
    await crawler.start()


async def async_cleanup():
    return None
"""


def _fake_checkout(root: Path) -> Path:
    checkout = root / "fake-mediacrawler"
    (checkout / "config").mkdir(parents=True)
    (checkout / "config" / "__init__.py").write_text(textwrap.dedent(_CONFIG).lstrip(), encoding="utf-8")
    main_source = textwrap.dedent(_MAIN).lstrip().replace("__DY_COVER_URL__", repr(DY_COVER_URL))
    (checkout / "main.py").write_text(main_source, encoding="utf-8")
    return checkout.resolve()


def _fake_xhs_checkout(root: Path, *, creator_mode: bool, video_mode: bool = False) -> Path:
    checkout = root / "fake-mediacrawler-xhs"
    (checkout / "config").mkdir(parents=True)
    (checkout / "config" / "__init__.py").write_text(textwrap.dedent(_CONFIG).lstrip(), encoding="utf-8")
    target_record = (
        {
            "note_id": XHS_NOTE_ID,
            "type": "video",
            "title": "target video",
            "image_list": XHS_COVER_URL,
            "video_url": XHS_VIDEO_URL,
        }
        if video_mode
        else {
            "note_id": XHS_NOTE_ID,
            "type": "normal",
            "title": "target",
            "image_list": XHS_IMAGE_URL,
        }
    )
    records = [
        {
            "note_id": "different-note",
            "type": "normal",
            "title": "other",
            "image_list": "https://image.example.test/xhs/other.jpg?sign=other",
        },
        target_record,
    ]
    if not creator_mode:
        records = records[1:]
    main_source = (
        textwrap.dedent(_XHS_MAIN)
        .lstrip()
        .replace("__CREATOR_MODE__", repr(creator_mode))
        .replace("__CREATOR_URL__", repr(XHS_CREATOR_URL))
        .replace("__DETAIL_URL__", repr(XHS_DETAIL_URL))
        .replace("__RECORDS__", repr(records))
    )
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


def _fake_zhihu_checkout(root: Path) -> Path:
    checkout = root / "fake-mediacrawler-zhihu"
    for package in (
        checkout / "config",
        checkout / "media_platform",
        checkout / "media_platform" / "zhihu",
        checkout / "store",
        checkout / "store" / "zhihu",
    ):
        package.mkdir(parents=True, exist_ok=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
    (checkout / "config" / "__init__.py").write_text(textwrap.dedent(_CONFIG).lstrip(), encoding="utf-8")
    (checkout / "media_platform" / "zhihu" / "help.py").write_text(
        textwrap.dedent(_ZHIHU_HELP).lstrip(), encoding="utf-8"
    )
    (checkout / "media_platform" / "zhihu" / "client.py").write_text(
        textwrap.dedent(_ZHIHU_CLIENT).lstrip(), encoding="utf-8"
    )
    (checkout / "store" / "zhihu" / "_store_impl.py").write_text(
        textwrap.dedent(_ZHIHU_STORE_IMPL).lstrip(), encoding="utf-8"
    )
    (checkout / "store" / "zhihu" / "__init__.py").write_text(textwrap.dedent(_ZHIHU_STORE).lstrip(), encoding="utf-8")
    main_source = (
        textwrap.dedent(_ZHIHU_MAIN)
        .lstrip()
        .replace("__ZHIHU_ANSWER_URL__", repr(ZHIHU_ANSWER_URL))
        .replace("__ZHIHU_ANSWER_ID__", repr(ZHIHU_ANSWER_ID))
        .replace("__ZHIHU_QUESTION_ID__", repr(ZHIHU_QUESTION_ID))
        .replace("__ZHIHU_IMAGE_URL__", repr(ZHIHU_IMAGE_URL))
    )
    (checkout / "main.py").write_text(main_source, encoding="utf-8")
    return checkout.resolve()


def _fake_tieba_checkout(root: Path, *, gallery_size: int = 1) -> Path:
    if gallery_size not in {1, 2, 3}:
        raise ValueError("unsupported fixture gallery size")
    checkout = root / "fake-mediacrawler-tieba"
    for package in (
        checkout / "config",
        checkout / "media_platform",
        checkout / "media_platform" / "tieba",
        checkout / "store",
        checkout / "store" / "tieba",
    ):
        package.mkdir(parents=True, exist_ok=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
    (checkout / "config" / "__init__.py").write_text(textwrap.dedent(_CONFIG).lstrip(), encoding="utf-8")
    (checkout / "media_platform" / "tieba" / "help.py").write_text(
        textwrap.dedent(_TIEBA_HELP).lstrip(), encoding="utf-8"
    )
    (checkout / "media_platform" / "tieba" / "client.py").write_text(
        textwrap.dedent(_TIEBA_CLIENT).lstrip(), encoding="utf-8"
    )
    (checkout / "store" / "tieba" / "_store_impl.py").write_text(
        textwrap.dedent(_TIEBA_STORE_IMPL).lstrip(), encoding="utf-8"
    )
    (checkout / "store" / "tieba" / "__init__.py").write_text(textwrap.dedent(_TIEBA_STORE).lstrip(), encoding="utf-8")
    query = f"tbpicau={TIEBA_TOKEN}"
    second_query = f"tbpicau={TIEBA_SECOND_TOKEN}"
    second_item = {
        "type": 3,
        "origin_src": TIEBA_SECOND_IMAGE_URL,
        "cdn_src": f"https://tiebapic.baidu.com/forum/w%3D720/sign=d/{TIEBA_SECOND_IMAGE_ID}.jpg?{second_query}",
        "big_cdn_src": (f"https://tiebapic.baidu.com/forum/w%3D1920/sign=e/{TIEBA_SECOND_IMAGE_ID}.jpg?{second_query}"),
        "cdn_src_active": (
            f"https://tiebapic.baidu.com/forum/w%3D720/sign=f/{TIEBA_SECOND_IMAGE_ID}.jpg?{second_query}"
        ),
        "pic_id": 300_933_013_321,
        "bsize": "640,360",
        "origin_size": 72_144,
        "is_long_pic": 0,
        "show_original_btn": 1,
    }
    third_query = f"tbpicau={TIEBA_THIRD_TOKEN}"
    third_item = {
        "type": 3,
        "origin_src": TIEBA_THIRD_IMAGE_URL,
        "cdn_src": f"https://tiebapic.baidu.com/forum/w%3D720/sign=g/{TIEBA_THIRD_IMAGE_ID}.jpg?{third_query}",
        "big_cdn_src": f"https://tiebapic.baidu.com/forum/w%3D1920/sign=h/{TIEBA_THIRD_IMAGE_ID}.jpg?{third_query}",
        "cdn_src_active": (f"https://tiebapic.baidu.com/forum/w%3D720/sign=i/{TIEBA_THIRD_IMAGE_ID}.jpg?{third_query}"),
        "pic_id": 300_933_013_322,
        "bsize": "800,450",
        "origin_size": 82_144,
        "is_long_pic": 0,
        "show_original_btn": 1,
    }
    extra_items = (second_item, third_item)[: gallery_size - 1]
    main_source = (
        textwrap.dedent(_TIEBA_MAIN)
        .lstrip()
        .replace("__TIEBA_NOTE_ID__", repr(TIEBA_NOTE_ID))
        .replace("__TIEBA_IMAGE_URL__", repr(TIEBA_IMAGE_URL))
        .replace(
            "__TIEBA_CDN_URL__",
            repr(f"https://tiebapic.baidu.com/forum/w%3D720/sign=a/{TIEBA_IMAGE_ID}.jpg?{query}"),
        )
        .replace(
            "__TIEBA_BIG_CDN_URL__",
            repr(f"https://tiebapic.baidu.com/forum/w%3D1920/sign=b/{TIEBA_IMAGE_ID}.jpg?{query}"),
        )
        .replace(
            "__TIEBA_ACTIVE_CDN_URL__",
            repr(f"https://tiebapic.baidu.com/forum/w%3D720/sign=c/{TIEBA_IMAGE_ID}.jpg?{query}"),
        )
        .replace("__TIEBA_SECOND_IMAGE_ITEM__", ",".join(repr(item) for item in extra_items))
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


def _xhs_process_runner(tmp_path: Path, checkout: Path) -> MediaCrawlerDetailProcessRunner:
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


def _xhs_context(*, creator_mode: bool, video_mode: bool = False) -> MediaCrawlerRefreshContext:
    kind = AssetKind.VIDEO if video_mode else AssetKind.IMAGE
    source_url = XHS_VIDEO_URL if video_mode else XHS_IMAGE_URL
    remote_id = f"{XHS_NOTE_ID}:{kind.value}:0"
    locator = AdapterRefreshLocator(
        adapter="mediacrawler",
        asset_key=stable_asset_key(
            platform="xhs",
            content_remote_type="content",
            content_remote_id=XHS_NOTE_ID,
            kind=kind.value,
            position=0,
            remote_id=remote_id,
        ),
    )
    source_hint = asset_source_hint(source_url)
    assert source_hint is not None
    return MediaCrawlerRefreshContext(
        asset_id=ASSET_ID,
        account_id=ACCOUNT_ID,
        subscription_id=SUBSCRIPTION_ID,
        platform=Platform.XHS,
        login_method=LoginMethod.QR,
        content_remote_type="content",
        content_remote_id=XHS_NOTE_ID,
        author_remote_id=XHS_AUTHOR_ID,
        author_display_name="XHS fixture creator",
        asset_remote_id=remote_id,
        asset_kind=kind,
        asset_position=0,
        source_hint=source_hint,
        locator=locator,
        detail_reference=None if creator_mode else SecretValue(XHS_DETAIL_URL),
        creator_reference=SecretValue(XHS_CREATOR_URL) if creator_mode else None,
        creator_max_items=2 if creator_mode else None,
        watchdogs=WatchdogLimits(
            max_seconds=10,
            max_output_bytes=64 * 1024,
            max_output_items=2,
            max_output_files=4,
            max_line_bytes=16 * 1024,
            poll_seconds=0.01,
        ),
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


def _zhihu_process_runner(tmp_path: Path, checkout: Path) -> MediaCrawlerDetailProcessRunner:
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


def _tieba_process_runner(tmp_path: Path, checkout: Path) -> MediaCrawlerDetailProcessRunner:
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


def _zhihu_context() -> MediaCrawlerRefreshContext:
    remote_id = f"{ZHIHU_ANSWER_ID}:image:0"
    source_hint = asset_source_hint(ZHIHU_IMAGE_URL)
    assert source_hint is not None
    return MediaCrawlerRefreshContext(
        asset_id=ASSET_ID,
        account_id=ACCOUNT_ID,
        subscription_id=SUBSCRIPTION_ID,
        platform=Platform.ZHIHU,
        login_method=LoginMethod.QR,
        content_remote_type="content",
        content_remote_id=ZHIHU_ANSWER_ID,
        author_remote_id="creator-42",
        author_display_name="Zhihu fixture creator",
        asset_remote_id=remote_id,
        asset_kind=AssetKind.IMAGE,
        asset_position=0,
        source_hint=source_hint,
        locator=AdapterRefreshLocator(
            adapter="mediacrawler",
            asset_key=stable_asset_key(
                platform="zhihu",
                content_remote_type="content",
                content_remote_id=ZHIHU_ANSWER_ID,
                kind="image",
                position=0,
                remote_id=remote_id,
            ),
        ),
        detail_reference=ZHIHU_ANSWER_URL,
        request_delay_seconds=0.25,
        watchdogs=WatchdogLimits(max_seconds=10, poll_seconds=0.01),
    )


def _tieba_context(*, position: int = 0, gallery_size: int = 1) -> MediaCrawlerRefreshContext:
    hints = (TIEBA_IMAGE_HINT, TIEBA_SECOND_IMAGE_HINT, TIEBA_THIRD_IMAGE_HINT)[:gallery_size]
    remote_id = f"{TIEBA_NOTE_ID}:image:{position}"
    return MediaCrawlerRefreshContext(
        asset_id=ASSET_ID,
        account_id=ACCOUNT_ID,
        subscription_id=SUBSCRIPTION_ID,
        platform=Platform.TIEBA,
        login_method=LoginMethod.QR,
        content_remote_type="content",
        content_remote_id=TIEBA_NOTE_ID,
        author_remote_id="creator-42",
        author_display_name="Tieba fixture creator",
        asset_remote_id=remote_id,
        asset_kind=AssetKind.IMAGE,
        asset_position=position,
        source_hint=hints[position],
        locator=AdapterRefreshLocator(
            adapter="mediacrawler",
            asset_key=stable_asset_key(
                platform="tieba",
                content_remote_type="content",
                content_remote_id=TIEBA_NOTE_ID,
                kind="image",
                position=position,
                remote_id=remote_id,
            ),
        ),
        tieba_image_source_hints=hints,
        detail_reference=TIEBA_THREAD_URL,
        request_delay_seconds=0.25,
        watchdogs=WatchdogLimits(max_seconds=10, poll_seconds=0.01),
    )


def _bili_video_context(
    *,
    cids: tuple[int, ...] = (),
    position: int = 0,
) -> MediaCrawlerRefreshContext:
    remote_ids = tuple(f"987654321:video:cid:{cid}" for cid in cids) if len(cids) > 1 else ("987654321:video:0",)
    remote_id = remote_ids[position]
    locator = AdapterRefreshLocator(
        adapter="mediacrawler",
        asset_key=stable_asset_key(
            platform="bili",
            content_remote_type="content",
            content_remote_id="987654321",
            kind="video",
            position=position,
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
        asset_position=position,
        source_hint=None,
        locator=locator,
        bili_video_remote_ids=remote_ids,
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


@pytest.mark.parametrize("creator_mode", [True, False], ids=["creator-fallback", "explicit-detail"])
def test_xhs_creator_fallback_and_explicit_detail_are_isolated_and_cleaned(
    tmp_path: Path,
    creator_mode: bool,
) -> None:
    checkout = _fake_xhs_checkout(tmp_path, creator_mode=creator_mode)
    context = _xhs_context(creator_mode=creator_mode)

    resolved = MediaCrawlerLocatorRefresher(context, _xhs_process_runner(tmp_path, checkout)).resolve(context.locator)

    assert resolved.url == XHS_IMAGE_URL
    assert resolved.request_profile is MediaRequestProfile.DEFAULT
    assert list((tmp_path / "runtime" / "jobs").iterdir()) == []
    retained = b"".join(path.read_bytes() for path in (tmp_path / "runtime").rglob("*") if path.is_file())
    assert b"xhs-creator-authority-sentinel" not in retained
    assert b"xhs-detail-authority-sentinel" not in retained
    assert b"xhs-image-sentinel" not in retained


def test_xhs_creator_video_refresh_uses_exact_cdn_asset_and_cleans_ephemera(tmp_path: Path) -> None:
    checkout = _fake_xhs_checkout(tmp_path, creator_mode=True, video_mode=True)
    context = _xhs_context(creator_mode=True, video_mode=True)

    resolved = MediaCrawlerLocatorRefresher(context, _xhs_process_runner(tmp_path, checkout)).resolve(context.locator)

    assert resolved.url == XHS_VIDEO_URL
    assert resolved.request_profile is MediaRequestProfile.DEFAULT
    assert "xhs-video-sentinel" not in repr(context)
    assert "xhs-video-sentinel" not in repr(resolved)
    assert list((tmp_path / "runtime" / "jobs").iterdir()) == []
    retained = b"".join(path.read_bytes() for path in (tmp_path / "runtime").rglob("*") if path.is_file())
    assert b"xhs-creator-authority-sentinel" not in retained
    assert b"xhs-video-sentinel" not in retained
    assert b"xhs-cover-sentinel" not in retained


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
            author_remote_id="creator-42",
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


def test_zhihu_answer_detail_installs_image_shim_binds_config_and_cleans_ephemera(tmp_path: Path) -> None:
    checkout = _fake_zhihu_checkout(tmp_path)
    context = _zhihu_context()

    resolved = MediaCrawlerLocatorRefresher(
        context,
        _zhihu_process_runner(tmp_path, checkout),
    ).resolve(context.locator)

    assert resolved.url == ZHIHU_IMAGE_URL
    assert resolved.request_profile is MediaRequestProfile.DEFAULT
    assert list((tmp_path / "runtime" / "jobs").iterdir()) == []
    profile = tmp_path / "runtime" / "accounts" / "zhihu" / str(ACCOUNT_ID) / "browser_data" / "zhihu_user_data_dir"
    assert (profile / "session.marker").read_text(encoding="utf-8") == "stable fixture profile"
    retained = b"".join(path.read_bytes() for path in (tmp_path / "runtime").rglob("*") if path.is_file())
    assert ZHIHU_IMAGE_FIELD.encode("utf-8") not in retained
    assert b"zhihu-detail-sentinel" not in retained


def test_tieba_detail_installs_first_floor_shim_binds_numeric_config_and_cleans_ephemera(
    tmp_path: Path,
) -> None:
    checkout = _fake_tieba_checkout(tmp_path)
    context = _tieba_context()

    resolved = MediaCrawlerLocatorRefresher(
        context,
        _tieba_process_runner(tmp_path, checkout),
    ).resolve(context.locator)

    assert resolved.url == TIEBA_IMAGE_URL
    assert resolved.request_profile is MediaRequestProfile.DEFAULT
    assert list((tmp_path / "runtime" / "jobs").iterdir()) == []
    profile = tmp_path / "runtime" / "accounts" / "tieba" / str(ACCOUNT_ID) / "browser_data" / "tieba_user_data_dir"
    assert (profile / "session.marker").read_text(encoding="utf-8") == "stable fixture profile"
    retained = b"".join(path.read_bytes() for path in (tmp_path / "runtime").rglob("*") if path.is_file())
    assert TIEBA_IMAGE_FIELD.encode("utf-8") not in retained
    assert TIEBA_TOKEN.encode("utf-8") not in retained


@pytest.mark.parametrize("position", [0, 1])
def test_tieba_detail_carries_exact_two_image_gallery_across_gather_and_refreshes_each_position(
    tmp_path: Path,
    position: int,
) -> None:
    checkout = _fake_tieba_checkout(tmp_path, gallery_size=2)
    context = _tieba_context(position=position, gallery_size=2)

    resolved = MediaCrawlerLocatorRefresher(
        context,
        _tieba_process_runner(tmp_path, checkout),
    ).resolve(context.locator)

    assert resolved.url == (TIEBA_IMAGE_URL, TIEBA_SECOND_IMAGE_URL)[position]
    assert resolved.request_profile is MediaRequestProfile.DEFAULT
    assert list((tmp_path / "runtime" / "jobs").iterdir()) == []
    retained = b"".join(path.read_bytes() for path in (tmp_path / "runtime").rglob("*") if path.is_file())
    for transient in (TIEBA_IMAGE_FIELD, TIEBA_IMAGES_FIELD, TIEBA_TOKEN, TIEBA_SECOND_TOKEN):
        assert transient.encode("utf-8") not in retained


@pytest.mark.parametrize("position", [0, 1, 2])
def test_tieba_detail_carries_v3_gallery_across_gather_and_refreshes_each_position(
    tmp_path: Path,
    position: int,
) -> None:
    checkout = _fake_tieba_checkout(tmp_path, gallery_size=3)
    context = _tieba_context(position=position, gallery_size=3)

    resolved = MediaCrawlerLocatorRefresher(
        context,
        _tieba_process_runner(tmp_path, checkout),
    ).resolve(context.locator)

    assert resolved.url == (TIEBA_IMAGE_URL, TIEBA_SECOND_IMAGE_URL, TIEBA_THIRD_IMAGE_URL)[position]
    assert resolved.request_profile is MediaRequestProfile.DEFAULT
    assert list((tmp_path / "runtime" / "jobs").iterdir()) == []
    retained = b"".join(path.read_bytes() for path in (tmp_path / "runtime").rglob("*") if path.is_file())
    for transient in (
        TIEBA_IMAGE_FIELD,
        TIEBA_IMAGES_FIELD,
        TIEBA_GALLERY_FIELD,
        TIEBA_TOKEN,
        TIEBA_SECOND_TOKEN,
        TIEBA_THIRD_TOKEN,
    ):
        assert transient.encode("utf-8") not in retained


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
            author_remote_id="creator-42",
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
            author_remote_id="creator-42",
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
        author_remote_id="creator-42",
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
            "author_remote_id": "creator-42",
            "detail_reference": "7525082444551310603",
            "creator_reference": None,
            "creator_max_items": None,
            "cookie": None,
            "headless": True,
            "request_delay_seconds": 0.25,
            "bili_progressive_detail": False,
            "bili_video_cid": None,
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


def test_zhihu_detail_parent_accepts_only_plain_canonical_answer_authority() -> None:
    request = MediaCrawlerDetailRequest(
        account_id=ACCOUNT_ID,
        subscription_id=SUBSCRIPTION_ID,
        platform=Platform.ZHIHU,
        login_method=LoginMethod.QR,
        content_remote_id=ZHIHU_ANSWER_ID,
        author_remote_id="creator-42",
        detail_reference=ZHIHU_ANSWER_URL,
    )

    assert request.resolved_detail_reference() == ZHIHU_ANSWER_URL
    assert request.creator_reference is None
    assert request.creator_max_items is None


@pytest.mark.parametrize(
    "detail_reference",
    [
        None,
        SecretValue(ZHIHU_ANSWER_URL),
        f"https://www.zhihu.com/question/{ZHIHU_QUESTION_ID}/answer/987654322",
        f"{ZHIHU_ANSWER_URL}?",
        f"{ZHIHU_ANSWER_URL}?utm_source=drift",
        f"http://www.zhihu.com/question/{ZHIHU_QUESTION_ID}/answer/{ZHIHU_ANSWER_ID}",
        f"{ZHIHU_ANSWER_URL}/",
    ],
)
def test_zhihu_detail_parent_rejects_missing_secret_or_unbound_reference(
    detail_reference: str | SecretValue | None,
) -> None:
    with pytest.raises(MediaDownloadError, match="locator_refresh_configuration_invalid"):
        MediaCrawlerDetailRequest(
            account_id=ACCOUNT_ID,
            subscription_id=SUBSCRIPTION_ID,
            platform=Platform.ZHIHU,
            login_method=LoginMethod.QR,
            content_remote_id=ZHIHU_ANSWER_ID,
            author_remote_id="creator-42",
            detail_reference=detail_reference,
        )


def test_zhihu_detail_parent_rejects_creator_mode_authority() -> None:
    with pytest.raises(MediaDownloadError, match="locator_refresh_configuration_invalid"):
        MediaCrawlerDetailRequest(
            account_id=ACCOUNT_ID,
            subscription_id=SUBSCRIPTION_ID,
            platform=Platform.ZHIHU,
            login_method=LoginMethod.QR,
            content_remote_id=ZHIHU_ANSWER_ID,
            author_remote_id="creator-42",
            detail_reference=ZHIHU_ANSWER_URL,
            creator_reference=SecretValue(ZHIHU_ANSWER_URL),
            creator_max_items=1,
        )


def test_zhihu_detail_child_revalidates_canonical_answer_identity(tmp_path: Path) -> None:
    account_root = tmp_path / "accounts" / "zhihu" / str(ACCOUNT_ID)
    profile_root = account_root / "browser_data" / "zhihu_user_data_dir"
    job_root = tmp_path / "jobs" / "attempt"
    limits = WatchdogLimits()
    base: dict[str, object] = {
        "schema_version": detail_runner_module.DETAIL_RUNNER_SCHEMA_VERSION,
        "checkout_root": str(Path.cwd().resolve()),
        "account_root": str(account_root),
        "profile_root": str(profile_root),
        "job_root": str(job_root),
        "output_root": str(job_root / "output"),
        "platform": Platform.ZHIHU.value,
        "login_method": LoginMethod.QR.value,
        "content_remote_id": ZHIHU_ANSWER_ID,
        "author_remote_id": "creator-42",
        "detail_reference": ZHIHU_ANSWER_URL,
        "creator_reference": None,
        "creator_max_items": None,
        "cookie": None,
        "headless": True,
        "request_delay_seconds": 0.25,
        "bili_progressive_detail": False,
        "bili_video_cid": None,
        "watchdogs": {
            "max_seconds": limits.max_seconds,
            "max_output_bytes": limits.max_output_bytes,
            "max_output_items": limits.max_output_items,
            "max_output_files": limits.max_output_files,
            "max_line_bytes": limits.max_line_bytes,
            "poll_seconds": limits.poll_seconds,
        },
    }

    valid = detail_runner_module._ChildRequest.load(json.dumps(base, separators=(",", ":")).encode())
    assert valid.detail_reference == ZHIHU_ANSWER_URL

    for changes in (
        {"content_remote_id": "987654322"},
        {"detail_reference": f"{ZHIHU_ANSWER_URL}?"},
        {"detail_reference": f"{ZHIHU_ANSWER_URL}?utm_source=drift"},
        {"creator_reference": ZHIHU_ANSWER_URL},
        {"creator_max_items": 1},
    ):
        tampered = dict(base)
        tampered.update(changes)
        with pytest.raises(detail_runner_module._ChildConfigurationError):
            detail_runner_module._ChildRequest.load(json.dumps(tampered, separators=(",", ":")).encode())


def test_tieba_detail_parent_accepts_only_plain_canonical_thread_authority() -> None:
    request = MediaCrawlerDetailRequest(
        account_id=ACCOUNT_ID,
        subscription_id=SUBSCRIPTION_ID,
        platform=Platform.TIEBA,
        login_method=LoginMethod.QR,
        content_remote_id=TIEBA_NOTE_ID,
        author_remote_id="creator-42",
        detail_reference=TIEBA_THREAD_URL,
    )

    assert request.resolved_detail_reference() == TIEBA_THREAD_URL
    assert request.creator_reference is None
    assert request.creator_max_items is None


@pytest.mark.parametrize(
    "detail_reference",
    [
        None,
        SecretValue(TIEBA_THREAD_URL),
        "https://tieba.baidu.com/p/10376710030",
        f"{TIEBA_THREAD_URL}?",
        f"{TIEBA_THREAD_URL}?pn=1",
        f"http://tieba.baidu.com/p/{TIEBA_NOTE_ID}",
        f"{TIEBA_THREAD_URL}/",
        f"https://TIEBA.BAIDU.COM/p/{TIEBA_NOTE_ID}",
    ],
)
def test_tieba_detail_parent_rejects_missing_secret_or_unbound_reference(
    detail_reference: str | SecretValue | None,
) -> None:
    with pytest.raises(MediaDownloadError, match="locator_refresh_configuration_invalid"):
        MediaCrawlerDetailRequest(
            account_id=ACCOUNT_ID,
            subscription_id=SUBSCRIPTION_ID,
            platform=Platform.TIEBA,
            login_method=LoginMethod.QR,
            content_remote_id=TIEBA_NOTE_ID,
            author_remote_id="creator-42",
            detail_reference=detail_reference,
        )


def test_tieba_detail_child_revalidates_canonical_thread_identity(tmp_path: Path) -> None:
    account_root = tmp_path / "accounts" / "tieba" / str(ACCOUNT_ID)
    profile_root = account_root / "browser_data" / "tieba_user_data_dir"
    job_root = tmp_path / "jobs" / "attempt"
    limits = WatchdogLimits()
    base: dict[str, object] = {
        "schema_version": detail_runner_module.DETAIL_RUNNER_SCHEMA_VERSION,
        "checkout_root": str(Path.cwd().resolve()),
        "account_root": str(account_root),
        "profile_root": str(profile_root),
        "job_root": str(job_root),
        "output_root": str(job_root / "output"),
        "platform": Platform.TIEBA.value,
        "login_method": LoginMethod.QR.value,
        "content_remote_id": TIEBA_NOTE_ID,
        "author_remote_id": "creator-42",
        "detail_reference": TIEBA_THREAD_URL,
        "creator_reference": None,
        "creator_max_items": None,
        "cookie": None,
        "headless": True,
        "request_delay_seconds": 0.25,
        "bili_progressive_detail": False,
        "bili_video_cid": None,
        "watchdogs": {
            "max_seconds": limits.max_seconds,
            "max_output_bytes": limits.max_output_bytes,
            "max_output_items": limits.max_output_items,
            "max_output_files": limits.max_output_files,
            "max_line_bytes": limits.max_line_bytes,
            "poll_seconds": limits.poll_seconds,
        },
    }

    valid = detail_runner_module._ChildRequest.load(json.dumps(base, separators=(",", ":")).encode())
    assert valid.detail_reference == TIEBA_THREAD_URL

    for changes in (
        {"content_remote_id": "10376710030"},
        {"detail_reference": f"{TIEBA_THREAD_URL}?"},
        {"detail_reference": f"{TIEBA_THREAD_URL}?pn=1"},
        {"detail_reference": f"http://tieba.baidu.com/p/{TIEBA_NOTE_ID}"},
        {"creator_reference": TIEBA_THREAD_URL},
        {"creator_max_items": 1},
    ):
        tampered = dict(base)
        tampered.update(changes)
        with pytest.raises(detail_runner_module._ChildConfigurationError):
            detail_runner_module._ChildRequest.load(json.dumps(tampered, separators=(",", ":")).encode())


def test_xhs_detail_child_revalidates_creator_authority_xor_and_bounds(tmp_path: Path) -> None:
    account_root = tmp_path / "accounts" / "xhs" / str(ACCOUNT_ID)
    profile_root = account_root / "browser_data" / "xhs_user_data_dir"
    job_root = tmp_path / "jobs" / "attempt"
    limits = WatchdogLimits(max_output_items=2)
    base: dict[str, object] = {
        "schema_version": detail_runner_module.DETAIL_RUNNER_SCHEMA_VERSION,
        "checkout_root": str(Path.cwd().resolve()),
        "account_root": str(account_root),
        "profile_root": str(profile_root),
        "job_root": str(job_root),
        "output_root": str(job_root / "output"),
        "platform": Platform.XHS.value,
        "login_method": LoginMethod.QR.value,
        "content_remote_id": XHS_NOTE_ID,
        "author_remote_id": XHS_AUTHOR_ID,
        "detail_reference": None,
        "creator_reference": XHS_CREATOR_URL,
        "creator_max_items": 2,
        "cookie": None,
        "headless": True,
        "request_delay_seconds": 0.25,
        "bili_progressive_detail": False,
        "bili_video_cid": None,
        "watchdogs": {
            "max_seconds": limits.max_seconds,
            "max_output_bytes": limits.max_output_bytes,
            "max_output_items": limits.max_output_items,
            "max_output_files": limits.max_output_files,
            "max_line_bytes": limits.max_line_bytes,
            "poll_seconds": limits.poll_seconds,
        },
    }
    valid = detail_runner_module._ChildRequest.load(json.dumps(base, separators=(",", ":")).encode())
    assert "xhs-creator-authority-sentinel" not in repr(valid)

    tampered = [
        {"author_remote_id": "different-author"},
        {"detail_reference": XHS_DETAIL_URL},
        {"creator_max_items": 3},
    ]
    for changes in tampered:
        payload = dict(base)
        payload.update(changes)
        with pytest.raises(detail_runner_module._ChildConfigurationError):
            detail_runner_module._ChildRequest.load(json.dumps(payload, separators=(",", ":")).encode())


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
        "pages": [{"page": 1, "cid": 24680}],
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


def test_bilibili_multipart_child_fetches_only_the_requested_cid_and_returns_the_complete_tuple(
    tmp_path: Path,
) -> None:
    cids = (24680, 97531, 86420)
    view = {
        "aid": 987654321,
        "cid": cids[0],
        "pages": [{"page": index, "cid": cid} for index, cid in enumerate(cids, 1)],
        "title": "three page fixture",
        "desc": "fixture",
        "pic": BILI_COVER,
        "owner": {"mid": 42, "name": "fixture"},
        "stat": {},
    }
    checkout = _fake_bili_checkout(tmp_path, view=view, expected_cid=cids[1])
    context = _bili_video_context(cids=cids, position=1)

    resolved = MediaCrawlerLocatorRefresher(context, _bili_process_runner(tmp_path, checkout)).resolve(context.locator)

    assert resolved.url == BILI_VIDEO_URL
    assert resolved.request_profile is MediaRequestProfile.BILIBILI_MEDIA
    request = context.detail_request()
    assert request.bili_video_cid == cids[1]
    assert "ephemeral-sentinel" not in repr(request)


def test_bilibili_dash_selects_quality_codec_hires_audio_and_keeps_urls_ephemeral(tmp_path: Path) -> None:
    play_response = {
        "dash": {
            "video": [
                {
                    "id": 80,
                    "codecid": 7,
                    "base_url": "https://video.example.test/bili/1080p-avc.m4s?sig=lower-quality",
                },
                {
                    "id": 127,
                    "codecid": 13,
                    "base_url": "https://video.example.test/bili/av1.m4s?sig=dash-av1-sentinel",
                },
                {
                    "id": 127,
                    "codecid": 12,
                    "baseUrl": "https://video.example.test/bili/hev.m4s?sig=dash-hev-sentinel",
                },
                {
                    "id": 127,
                    "codecid": 7,
                    "base_url": BILI_DASH_AVC_URL,
                    "backup_url": [BILI_DASH_AVC_BACKUP],
                },
                {"id": 999, "codecid": 7},
            ],
            "audio": [
                {
                    "id": 30280,
                    "base_url": "https://audio.example.test/bili/192k.m4s?sig=dash-192k-sentinel",
                }
            ],
            "dolby": {
                "audio": [
                    {
                        "id": 30250,
                        "base_url": "https://audio.example.test/bili/dolby.m4s?sig=dash-dolby-sentinel",
                    }
                ]
            },
            "flac": {"audio": {"id": 30251, "base_url": BILI_DASH_AUDIO_URL}},
        }
    }
    checkout = _fake_bili_checkout(tmp_path, play_response=play_response)
    context = _bili_video_context()

    resolved = MediaCrawlerLocatorRefresher(context, _bili_process_runner(tmp_path, checkout)).resolve(context.locator)

    assert isinstance(resolved, ResolvedDashLocator)
    assert resolved.selection_key == (127, "avc", 30251)
    assert resolved.video.url == BILI_DASH_AVC_URL
    assert resolved.video.backup_urls == (BILI_DASH_AVC_BACKUP,)
    assert resolved.video.request_profile is MediaRequestProfile.BILIBILI_MEDIA
    assert resolved.audio is not None
    assert resolved.audio.url == BILI_DASH_AUDIO_URL
    assert resolved.audio.request_profile is MediaRequestProfile.BILIBILI_MEDIA
    for sentinel in (
        "dash-avc-sentinel",
        "dash-backup-sentinel",
        "dash-audio-sentinel",
        "dash-av1-sentinel",
        "dash-hev-sentinel",
    ):
        assert sentinel not in repr(resolved)
    jobs_root = tmp_path / "runtime" / "jobs"
    assert jobs_root.is_dir() and list(jobs_root.iterdir()) == []
    retained = b"".join(path.read_bytes() for path in (tmp_path / "runtime").rglob("*") if path.is_file())
    assert BILI_DASH_AVC_URL.encode() not in retained
    assert BILI_DASH_AVC_BACKUP.encode() not in retained
    assert BILI_DASH_AUDIO_URL.encode() not in retained
    assert b"__media_sync_bili_dash_page_v1" not in retained


def test_bilibili_silent_dash_is_a_valid_selected_target(tmp_path: Path) -> None:
    play_response = {
        "dash": {
            "video": [{"id": 120, "codecid": 12, "base_url": BILI_DASH_AVC_URL}],
            "audio": [],
            "dolby": {"audio": None},
            "flac": {"audio": None},
        }
    }
    checkout = _fake_bili_checkout(tmp_path, play_response=play_response)
    context = _bili_video_context()

    resolved = MediaCrawlerLocatorRefresher(context, _bili_process_runner(tmp_path, checkout)).resolve(context.locator)

    assert isinstance(resolved, ResolvedDashLocator)
    assert resolved.selection_key == (120, "hev", None)
    assert resolved.audio is None


def test_bilibili_private_jsonl_bridge_is_bounded_collision_safe_and_repr_safe() -> None:
    ordinary = json.dumps({"video_id": "987654321", "title": "fixture"}, separators=(",", ":")).encode() + b"\n"
    progressive = detail_runner_module._BiliPlaybackResult(
        aid=987654321,
        pages=(detail_runner_module.BilibiliPageIdentity(page=1, cid=24680),),
        cid=24680,
        target=ResolvedLocator(BILI_VIDEO_URL, MediaRequestProfile.BILIBILI_MEDIA),
    )
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
        ("dash-video-type", {"dash": {"video": {}, "audio": []}}, False, "locator_refresh_result_invalid"),
        (
            "dash-known-video-missing-url",
            {"dash": {"video": [{"id": 127, "codecid": 7}], "audio": []}},
            False,
            "locator_refresh_result_invalid",
        ),
        (
            "dash-conflicting-url-aliases",
            {
                "dash": {
                    "video": [
                        {
                            "id": 127,
                            "codecid": 7,
                            "base_url": BILI_DASH_AVC_URL,
                            "baseUrl": "https://video.example.test/bili/different.m4s?sig=conflict",
                        }
                    ],
                    "audio": [],
                }
            },
            False,
            "locator_refresh_result_invalid",
        ),
        (
            "dash-audio-type",
            {
                "dash": {
                    "video": [{"id": 127, "codecid": 7, "base_url": BILI_DASH_AVC_URL}],
                    "audio": {},
                }
            },
            False,
            "locator_refresh_result_invalid",
        ),
        (
            "dash-known-audio-missing-url",
            {
                "dash": {
                    "video": [{"id": 127, "codecid": 7, "base_url": BILI_DASH_AVC_URL}],
                    "audio": [{"id": 30280}],
                }
            },
            False,
            "locator_refresh_result_invalid",
        ),
        (
            "dash-video-list-limit",
            {
                "dash": {
                    "video": [{"id": 127, "codecid": 7, "base_url": BILI_DASH_AVC_URL}] * 65,
                    "audio": [],
                }
            },
            False,
            "locator_refresh_result_invalid",
        ),
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
