"""Bounded exact dynamic requests on the locked client; no standalone crawler."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

from .bilibili_capture import validate_bili_upload_detail
from .bilibili_dynamic import (
    BILI_DYNAMIC_DETAIL_FEATURES,
    BILI_DYNAMIC_DETAIL_PATH,
    BILI_OPUS_DETAIL_FEATURES,
    BILI_OPUS_DETAIL_PATH,
    BiliDynamicError,
    BiliDynamicIdentityError,
    BiliDynamicUnsupportedError,
    parse_bili_dynamic_detail,
    parse_dynamic_identity,
)
from .bilibili_multifeed import BiliDynamicSnapshotStore, BiliDynamicUnit, BiliMultiFeedCoverage, BiliMultiFeedState
from .bilibili_scan import BiliIdentity

if TYPE_CHECKING:
    from .bridge import RunnerManifest

_DYNAMIC = BILI_DYNAMIC_DETAIL_PATH
_OPUS = BILI_OPUS_DETAIL_PATH
_FEED = "/x/polymer/web-dynamic/v1/feed/space"
_FEATURES = BILI_DYNAMIC_DETAIL_FEATURES
_OPUS_FEATURES = BILI_OPUS_DETAIL_FEATURES


def _failure() -> BiliDynamicError:
    return BiliDynamicError()


async def capture_dynamic_unit(
    manifest: RunnerManifest,
    client: Any,
    creator_id: int,
    store_video: Callable[[Any, BiliIdentity], Awaitable[None]],
) -> BiliMultiFeedCoverage:
    """Persist discovery before checkpoint; consume only exact checked details."""
    state = manifest.bili_scan
    if not isinstance(state, BiliMultiFeedState) or state.next_feed != "dynamics":
        raise _failure()
    original_request, original_keys = client.request, client.get_wbi_keys
    keys: tuple[str, str] | None = None
    expected_path: str | None = None
    expected_query: dict[str, str] = {}
    request_seen = False
    nav_count = 0
    attempts: dict[str, int] = {}
    sent = False
    records: list[dict[str, object]] = []
    videos: dict[str, BiliIdentity] = {}

    async def cached_keys() -> tuple[str, str]:
        nonlocal keys
        if keys is None:
            candidate = await original_keys()
            if (
                not isinstance(candidate, tuple)
                or len(candidate) != 2
                or any(type(value) is not str or re.fullmatch(r"[0-9a-fA-F]{32}", value) is None for value in candidate)
            ):
                raise _failure()
            keys = candidate
        return keys

    async def guarded_request(method: str, url: str, **kwargs: Any) -> Any:
        nonlocal request_seen, nav_count, sent
        parsed = urlsplit(url)
        if method != "GET" or parsed.scheme != "https" or parsed.netloc != "api.bilibili.com" or parsed.fragment:
            raise _failure()
        query = parse_qs(parsed.query, keep_blank_values=True)
        if parsed.path == "/x/web-interface/nav":
            if query or nav_count or expected_path not in {_FEED, _DYNAMIC, _OPUS} or keys is not None:
                raise _failure()
            nav_count += 1
        else:
            if request_seen or parsed.path != expected_path or any(len(values) != 1 for values in query.values()):
                raise _failure()
            signed = parsed.path in {_FEED, _DYNAMIC, _OPUS}
            expected_keys = set(expected_query) | ({"wts", "w_rid"} if signed else set())
            if set(query) != expected_keys or any(query.get(key) != [value] for key, value in expected_query.items()):
                raise _failure()
            if signed and (
                re.fullmatch(r"[0-9]{1,12}", query["wts"][0]) is None
                or re.fullmatch(r"[0-9a-f]{32}", query["w_rid"][0]) is None
            ):
                raise _failure()
            attempts[parsed.path] = attempts.get(parsed.path, 0) + 1
            maximum = 1 if parsed.path == _FEED else min(manifest.max_items, 30)
            if attempts[parsed.path] > maximum:
                raise _failure()
            request_seen = True
        if sent:
            await asyncio.sleep(manifest.request_delay_seconds or 0)
        sent = True
        return await original_request(method=method, url=url, **kwargs)

    async def get(path: str, params: dict[str, str]) -> Any:
        nonlocal expected_path, expected_query, request_seen
        expected_path, expected_query, request_seen = path, params.copy(), False
        result = await client.get(path, params.copy())
        if not request_seen:
            raise _failure()
        return result

    client.request, client.get_wbi_keys = guarded_request, cached_keys
    try:
        unit = BiliDynamicUnit(state, manifest.max_items)
        snapshots = BiliDynamicSnapshotStore(
            manifest.account_root,
            account_id=manifest.account_id,
            author_fingerprint_sha256=manifest.author_remote_id_fingerprint_sha256,
            upstream_sha=manifest.upstream_sha,
            creator_id=creator_id,
        )
        while (action := unit.next_action()).kind != "stop":
            if action.kind == "list":
                if action.offset is None:
                    raise _failure()
                response = await get(
                    _FEED,
                    {
                        "offset": action.offset,
                        "host_mid": str(creator_id),
                        "platform": "web",
                        "features": _FEATURES,
                    },
                )
                unit.observe_page(snapshots.persist(offset=action.offset, data=response))
            elif action.kind == "load":
                if action.snapshot is None:
                    raise _failure()
                unit.observe_page(snapshots.load(action.snapshot))
            elif action.kind == "detail":
                identity = action.identity
                if identity is None:
                    raise _failure()
                response = await get(
                    _DYNAMIC,
                    {
                        "id": identity.did,
                        "timezone_offset": "-480",
                        "platform": "web",
                        "gaia_source": "main_web",
                        "features": _FEATURES,
                    },
                )
                if not isinstance(response, dict) or not isinstance(response.get("item"), dict):
                    raise _failure()
                item = response["item"]
                # Validate authority before any optional follow-up endpoint.
                if parse_dynamic_identity(item, creator_id) != identity:
                    raise BiliDynamicIdentityError
                modules = item.get("modules")
                if not isinstance(modules, dict):
                    raise _failure()
                dynamic = modules.get("module_dynamic")
                if not isinstance(dynamic, dict):
                    raise _failure()
                major = dynamic.get("major")
                opus_item = None
                if isinstance(major, dict) and major.get("type") == "MAJOR_TYPE_OPUS":
                    if (
                        identity.dynamic_type not in {"DYNAMIC_TYPE_WORD", "DYNAMIC_TYPE_DRAW"}
                        or item.get("orig") is not None
                        or item.get("visible") is not True
                        or dynamic.get("additional") is not None
                    ):
                        raise BiliDynamicUnsupportedError
                    if (
                        not isinstance(client.cookie_dict, dict)
                        or type(client.cookie_dict.get("buvid3")) is not str
                        or not client.cookie_dict["buvid3"]
                    ):
                        raise _failure()
                    opus = await get(_OPUS, {"id": identity.did, "features": _OPUS_FEATURES})
                    if not isinstance(opus, dict) or not isinstance(opus.get("item"), dict):
                        raise _failure()
                    opus_item = opus["item"]
                payload = parse_bili_dynamic_detail(
                    item,
                    creator_id=creator_id,
                    expected_identity=identity,
                    opus_item=opus_item,
                )
                video_identity = None
                if payload.video_reference is not None:
                    reference = payload.video_reference
                    expected_path = "/x/web-interface/view/detail"
                    expected_query, request_seen = {"bvid": reference.bvid}, False
                    detail = await client.get_video_info(bvid=reference.bvid)
                    if not request_seen or not isinstance(detail, dict) or not isinstance(detail.get("View"), dict):
                        raise _failure()
                    video_identity = BiliIdentity(reference.aid, reference.bvid, detail["View"].get("pubdate"))
                    try:
                        validate_bili_upload_detail(detail, identity=video_identity, creator_id=creator_id)
                    except RuntimeError:
                        raise BiliDynamicIdentityError from None
                    previous = videos.get(reference.aid)
                    if previous is not None and previous != video_identity:
                        raise _failure()
                    if previous is None:
                        await store_video(detail, video_identity)
                        videos[reference.aid] = video_identity
                records.append(payload.to_record())
                unit.consume(identity, video_identity=video_identity)
            else:
                raise _failure()
        coverage = unit.coverage()
        coverage.validate(state, manifest.max_items)
        output = manifest.output_root / "media-sync-dynamics.jsonl"
        if manifest.output_root.is_symlink() or output.is_symlink():
            raise _failure()
        if records:
            with output.open("x", encoding="utf-8", newline="\n") as stream:
                for record in records:
                    stream.write(json.dumps(record, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n")
        return coverage
    except BiliDynamicError:
        raise
    except ValueError:
        # The pure multifeed/snapshot validators use ValueError. Keep fixed
        # dynamic diagnostics, without leaking response bodies or file paths.
        raise _failure() from None
    finally:
        client.request, client.get_wbi_keys = original_request, original_keys
