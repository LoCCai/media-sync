from __future__ import annotations

from uuid import uuid4

import pytest

from media_sync.domain import Platform
from media_sync.infrastructure.db.creator_profile_repository import (
    CreatorProfileError,
    ProfileValue,
    creator_profile_homepage,
)
from media_sync.integrations.mediacrawler.creator_profile_identity import profile_homepage, validate_creator_profile_id
from media_sync.integrations.mediacrawler.creator_profile_runner import (
    MediaCrawlerCreatorProfile,
    MediaCrawlerCreatorProfileRequest,
    MediaCrawlerCreatorProfileResult,
    MediaCrawlerCreatorProfileStatus,
)


@pytest.mark.parametrize(
    "platform,remote_id,homepage",
    [
        (Platform.BILI, "18446744073709551615", "https://space.bilibili.com/18446744073709551615"),
        (Platform.WB, "123", "https://weibo.com/u/123"),
        (Platform.KS, "3xSynthetic_ID-9", "https://www.kuaishou.com/profile/3xSynthetic_ID-9"),
        (Platform.ZHIHU, "test.user-token_9", "https://www.zhihu.com/people/test.user-token_9"),
    ],
)
def test_exact_platform_identity_survives_all_boundaries(platform: Platform, remote_id: str, homepage: str) -> None:
    request = MediaCrawlerCreatorProfileRequest(uuid4(), platform, remote_id, uuid4())
    profile = MediaCrawlerCreatorProfile(remote_id, "平台原始昵称", None)
    result = MediaCrawlerCreatorProfileResult(
        MediaCrawlerCreatorProfileStatus.SUCCEEDED,
        request.account_id,
        platform,
        remote_id,
        request.request_id,
        "a" * 40,
        profile,
    )
    assert result.profile is profile
    assert validate_creator_profile_id(platform, remote_id) == remote_id
    assert profile_homepage(platform, remote_id) == creator_profile_homepage(platform.value, remote_id) == homepage
    ProfileValue(platform.value, remote_id, profile.display_name, homepage, "a" * 40).validate()
    with pytest.raises(ValueError, match="creator_profile_result_invalid"):
        MediaCrawlerCreatorProfileResult(
            MediaCrawlerCreatorProfileStatus.SUCCEEDED,
            request.account_id,
            platform,
            remote_id,
            request.request_id,
            "a" * 40,
            MediaCrawlerCreatorProfile("other", "other", None),
        )


@pytest.mark.parametrize("platform", [Platform.KS, Platform.ZHIHU])
@pytest.mark.parametrize(
    "value", ["", ".", "..", "a/b", "a%2fb", "a?x=1", "a#x", "a\\b", " a", "a\n", "中文", 123, True, None]
)
def test_opaque_identity_never_normalizes_urls_or_path_segments(platform: Platform, value: object) -> None:
    with pytest.raises(ValueError, match="creator_profile_identity_invalid"):
        MediaCrawlerCreatorProfileRequest(uuid4(), platform, value, uuid4())
    with pytest.raises(CreatorProfileError, match="creator_profile_identity_mismatch"):
        creator_profile_homepage(platform.value, value)


@pytest.mark.parametrize(
    "platform,value", [(Platform.KS, "a.b"), (Platform.KS, "a" * 129), (Platform.ZHIHU, "a" * 256)]
)
def test_opaque_platform_shapes_are_not_interchangeable(platform: Platform, value: str) -> None:
    with pytest.raises(ValueError):
        validate_creator_profile_id(platform, value)


@pytest.mark.parametrize("platform", [Platform.BILI, Platform.WB])
@pytest.mark.parametrize("value", ["0", "0123", "3xOpaque", "name-token", "18446744073709551616"])
def test_opaque_support_never_weakens_numeric_result_authority(platform: Platform, value: str) -> None:
    # A platform-agnostic DTO is only a bounded transport object, not authority.
    profile = MediaCrawlerCreatorProfile(value, "Name", None)
    with pytest.raises(ValueError, match="creator_profile_identity_invalid"):
        MediaCrawlerCreatorProfileResult(
            MediaCrawlerCreatorProfileStatus.SUCCEEDED,
            uuid4(),
            platform,
            value,
            uuid4(),
            "a" * 40,
            profile,
        )
