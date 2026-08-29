"""Framework-independent enumerations used by the media-sync domain."""

from enum import StrEnum


class Platform(StrEnum):
    """Stable platform codes used in persistence and public contracts."""

    XHS = "xhs"
    DY = "dy"
    KS = "ks"
    BILI = "bili"
    WB = "wb"
    TIEBA = "tieba"
    ZHIHU = "zhihu"


class LoginMethod(StrEnum):
    """Authentication methods an adapter may qualify and expose."""

    QR = "qr"
    COOKIE = "cookie"
    SAVED_SESSION = "saved_session"
    PHONE = "phone"


class CreatorReferenceKind(StrEnum):
    """Creator reference forms understood by an adapter."""

    REMOTE_ID = "remote_id"
    PROFILE_URL = "profile_url"


class ContentKind(StrEnum):
    """Normalized creator-content kinds."""

    VIDEO = "video"
    IMAGE = "image"
    GALLERY = "gallery"
    TEXT = "text"
    ARTICLE = "article"
    AUDIO = "audio"
    DYNAMIC = "dynamic"
    MIXED = "mixed"


class AssetKind(StrEnum):
    """Normalized downloadable or exportable asset kinds."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    SUBTITLE = "subtitle"
    COVER = "cover"
    AVATAR = "avatar"
    ATTACHMENT = "attachment"


class AuthStatus(StrEnum):
    """Observable authentication/session state."""

    UNKNOWN = "unknown"
    REQUIRED = "required"
    AUTHENTICATING = "authenticating"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    FAILED = "failed"


class AssetStatus(StrEnum):
    """Lifecycle state for a discovered asset."""

    DISCOVERED = "discovered"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    VERIFIED = "verified"
    EXPORTED = "exported"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_TERMINAL = "failed_terminal"


class RunStatus(StrEnum):
    """Durable state of one subscription synchronization run."""

    QUEUED = "queued"
    CLAIMED = "claimed"
    AWAITING_AUTH = "awaiting_auth"
    RUNNING = "running"
    INGESTING = "ingesting"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_TERMINAL = "failed_terminal"
    CANCELLED = "cancelled"


class JobStatus(StrEnum):
    """Durable state of a general background job."""

    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    WAITING_AUTH = "waiting_auth"
    WAITING_USER = "waiting_user"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_TERMINAL = "failed_terminal"
    CANCELLED = "cancelled"


# Product language uses both "task" and "job" for this state machine. Keep one
# enum identity so persistence cannot accidentally store two vocabularies.
TaskStatus = JobStatus


__all__ = [
    "AssetKind",
    "AssetStatus",
    "AuthStatus",
    "ContentKind",
    "CreatorReferenceKind",
    "JobStatus",
    "LoginMethod",
    "Platform",
    "RunStatus",
    "TaskStatus",
]
