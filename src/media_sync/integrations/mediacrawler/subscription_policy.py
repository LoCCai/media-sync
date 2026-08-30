"""Closed, durable subscription policy for scheduled MediaCrawler runs."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

from media_sync.security import InvalidSecretReferenceError, SecretReference

SUBSCRIPTION_POLICY_SCHEMA_VERSION: Final = 1
MAX_REQUEST_DELAY_SECONDS: Final = 300.0


class MediaCrawlerSubscriptionPolicyError(ValueError):
    """A durable MediaCrawler subscription policy is malformed or unsafe."""


def _creator_secret_reference(value: object) -> str:
    if not isinstance(value, str):
        raise MediaCrawlerSubscriptionPolicyError("creator secret_ref must be an opaque secret reference")
    try:
        reference = SecretReference.parse(value)
    except InvalidSecretReferenceError:
        raise MediaCrawlerSubscriptionPolicyError("creator secret_ref must be an opaque secret reference") from None
    serialized = reference.serialize()
    if value != serialized:
        raise MediaCrawlerSubscriptionPolicyError("creator secret_ref must use its canonical serialized form")
    return serialized


def _request_delay(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise MediaCrawlerSubscriptionPolicyError("request_delay_seconds must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0 < normalized <= MAX_REQUEST_DELAY_SECONDS:
        raise MediaCrawlerSubscriptionPolicyError(
            f"request_delay_seconds must be greater than zero and at most {MAX_REQUEST_DELAY_SECONDS:g}"
        )
    return normalized


def _boolean(value: object, *, name: str) -> bool:
    if type(value) is not bool:
        raise MediaCrawlerSubscriptionPolicyError(f"{name} must be boolean")
    return value


@dataclass(frozen=True, slots=True)
class MediaCrawlerSubscriptionPolicy:
    """Closed v1 controls persisted inside ``Subscription.policy.mediacrawler``."""

    allow_full_history: bool
    request_delay_seconds: float
    headless: bool
    creator_secret_ref: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if type(self.allow_full_history) is not bool:
            raise MediaCrawlerSubscriptionPolicyError("allow_full_history must be boolean")
        if type(self.headless) is not bool:
            raise MediaCrawlerSubscriptionPolicyError("headless must be boolean")
        object.__setattr__(self, "request_delay_seconds", _request_delay(self.request_delay_seconds))
        if self.creator_secret_ref is not None:
            object.__setattr__(
                self,
                "creator_secret_ref",
                _creator_secret_reference(self.creator_secret_ref),
            )

    def to_payload(self) -> dict[str, object]:
        """Return the exact JSON-compatible v1 MediaCrawler region."""

        payload: dict[str, object] = {
            "schema_version": SUBSCRIPTION_POLICY_SCHEMA_VERSION,
            "allow_full_history": self.allow_full_history,
            "request_delay_seconds": self.request_delay_seconds,
            "headless": self.headless,
        }
        if self.creator_secret_ref is not None:
            payload["creator_input"] = {"secret_ref": self.creator_secret_ref}
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> MediaCrawlerSubscriptionPolicy:
        """Validate one exact ``mediacrawler`` region without legacy fallback."""

        if not isinstance(payload, Mapping):
            raise MediaCrawlerSubscriptionPolicyError("MediaCrawler policy must be an object")
        required = {
            "schema_version",
            "allow_full_history",
            "request_delay_seconds",
            "headless",
        }
        supplied = set(payload)
        if supplied not in (required, required | {"creator_input"}):
            raise MediaCrawlerSubscriptionPolicyError("MediaCrawler policy is not closed schema v1")
        schema_version = payload.get("schema_version")
        if type(schema_version) is not int or schema_version != SUBSCRIPTION_POLICY_SCHEMA_VERSION:
            raise MediaCrawlerSubscriptionPolicyError("MediaCrawler policy is not closed schema v1")

        creator_secret_ref: str | None = None
        if "creator_input" in payload:
            creator_input = payload.get("creator_input")
            if not isinstance(creator_input, Mapping) or set(creator_input) != {"secret_ref"}:
                raise MediaCrawlerSubscriptionPolicyError("creator_input must contain only an opaque secret_ref")
            creator_secret_ref = _creator_secret_reference(creator_input.get("secret_ref"))

        return cls(
            allow_full_history=_boolean(payload.get("allow_full_history"), name="allow_full_history"),
            request_delay_seconds=_request_delay(payload.get("request_delay_seconds")),
            headless=_boolean(payload.get("headless"), name="headless"),
            creator_secret_ref=creator_secret_ref,
        )


def from_subscription_policy(
    subscription_policy: Mapping[str, object],
    *,
    allow_other_adapter_regions: bool = False,
) -> MediaCrawlerSubscriptionPolicy:
    """Read only the MediaCrawler region from an outer ``Subscription.policy``.

    By default the outer object is closed too. A caller that owns a shared
    adapter-policy document may explicitly retain other regions; their values
    are deliberately neither inspected nor copied here.
    """

    if not isinstance(subscription_policy, Mapping):
        raise MediaCrawlerSubscriptionPolicyError("subscription policy must be an object")
    if type(allow_other_adapter_regions) is not bool:
        raise MediaCrawlerSubscriptionPolicyError("allow_other_adapter_regions must be boolean")
    supplied_regions = set(subscription_policy)
    if "mediacrawler" not in supplied_regions:
        raise MediaCrawlerSubscriptionPolicyError("subscription policy has no MediaCrawler region")
    if not allow_other_adapter_regions and supplied_regions != {"mediacrawler"}:
        raise MediaCrawlerSubscriptionPolicyError("subscription policy contains unsupported adapter regions")
    mediacrawler_policy = subscription_policy.get("mediacrawler")
    if not isinstance(mediacrawler_policy, Mapping):
        raise MediaCrawlerSubscriptionPolicyError("MediaCrawler policy must be an object")
    return MediaCrawlerSubscriptionPolicy.from_payload(mediacrawler_policy)


__all__ = [
    "MAX_REQUEST_DELAY_SECONDS",
    "SUBSCRIPTION_POLICY_SCHEMA_VERSION",
    "MediaCrawlerSubscriptionPolicy",
    "MediaCrawlerSubscriptionPolicyError",
    "from_subscription_policy",
]
