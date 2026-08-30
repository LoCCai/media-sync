"""SQLAlchemy persistence package.

Repositories consume an explicit ``Session``.  ``Database.session()`` owns the
outer transaction so callers can combine multiple repository operations.
"""

from .asset_identity import ASSET_IDENTITY_VERSION, AssetFingerprints, asset_fingerprints
from .base import Base, UTCDateTime, new_uuid, utc_now
from .database import Database, create_database_engine
from .mediacrawler_ingestion import (
    IngestionMode,
    MediaCrawlerIngestionResult,
    MediaCrawlerIngestionService,
)
from .migration import upgrade_database
from .models import (
    Account,
    Asset,
    AssetRefreshSource,
    Author,
    Content,
    ExportRecord,
    Job,
    LoginSession,
    RunEvent,
    SchedulerLane,
    Subscription,
    SyncRun,
)
from .repositories import (
    AccountRepository,
    AssetConflictError,
    AssetLeaseLostError,
    AssetRefreshSourceRepository,
    AssetRepository,
    AssetUpsert,
    AuthorRepository,
    AuthorUpsert,
    ContentUpsert,
    ExportRecordConflictError,
    ExportRecordRepository,
    JobRepository,
    LeaseLostError,
    LoginSessionRepository,
    NotFoundError,
    RepositoryError,
    StaleCheckpointError,
    SubscriptionRepository,
    SyncRunRepository,
)
from .sync_repository import SQLAlchemySyncRepository

__all__ = [
    "ASSET_IDENTITY_VERSION",
    "Account",
    "AccountRepository",
    "Asset",
    "AssetConflictError",
    "AssetFingerprints",
    "AssetLeaseLostError",
    "AssetRefreshSource",
    "AssetRefreshSourceRepository",
    "AssetRepository",
    "AssetUpsert",
    "Author",
    "AuthorRepository",
    "AuthorUpsert",
    "Base",
    "Content",
    "ContentUpsert",
    "Database",
    "ExportRecord",
    "ExportRecordConflictError",
    "ExportRecordRepository",
    "IngestionMode",
    "Job",
    "JobRepository",
    "LeaseLostError",
    "LoginSession",
    "LoginSessionRepository",
    "MediaCrawlerIngestionResult",
    "MediaCrawlerIngestionService",
    "NotFoundError",
    "RepositoryError",
    "RunEvent",
    "SQLAlchemySyncRepository",
    "SchedulerLane",
    "StaleCheckpointError",
    "Subscription",
    "SubscriptionRepository",
    "SyncRun",
    "SyncRunRepository",
    "UTCDateTime",
    "asset_fingerprints",
    "create_database_engine",
    "new_uuid",
    "upgrade_database",
    "utc_now",
]
