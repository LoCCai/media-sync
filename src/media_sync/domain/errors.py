"""A small, stable error vocabulary for domain and adapter boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from types import MappingProxyType


class DomainError(Exception):
    """Base class for expected, classifiable media-sync failures."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        context: Mapping[str, object] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.context = MappingProxyType(dict(context or {}))
        super().__init__(f"{code}: {message}")


class DomainValidationError(DomainError):
    """Raised when a domain value object violates an invariant."""

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        context: Mapping[str, object] | None = None,
    ) -> None:
        details = dict(context or {})
        if field is not None:
            details["field"] = field
        super().__init__("domain_validation", message, context=details)
        self.field = field


class AdapterError(DomainError):
    """Base class with machine-readable worker scheduling attributes."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        platform: str,
        retryable: bool,
        requires_auth: bool = False,
        requires_interaction: bool = False,
        retry_after: int | float | timedelta | None = None,
        context: Mapping[str, object] | None = None,
    ) -> None:
        normalized_platform = platform.strip()
        if not normalized_platform:
            raise DomainValidationError("platform must not be blank", field="platform")
        if isinstance(retry_after, timedelta):
            normalized_retry_after = retry_after.total_seconds()
        elif retry_after is None:
            normalized_retry_after = None
        elif isinstance(retry_after, bool):
            raise DomainValidationError("retry_after must be a number of seconds", field="retry_after")
        else:
            normalized_retry_after = float(retry_after)
        if normalized_retry_after is not None and normalized_retry_after < 0:
            raise DomainValidationError("retry_after must be non-negative", field="retry_after")

        details = dict(context or {})
        details.update(
            {
                "platform": normalized_platform,
                "retryable": retryable,
                "requires_auth": requires_auth,
                "requires_interaction": requires_interaction,
            }
        )
        if normalized_retry_after is not None:
            details["retry_after"] = normalized_retry_after
        super().__init__(code, message, context=details)
        self.platform = normalized_platform
        self.retryable = retryable
        self.requires_auth = requires_auth
        self.requires_interaction = requires_interaction
        self.retry_after = normalized_retry_after


class AuthExpiredError(AdapterError):
    """The stored platform session is no longer authenticated."""

    def __init__(self, platform: str, message: str = "authentication session expired") -> None:
        super().__init__(
            "auth_expired",
            message,
            platform=platform,
            retryable=False,
            requires_auth=True,
        )


class InteractiveChallengeRequiredError(AdapterError):
    """A human must complete a QR, CAPTCHA or equivalent challenge."""

    def __init__(
        self,
        platform: str,
        challenge: str = "interactive challenge",
    ) -> None:
        super().__init__(
            "interactive_challenge_required",
            f"{challenge} requires user interaction",
            platform=platform,
            retryable=False,
            requires_interaction=True,
            context={"challenge": challenge},
        )
        self.challenge = challenge


class RateLimitedError(AdapterError):
    """The upstream asks the worker to back off before retrying."""

    def __init__(
        self,
        platform: str,
        retry_after: int | float | timedelta | None = None,
        message: str = "upstream rate limit reached",
    ) -> None:
        super().__init__(
            "rate_limited",
            message,
            platform=platform,
            retryable=True,
            retry_after=retry_after,
        )


class TemporaryUpstreamError(AdapterError):
    """A transient upstream failure suitable for bounded retry."""

    def __init__(self, platform: str, message: str = "temporary upstream failure") -> None:
        super().__init__(
            "temporary_upstream",
            message,
            platform=platform,
            retryable=True,
        )


class PermanentUpstreamError(AdapterError):
    """An upstream rejection that should not be automatically retried."""

    def __init__(self, platform: str, message: str = "permanent upstream failure") -> None:
        super().__init__(
            "permanent_upstream",
            message,
            platform=platform,
            retryable=False,
        )


class ContentNotFoundError(AdapterError):
    """The requested content no longer exists or is not visible."""

    def __init__(self, platform: str, remote_id: str) -> None:
        normalized_remote_id = remote_id.strip()
        if not normalized_remote_id:
            raise DomainValidationError("remote_id must not be blank", field="remote_id")
        super().__init__(
            "content_not_found",
            f"content {normalized_remote_id!r} was not found",
            platform=platform,
            retryable=False,
            context={"remote_id": normalized_remote_id},
        )
        self.remote_id = normalized_remote_id


class UpstreamSchemaChangedError(AdapterError):
    """An upstream payload no longer satisfies the qualified adapter schema."""

    def __init__(self, platform: str, detail: str = "upstream response schema changed") -> None:
        super().__init__(
            "upstream_schema_changed",
            detail,
            platform=platform,
            retryable=False,
        )


class InvalidStateTransitionError(DomainError):
    """Raised when an entity is asked to make an illegal state transition."""

    def __init__(self, entity: str, current: str, target: str) -> None:
        super().__init__(
            "invalid_state_transition",
            f"{entity} cannot transition from {current!r} to {target!r}",
            context={"entity": entity, "current": current, "target": target},
        )
        self.entity = entity
        self.current = current
        self.target = target


class UnsupportedCapabilityError(DomainError):
    """Raised before work starts when an adapter lacks a requested capability."""

    def __init__(self, platform: str, capability: str) -> None:
        super().__init__(
            "unsupported_capability",
            f"platform {platform!r} does not support {capability!r}",
            context={"platform": platform, "capability": capability},
        )
        self.platform = platform
        self.capability = capability


class EntityNotFoundError(DomainError):
    """Raised when a referenced domain entity is not available."""

    def __init__(self, entity: str, reference: str) -> None:
        super().__init__(
            "entity_not_found",
            f"{entity} {reference!r} was not found",
            context={"entity": entity, "reference": reference},
        )
        self.entity = entity
        self.reference = reference


__all__ = [
    "AdapterError",
    "AuthExpiredError",
    "ContentNotFoundError",
    "DomainError",
    "DomainValidationError",
    "EntityNotFoundError",
    "InteractiveChallengeRequiredError",
    "InvalidStateTransitionError",
    "PermanentUpstreamError",
    "RateLimitedError",
    "TemporaryUpstreamError",
    "UnsupportedCapabilityError",
    "UpstreamSchemaChangedError",
]
