"""Engine creation and transaction boundaries for the local database."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .base import Base

SQLITE_BUSY_TIMEOUT_MS = 5_000


def _ensure_sqlite_parent(database_url: str) -> None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        return
    Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def _configure_sqlite_connection(dbapi_connection: Any, connection_record: Any) -> None:
    del connection_record
    # Python 3.11's sqlite3 legacy transaction mode does not BEGIN before a
    # SAVEPOINT, so releasing a nested transaction can accidentally commit it
    # outside the Session's outer rollback.  SQLAlchemy owns BEGIN explicitly.
    dbapi_connection.isolation_level = None
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def _begin_sqlite_transaction(connection: Connection) -> None:
    connection.exec_driver_sql("BEGIN")


def create_database_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Create an engine with safe SQLite defaults when applicable."""

    _ensure_sqlite_parent(database_url)
    url = make_url(database_url)
    kwargs: dict[str, Any] = {"echo": echo, "future": True}
    if url.drivername.startswith("sqlite"):
        kwargs["connect_args"] = {
            "check_same_thread": False,
            "timeout": SQLITE_BUSY_TIMEOUT_MS / 1_000,
        }
        if url.database in {None, "", ":memory:"}:
            kwargs["poolclass"] = StaticPool
    engine = create_engine(database_url, **kwargs)
    if url.drivername.startswith("sqlite"):
        event.listen(engine, "connect", _configure_sqlite_connection)
        event.listen(engine, "begin", _begin_sqlite_transaction)
    return engine


class Database:
    """Own an engine and expose explicit commit/rollback session scopes.

    Repository objects accept a :class:`sqlalchemy.orm.Session`, not this
    wrapper.  Use ``with database.session() as session`` and pass that session
    to one or more repositories.  Repository methods flush but never commit,
    allowing application services to compose a single atomic transaction.
    """

    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        self.url = database_url
        self.engine = create_database_engine(database_url, echo=echo)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
            autoflush=False,
        )

    def create_schema(self) -> None:
        """Create the current metadata directly, primarily for isolated tests."""

        Base.metadata.create_all(self.engine)

    def drop_schema(self) -> None:
        """Drop all known tables; intended only for isolated tests."""

        Base.metadata.drop_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a transactional session and commit or roll back on exit."""

        session = self.session_factory()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()


__all__ = ["SQLITE_BUSY_TIMEOUT_MS", "Database", "create_database_engine"]
