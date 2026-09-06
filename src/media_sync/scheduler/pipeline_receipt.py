"""Version-independent, closed and path-free pipeline delivery observations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from uuid import UUID

from media_sync.domain import Platform


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

    def __post_init__(self) -> None:
        for name in ("subscription_id", "account_id", "author_id", "export_job_id"):
            value = getattr(self, name)
            if type(value) is not str or str(UUID(value)) != value:
                raise ValueError("pipeline delivery receipt UUIDs must be canonical strings")
        if type(self.platform) is not str or self.platform not in {item.value for item in Platform}:
            raise ValueError("pipeline delivery receipt platform is invalid")
        for name in (
            "selected_asset_count",
            "verified_asset_count",
            "downloaded_count",
            "already_verified_count",
            "managed_file_count",
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

    def to_mapping(self) -> dict[str, object]:
        return {item.name: getattr(self, item.name) for item in fields(self)}

    @classmethod
    def from_mapping(cls, value: object) -> PipelineDeliveryReceipt:
        if not isinstance(value, Mapping) or set(value) != {item.name for item in fields(cls)}:
            raise ValueError("pipeline delivery receipt is not closed schema")
        return cls(**dict(value))


__all__ = ["PipelineDeliveryReceipt"]
