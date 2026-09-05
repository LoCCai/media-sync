"""Versioned, redaction-safe MediaCrawler platform capabilities."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Literal

from media_sync.domain import LoginMethod, Platform

from .policies import FULL_HISTORY_PLATFORMS

CAPABILITY_SCHEMA_VERSION: Final = 1
CREATOR_STABLE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9._-]{1,255}\Z", re.ASCII)

_LOGIN_METHODS: Final = (
    LoginMethod.QR,
    LoginMethod.COOKIE,
    LoginMethod.SAVED_SESSION,
)
_SAFE_CODE = re.compile(r"[a-z0-9_]{1,64}\Z", re.ASCII)


class MediaCrawlerCapabilityError(ValueError):
    """A capability lookup or creator identity is outside the closed contract."""


class CreatorInputKind(StrEnum):
    """Stable, non-secret creator identifiers requested by the workbench."""

    PROFILE_ID = "profile_id"
    SEC_USER_ID = "sec_user_id"
    USER_ID = "user_id"
    UID = "uid"
    PORTRAIT_ID = "portrait_id"
    URL_TOKEN = "url_token"


def normalize_creator_stable_id(value: str) -> str:
    """Return one conservative stable creator ID without disclosing bad input."""

    if not isinstance(value, str):
        raise MediaCrawlerCapabilityError("creator ID must be a stable non-secret identifier")
    normalized = value.strip()
    if CREATOR_STABLE_ID_PATTERN.fullmatch(normalized) is None:
        raise MediaCrawlerCapabilityError("creator ID must be a stable non-secret identifier")
    return normalized


def _bounded_text(value: str, *, name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise MediaCrawlerCapabilityError(f"{name} must be text")
    if value != value.strip() or not value or len(value) > maximum:
        raise MediaCrawlerCapabilityError(f"{name} is outside the capability contract")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise MediaCrawlerCapabilityError(f"{name} is outside the capability contract")
    return value


def _bounded_codes(values: tuple[str, ...], *, name: str) -> tuple[str, ...]:
    normalized = tuple(values)
    if not 1 <= len(normalized) <= 16 or len(normalized) != len(set(normalized)):
        raise MediaCrawlerCapabilityError(f"{name} is outside the capability contract")
    if any(_SAFE_CODE.fullmatch(value) is None for value in normalized):
        raise MediaCrawlerCapabilityError(f"{name} is outside the capability contract")
    return normalized


def _bounded_limitations(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(values)
    if not 1 <= len(normalized) <= 8 or len(normalized) != len(set(normalized)):
        raise MediaCrawlerCapabilityError("limitations are outside the capability contract")
    for value in normalized:
        _bounded_text(value, name="limitation", maximum=240)
    return normalized


@dataclass(frozen=True, slots=True)
class CreatorInputCapability:
    """Display guidance for a stable creator identifier and optional authority."""

    kind: CreatorInputKind
    label: str
    placeholder: str
    examples: tuple[str, ...]
    allows_secret_reference: bool

    def __post_init__(self) -> None:
        try:
            kind = CreatorInputKind(self.kind)
        except (TypeError, ValueError) as error:
            raise MediaCrawlerCapabilityError("unsupported creator input kind") from error
        label = _bounded_text(self.label, name="creator input label", maximum=80)
        placeholder = _bounded_text(self.placeholder, name="creator input placeholder", maximum=120)
        examples = tuple(self.examples)
        if not 1 <= len(examples) <= 3 or len(examples) != len(set(examples)):
            raise MediaCrawlerCapabilityError("creator input examples are outside the capability contract")
        for example in examples:
            if normalize_creator_stable_id(example) != example:
                raise MediaCrawlerCapabilityError("creator input examples must be canonical stable IDs")
        if type(self.allows_secret_reference) is not bool:
            raise MediaCrawlerCapabilityError("allows_secret_reference must be boolean")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "placeholder", placeholder)
        object.__setattr__(self, "examples", examples)

    def to_payload(self) -> dict[str, object]:
        """Return a fresh JSON-compatible creator-input description."""

        return {
            "kind": self.kind.value,
            "label": self.label,
            "placeholder": self.placeholder,
            "examples": list(self.examples),
            "allows_secret_reference": self.allows_secret_reference,
        }


@dataclass(frozen=True, slots=True)
class MediaCrawlerPlatformCapability:
    """One immutable capability for new scheduled requests, not legacy artifacts."""

    platform: Platform
    display_name: str
    login_methods: tuple[LoginMethod, ...]
    qr_login: bool
    creator_input: CreatorInputCapability
    requires_full_history_acknowledgement: bool
    offline_shapes: tuple[str, ...]
    limitations: tuple[str, ...]
    live_qualification: Literal["NOT_RUN"] = "NOT_RUN"

    def __post_init__(self) -> None:
        try:
            platform = Platform(self.platform)
            login_methods = tuple(LoginMethod(method) for method in self.login_methods)
        except (TypeError, ValueError) as error:
            raise MediaCrawlerCapabilityError("unsupported MediaCrawler platform capability") from error
        if login_methods != _LOGIN_METHODS:
            raise MediaCrawlerCapabilityError("login methods must use the closed MediaCrawler order")
        if type(self.qr_login) is not bool or self.qr_login is not (LoginMethod.QR in login_methods):
            raise MediaCrawlerCapabilityError("qr_login must match the closed login methods")
        if not isinstance(self.creator_input, CreatorInputCapability):
            raise MediaCrawlerCapabilityError("creator_input must use the typed capability contract")
        if type(self.requires_full_history_acknowledgement) is not bool:
            raise MediaCrawlerCapabilityError("requires_full_history_acknowledgement must be boolean")
        if self.requires_full_history_acknowledgement is not _new_request_requires_full_history(platform):
            raise MediaCrawlerCapabilityError("full-history acknowledgement must match the new-request policy")
        if self.live_qualification != "NOT_RUN":
            raise MediaCrawlerCapabilityError("live qualification has not been established")
        object.__setattr__(self, "platform", platform)
        object.__setattr__(self, "display_name", _bounded_text(self.display_name, name="display name", maximum=40))
        object.__setattr__(self, "login_methods", login_methods)
        object.__setattr__(self, "offline_shapes", _bounded_codes(self.offline_shapes, name="offline shapes"))
        object.__setattr__(self, "limitations", _bounded_limitations(self.limitations))

    def to_payload(self) -> dict[str, object]:
        """Return a fresh JSON-compatible row containing no runtime data."""

        return {
            "platform": self.platform.value,
            "display_name": self.display_name,
            "login_methods": [method.value for method in self.login_methods],
            "qr_login": self.qr_login,
            "pasted_cookie_login": self.platform in {Platform.BILI, Platform.WB, Platform.XHS, Platform.ZHIHU},
            "creator_input": self.creator_input.to_payload(),
            "requires_full_history_acknowledgement": self.requires_full_history_acknowledgement,
            "bounded_capture": bounded_capture_payload(self.platform),
            "offline_shapes": list(self.offline_shapes),
            "limitations": list(self.limitations),
            "live_qualification": self.live_qualification,
        }


def _creator_input(
    kind: CreatorInputKind,
    label: str,
    placeholder: str,
    *examples: str,
    allows_secret_reference: bool = False,
) -> CreatorInputCapability:
    return CreatorInputCapability(
        kind=kind,
        label=label,
        placeholder=placeholder,
        examples=examples,
        allows_secret_reference=allows_secret_reference,
    )


def _new_request_requires_full_history(platform: Platform) -> bool:
    # The legacy bridge classification deliberately still includes Bili. Only
    # newly constructed requests carry its owned versioned bounded contract.
    return platform in FULL_HISTORY_PLATFORMS and platform is not Platform.BILI


def bounded_capture_payload(platform: Platform) -> dict[str, object] | None:
    """Return fixed budgets for the new Bili upload path, never live evidence."""

    if platform is not Platform.BILI:
        return None
    return {
        "version": 1,
        "feed": "ordinary_uploads",
        "order": "pubdate",
        "page_size": 30,
        "max_items_per_unit": 30,
        "max_list_attempts_per_unit": 2,
        "alternating_lanes": ["head", "history"],
        "browser_setup_separate": True,
        "download_scope_bounded": False,
        "history_completeness_claimed": False,
        "legacy_requires_full_history_acknowledgement": True,
    }


def _capability(
    platform: Platform,
    display_name: str,
    creator_input: CreatorInputCapability,
    offline_shapes: tuple[str, ...],
    limitations: tuple[str, ...],
) -> MediaCrawlerPlatformCapability:
    return MediaCrawlerPlatformCapability(
        platform=platform,
        display_name=display_name,
        login_methods=_LOGIN_METHODS,
        qr_login=True,
        creator_input=creator_input,
        requires_full_history_acknowledgement=_new_request_requires_full_history(platform),
        offline_shapes=offline_shapes,
        limitations=limitations,
    )


_LIVE_LIMITATION = "Live login, creator crawl, CDN retrieval, and media-server playback remain unqualified."

MEDIACRAWLER_PLATFORM_CAPABILITIES: Final = (
    _capability(
        Platform.XHS,
        "小红书",
        _creator_input(
            CreatorInputKind.PROFILE_ID,
            "创作者主页 ID",
            "输入稳定的主页 ID",
            "5f1234567890abcdef123456",
            allows_secret_reference=True,
        ),
        (
            "static_image_note",
            "video_note",
            "multi_video_note",
            "live_photo",
            "live_photo_gallery",
        ),
        (
            "Animated notes, authority-expiry recovery, and broader mixed-media shapes remain unsupported.",
            _LIVE_LIMITATION,
        ),
    ),
    _capability(
        Platform.DY,
        "抖音",
        _creator_input(
            CreatorInputKind.SEC_USER_ID,
            "创作者 sec_user_id",
            "输入稳定的 sec_user_id",
            "creator_123",
        ),
        ("single_video", "image_gallery"),
        (
            "Creator pagination may scan full history and requires explicit acknowledgement.",
            "Mixed video-image semantics and associated gallery music remain unsupported.",
            _LIVE_LIMITATION,
        ),
    ),
    _capability(
        Platform.KS,
        "快手",
        _creator_input(
            CreatorInputKind.USER_ID,
            "创作者用户 ID",
            "输入稳定的用户 ID",
            "creator_123",
        ),
        ("single_video", "atlas_gallery"),
        (
            "Creator pagination may scan full history and requires explicit acknowledgement.",
            "Mixed video-image semantics and animated atlas media remain unsupported.",
            _LIVE_LIMITATION,
        ),
    ),
    _capability(
        Platform.BILI,
        "哔哩哔哩",
        _creator_input(
            CreatorInputKind.UID,
            "创作者 UID (建议纯数字)",
            "例如 123456",
            "123456",
        ),
        (
            "cover_image",
            "progressive_video",
            "dash_video",
            "single_segment_flv_remux",
            "multi_segment_progressive_concat",
            "multi_segment_flv_concat",
        ),
        (
            "New upload units consume at most min(max_items, 30) verified details and two list HTTP attempts.",
            "Browser/auth setup and up to two WBI key reads are separate; this is not a download or full-history cap.",
            "Default scope remains uploads; explicit v2 dynamics/both supports WORD/DRAW/OPUS and owned AV references.",
            "Dynamics require max_items >= 2; discovery pages can commit zero records. "
            "Reposts and unknown components fail closed.",
            "Legacy artifacts remain gated by full-history acknowledgement. Numeric UIDs are recommended.",
            "Transcoding, pages above 64, paid, bangumi, and live media remain unsupported.",
            _LIVE_LIMITATION,
        ),
    ),
    _capability(
        Platform.WB,
        "微博",
        _creator_input(
            CreatorInputKind.USER_ID,
            "创作者用户 ID (建议纯数字)",
            "例如 123456",
            "123456",
        ),
        (
            "static_image_gallery",
            "original_video",
            "video_poster",
            "playback_list_quality_selection",
        ),
        (
            "Creator pagination may scan full history and requires explicit acknowledgement.",
            "Numeric user IDs are recommended; compatible stable IDs remain accepted.",
            "Retweets, animated images, paid media, and live media remain unsupported.",
            _LIVE_LIMITATION,
        ),
    ),
    _capability(
        Platform.TIEBA,
        "贴吧",
        _creator_input(
            CreatorInputKind.PORTRAIT_ID,
            "作者 portrait ID",
            "输入稳定的 portrait ID",
            "author_123",
        ),
        ("first_floor_article_image_gallery",),
        (
            "Only ordinary first-floor article galleries with 1 to 64 static images are qualified offline.",
            "Mixed, rich, reply, and larger-gallery media remain unsupported.",
            _LIVE_LIMITATION,
        ),
    ),
    _capability(
        Platform.ZHIHU,
        "知乎",
        _creator_input(
            CreatorInputKind.URL_TOKEN,
            "创作者主页标识",
            "输入稳定的主页标识",
            "sample-author",
        ),
        ("answer_image_gallery",),
        (
            "Only answer galleries with 1 to 64 static images are qualified offline.",
            "Articles, playable video, animation, and richer embedded media remain unsupported.",
            _LIVE_LIMITATION,
        ),
    ),
)

_CAPABILITY_BY_PLATFORM = MappingProxyType(
    {capability.platform: capability for capability in MEDIACRAWLER_PLATFORM_CAPABILITIES}
)

if tuple(_CAPABILITY_BY_PLATFORM) != tuple(Platform):
    raise RuntimeError("MediaCrawler capability order must cover every platform exactly once")


def capability_for(platform: Platform) -> MediaCrawlerPlatformCapability:
    """Return the immutable capability for one supported platform."""

    try:
        normalized = Platform(platform)
        return _CAPABILITY_BY_PLATFORM[normalized]
    except (TypeError, ValueError, KeyError) as error:
        raise MediaCrawlerCapabilityError("unsupported MediaCrawler platform capability") from error


def platform_capabilities_payload() -> dict[str, object]:
    """Return a fresh, bounded and versioned public capability payload."""

    return {
        "version": CAPABILITY_SCHEMA_VERSION,
        "platforms": [capability.to_payload() for capability in MEDIACRAWLER_PLATFORM_CAPABILITIES],
    }


__all__ = [
    "CAPABILITY_SCHEMA_VERSION",
    "CREATOR_STABLE_ID_PATTERN",
    "MEDIACRAWLER_PLATFORM_CAPABILITIES",
    "CreatorInputCapability",
    "CreatorInputKind",
    "MediaCrawlerCapabilityError",
    "MediaCrawlerPlatformCapability",
    "bounded_capture_payload",
    "capability_for",
    "normalize_creator_stable_id",
    "platform_capabilities_payload",
]
