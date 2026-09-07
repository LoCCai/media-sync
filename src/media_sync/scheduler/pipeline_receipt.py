"""Version-independent, closed and path-free pipeline delivery observations."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from media_sync.domain import Platform

_LEGACY_KEYS = frozenset(
    {
        "subscription_id",
        "account_id",
        "author_id",
        "platform",
        "export_job_id",
        "selected_asset_count",
        "verified_asset_count",
        "downloaded_count",
        "already_verified_count",
        "publication_disposition",
        "managed_file_count",
        "directory_verified",
    }
)
_V2_KEYS = _LEGACY_KEYS | {
    "schema_version",
    "source_run_id",
    "observed_content_count",
    "delivered_content_count",
    "failed_content_count",
    "retry_backlog_content_count",
    "delivered_retry_backlog_content_count",
    "failed_retry_backlog_content_count",
    "retryable_failed_content_count",
    "terminal_failed_content_count",
    "failure_codes",
    "partial",
}
_FIXED_CODE = re.compile(r"[a-z][a-z0-9_]{0,127}\Z")


@dataclass(frozen=True, slots=True)
class PipelineDeliveryReceipt:
    subscription_id: str
    account_id: str
    author_id: str
    platform: str
    export_job_id: str
    selected_asset_count: int
    verified_asset_count: int
    downloaded_count: int
    already_verified_count: int
    publication_disposition: str
    managed_file_count: int
    directory_verified: bool
    schema_version: int = 1
    source_run_id: str | None = None
    observed_content_count: int = 0
    delivered_content_count: int = 0
    failed_content_count: int = 0
    retry_backlog_content_count: int = 0
    delivered_retry_backlog_content_count: int = 0
    failed_retry_backlog_content_count: int = 0
    retryable_failed_content_count: int = 0
    terminal_failed_content_count: int = 0
    failure_codes: tuple[str, ...] = ()
    partial: bool = False

    def __post_init__(self) -> None:
        for name in ("subscription_id", "account_id", "author_id", "export_job_id"):
            value = getattr(self, name)
            if type(value) is not str or str(UUID(value)) != value:
                raise ValueError("pipeline delivery receipt UUIDs must be canonical strings")
        if type(self.platform) is not str or self.platform not in {item.value for item in Platform}:
            raise ValueError("pipeline delivery receipt platform is invalid")
        if type(self.schema_version) is not int or self.schema_version not in {1, 2}:
            raise ValueError("pipeline delivery receipt schema version is invalid")
        for name in (
            "selected_asset_count",
            "verified_asset_count",
            "downloaded_count",
            "already_verified_count",
            "managed_file_count",
            "observed_content_count",
            "delivered_content_count",
            "failed_content_count",
            "retry_backlog_content_count",
            "delivered_retry_backlog_content_count",
            "failed_retry_backlog_content_count",
            "retryable_failed_content_count",
            "terminal_failed_content_count",
        ):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 9_007_199_254_740_991:
                raise ValueError("pipeline delivery receipt counts must be non-negative integers")
        if (
            self.verified_asset_count != self.selected_asset_count
            or self.downloaded_count + self.already_verified_count != self.verified_asset_count
            or self.publication_disposition not in {"published", "already_exported"}
            or self.directory_verified is not True
        ):
            raise ValueError("pipeline delivery receipt is inconsistent")
        if self.schema_version == 1:
            if (
                self.source_run_id is not None
                or self.observed_content_count
                or self.delivered_content_count
                or self.failed_content_count
                or self.retry_backlog_content_count
                or self.delivered_retry_backlog_content_count
                or self.failed_retry_backlog_content_count
                or self.retryable_failed_content_count
                or self.terminal_failed_content_count
                or self.failure_codes
                or self.partial
            ):
                raise ValueError("legacy pipeline delivery receipt carries v2 evidence")
            return
        if type(self.source_run_id) is not str or str(UUID(self.source_run_id)) != self.source_run_id:
            raise ValueError("pipeline delivery receipt source Run is invalid")
        if (
            self.delivered_content_count + self.failed_content_count != self.observed_content_count
            or self.delivered_retry_backlog_content_count + self.failed_retry_backlog_content_count
            != self.retry_backlog_content_count
            or self.retryable_failed_content_count + self.terminal_failed_content_count
            != self.failed_content_count + self.failed_retry_backlog_content_count
            or self.partial is not (self.failed_content_count + self.failed_retry_backlog_content_count > 0)
            or type(self.failure_codes) is not tuple
            or len(self.failure_codes) > 16
            or len(set(self.failure_codes)) != len(self.failure_codes)
            or tuple(sorted(self.failure_codes)) != self.failure_codes
            or any(type(code) is not str or _FIXED_CODE.fullmatch(code) is None for code in self.failure_codes)
            or (self.failed_content_count + self.failed_retry_backlog_content_count > 0 and not self.failure_codes)
            or (self.failed_content_count + self.failed_retry_backlog_content_count == 0 and self.failure_codes)
        ):
            raise ValueError("pipeline delivery receipt content evidence is inconsistent")

    def to_mapping(self) -> dict[str, object]:
        legacy = {key: getattr(self, key) for key in _LEGACY_KEYS}
        if self.schema_version == 1:
            return legacy
        return {
            **legacy,
            "schema_version": self.schema_version,
            "source_run_id": self.source_run_id,
            "observed_content_count": self.observed_content_count,
            "delivered_content_count": self.delivered_content_count,
            "failed_content_count": self.failed_content_count,
            "retry_backlog_content_count": self.retry_backlog_content_count,
            "delivered_retry_backlog_content_count": self.delivered_retry_backlog_content_count,
            "failed_retry_backlog_content_count": self.failed_retry_backlog_content_count,
            "retryable_failed_content_count": self.retryable_failed_content_count,
            "terminal_failed_content_count": self.terminal_failed_content_count,
            "failure_codes": list(self.failure_codes),
            "partial": self.partial,
        }

    @classmethod
    def from_mapping(cls, value: object) -> PipelineDeliveryReceipt:
        if not isinstance(value, Mapping) or set(value) not in {_LEGACY_KEYS, _V2_KEYS}:
            raise ValueError("pipeline delivery receipt is not closed schema")
        payload = dict(value)
        if set(payload) == _LEGACY_KEYS:
            return cls(**payload)
        if payload.get("schema_version") != 2 or type(payload.get("failure_codes")) is not list:
            raise ValueError("pipeline delivery receipt is not closed schema")
        payload["failure_codes"] = tuple(payload["failure_codes"])
        return cls(**payload)


__all__ = ["PipelineDeliveryReceipt"]
