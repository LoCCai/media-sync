"""SQLAlchemy persistence package.

Repositories consume an explicit ``Session``.  ``Database.session()`` owns the
outer transaction so callers can combine multiple repository operations.
"""

from .base import Base, UTCDateTime, new_uuid, utc_now
from .database import Database, create_database_engine
from .migration import upgrade_database
from .models import (
    Account,
    Asset,
    Author,
    Content,
    ExportRecord,
    Job,
    LoginSession,
    RunEvent,
    Subscription,
    SyncRun,
)
from .repositories import (
    AccountRepository,
    AssetRepository,
    AssetUpsert,
    AuthorRepository,
    AuthorUpsert,
    ContentUpsert,
    ExportRecordRepository,
    JobRepository,
    LeaseLostError,
    LoginSessionRepository,
    NotFoundError,
    RepositoryError,
    SubscriptionRepository,
    SyncRunRepository,
)
from .sync_repository import SQLAlchemySyncRepository

__all__ = [
    "Account",
    "AccountRepository",
    "Asset",
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
    "ExportRecordRepository",
    "Job",
    "JobRepository",
    "LeaseLostError",
    "LoginSession",
    "LoginSessionRepository",
    "NotFoundError",
    "RepositoryError",
    "RunEvent",
    "SQLAlchemySyncRepository",
    "Subscription",
    "SubscriptionRepository",
    "SyncRun",
    "SyncRunRepository",
    "UTCDateTime",
    "create_database_engine",
    "new_uuid",
    "upgrade_database",
    "utc_now",
]
