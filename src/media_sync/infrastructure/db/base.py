"""SQLAlchemy declarative base and database-neutral scalar types."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import uuid4

from sqlalchemy import JSON, DateTime, MetaData
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def new_uuid() -> str:
    """Return a portable UUID string suitable for public database identifiers."""

    return str(uuid4())


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Persist aware datetimes as UTC and restore UTC awareness on SQLite.

    SQLite has no timezone-aware datetime storage class.  Values are normalized
    to naive UTC on bind and receive ``timezone.utc`` again when loaded.  Other
    dialects receive an aware UTC value.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("database datetimes must be timezone-aware")
        normalized = value.astimezone(UTC)
        if dialect.name == "sqlite":
            return normalized.replace(tzinfo=None)
        return normalized

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        del dialect
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @property
    def python_type(self) -> type[datetime]:
        return datetime


class Base(DeclarativeBase):
    """Declarative root shared by runtime models and Alembic."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSON}
