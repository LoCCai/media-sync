"""Exact platform-specific profile identities; no aliases or URL normalization."""

from __future__ import annotations

import re

from media_sync.domain import Platform

CREATOR_PROFILE_PLATFORMS = frozenset(
    {Platform.BILI, Platform.WB, Platform.KS, Platform.ZHIHU, Platform.DY, Platform.TIEBA}
)
_NUMERIC = re.compile(r"[1-9][0-9]{0,19}\Z", re.ASCII)
_KUAISHOU = re.compile(r"[A-Za-z0-9_-]{1,128}\Z", re.ASCII)
_DOUYIN = re.compile(r"[A-Za-z0-9_-]{1,255}\Z", re.ASCII)
_TIEBA = re.compile(r"tb\.1\.[A-Za-z0-9._-]{28,31}\Z", re.ASCII)
_TOKEN = re.compile(r"[A-Za-z0-9._-]{1,255}\Z", re.ASCII)
_HOMEPAGES = {
    Platform.BILI: "https://space.bilibili.com/",
    Platform.WB: "https://weibo.com/u/",
    Platform.KS: "https://www.kuaishou.com/profile/",
    Platform.ZHIHU: "https://www.zhihu.com/people/",
    Platform.DY: "https://www.douyin.com/user/",
    Platform.TIEBA: "https://tieba.baidu.com/home/main?id=",
}


def profile_identifier(value: object) -> str:
    """Bound the transport value only; enclosing request/result supplies authority."""
    if type(value) is not str or _TOKEN.fullmatch(value) is None or value in {".", ".."}:
        raise ValueError("creator_profile_identity_invalid")
    return value


def validate_creator_profile_id(platform: Platform | str, value: object) -> str:
    try:
        selected = Platform(platform)
    except (TypeError, ValueError):
        raise ValueError("creator_profile_unsupported") from None
    if selected not in CREATOR_PROFILE_PLATFORMS:
        raise ValueError("creator_profile_unsupported")
    remote_id = profile_identifier(value)
    if selected in {Platform.BILI, Platform.WB}:
        if _NUMERIC.fullmatch(remote_id) is None or int(remote_id) > 2**64 - 1:
            raise ValueError("creator_profile_identity_invalid")
    elif (
        (selected is Platform.KS and _KUAISHOU.fullmatch(remote_id) is None)
        or (selected is Platform.DY and _DOUYIN.fullmatch(remote_id) is None)
        or (
            selected is Platform.TIEBA
            and (_TIEBA.fullmatch(remote_id) is None or ".." in remote_id or remote_id.endswith("."))
        )
    ):
        raise ValueError("creator_profile_identity_invalid")
    return remote_id


def profile_homepage(platform: Platform | str, value: object) -> str:
    remote_id = validate_creator_profile_id(platform, value)
    return _HOMEPAGES[Platform(platform)] + remote_id
