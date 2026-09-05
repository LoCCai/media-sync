"""Observed content ownership stays immutable across creator ingestions."""

from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from media_sync.infrastructure.db import (
    AuthorRepository,
    AuthorUpsert,
    ContentOwnershipConflictError,
    ContentUpsert,
    Database,
    RepositoryError,
)
from media_sync.infrastructure.db.base import Base
from media_sync.infrastructure.db.models import Author, Content

NOW = datetime(2026, 9, 6, 3, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)
POSTGRESQL_URL_ENV = "MEDIA_SYNC_TEST_POSTGRESQL_URL"
SENTINEL = "private-owner-cookie-do-not-reflect"


@pytest.fixture(params=["sqlite", "postgresql"])
def database(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[Database]:
    if request.param == "postgresql":
        raw_url = os.environ.get(POSTGRESQL_URL_ENV)
        if not raw_url:
            pytest.skip(f"{POSTGRESQL_URL_ENV} is not set; real PostgreSQL ownership tests were not run")
        url = make_url(raw_url)
        if url.get_backend_name() != "postgresql":
            pytest.fail(f"{POSTGRESQL_URL_ENV} must identify a PostgreSQL database")
        url = url.set(drivername="postgresql+psycopg")
        admin_database = Database(url.render_as_string(hide_password=False))
        schema = f"media_sync_content_ownership_{uuid4().hex}"
        instance: Database | None = None
        created = False
        try:
            with admin_database.engine.begin() as connection:
                connection.execute(CreateSchema(schema))
            created = True
            scoped_url = url.update_query_dict(
                {"options": f"-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=10000"},
                append=False,
            )
            instance = Database(scoped_url.render_as_string(hide_password=False))
            Base.metadata.create_all(instance.engine, tables=[Author.__table__, Content.__table__])
            yield instance
        finally:
            if instance is not None:
                instance.dispose()
            if created:
                with admin_database.engine.begin() as connection:
                    connection.execute(DropSchema(schema, cascade=True, if_exists=True))
            admin_database.dispose()
        return
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'ownership.sqlite3').as_posix()}")
    Base.metadata.create_all(instance.engine, tables=[Author.__table__, Content.__table__])
    try:
        yield instance
    finally:
        instance.dispose()


def _author(remote_id: str = "first-author", *, label: str = "Original author") -> AuthorUpsert:
    return AuthorUpsert(
        platform="bili", remote_id=remote_id, display_name=label, handle=label, raw={"observation": label}
    )


def _content(remote_id: str = "123456", *, label: str = "Original", remote_type: str = "content") -> ContentUpsert:
    return ContentUpsert(
        remote_id=remote_id,
        remote_type=remote_type,
        kind="dynamic" if remote_type == "dynamic" else "video",
        title=label,
        body=f"Body {label}",
        canonical_url=f"https://example.invalid/{remote_id}",
        published_at=NOW,
        remote_updated_at=NOW,
        metrics={"views": 4},
        raw={"observation": label},
        metadata_hash="a" * 64,
    )


def _seed(database: Database, *, tombstoned: bool = False) -> tuple[str, str]:
    with database.session() as session:
        author, contents = AuthorRepository(session).upsert_with_contents(_author(), [_content()], seen_at=NOW)
        if tombstoned:
            contents[0].tombstoned_at = NOW
        return author.id, contents[0].id


def _snapshot(database: Database, table: type[Author] | type[Content]) -> list[dict[str, object]]:
    with database.session() as session:
        return deepcopy([dict(row) for row in session.execute(select(table.__table__).order_by(table.id)).mappings()])


def _assert_conflict(error: RepositoryError) -> None:
    assert type(error) is ContentOwnershipConflictError
    assert str(error) == "content_ownership_conflict"
    assert error.args == ("content_ownership_conflict",)
    assert getattr(error, "code", None) == "content_ownership_conflict"
    assert SENTINEL not in repr(error)


def test_conflict_exception_accepts_no_identity_or_secret_arguments() -> None:
    _assert_conflict(ContentOwnershipConflictError())
    with pytest.raises(TypeError):
        ContentOwnershipConflictError(SENTINEL)  # type: ignore[call-arg]


def test_cross_author_content_identity_cannot_be_reassigned(database: Database) -> None:
    _seed(database, tombstoned=True)
    before_contents = _snapshot(database, Content)
    before_authors = _snapshot(database, Author)
    with database.session() as session:
        with pytest.raises(RepositoryError) as caught:
            AuthorRepository(session).upsert_with_contents(
                _author("second-author", label=SENTINEL), [_content(label=SENTINEL)], seen_at=LATER
            )
        _assert_conflict(caught.value)
        assert session.is_active
    assert _snapshot(database, Content) == before_contents
    assert _snapshot(database, Author) == before_authors


def test_same_author_refreshes_metadata_without_replacing_identity(database: Database) -> None:
    author_id, content_id = _seed(database, tombstoned=True)
    with database.session() as session:
        author, contents = AuthorRepository(session).upsert_with_contents(
            _author(label="Updated author"),
            [replace(_content(label="Updated"), metrics={"views": 9}, metadata_hash="b" * 64)],
            seen_at=LATER,
        )
        assert author.id == author_id
        assert contents[0].id == content_id
        assert contents[0].author_id == author_id
        assert contents[0].title == "Updated"
        assert contents[0].body == "Body Updated"
        assert contents[0].metrics == {"views": 9}
        assert contents[0].metadata_hash == "b" * 64
        assert contents[0].first_seen_at == NOW
        assert contents[0].last_seen_at == LATER
        assert contents[0].tombstoned_at is None
    assert len(_snapshot(database, Author)) == len(_snapshot(database, Content)) == 1


@pytest.mark.parametrize("existing_contender", [False, True])
def test_rejected_savepoint_rolls_back_author_and_earlier_content_but_keeps_outer_transaction(
    database: Database, existing_contender: bool
) -> None:
    _seed(database)
    if existing_contender:
        with database.session() as session:
            AuthorRepository(session).upsert(_author("contender", label="Prior contender"), seen_at=NOW)
    before_authors = _snapshot(database, Author)
    before_contents = _snapshot(database, Content)
    with database.session() as session:
        repository = AuthorRepository(session)
        repository.upsert(_author("outer-before"), seen_at=NOW)
        with pytest.raises(RepositoryError) as caught:
            repository.upsert_with_contents(
                _author("contender", label=SENTINEL),
                [_content("new-within-savepoint"), _content(label=SENTINEL)],
                seen_at=LATER,
            )
        _assert_conflict(caught.value)
        assert session.is_active
        repository.upsert_with_contents(_author("outer-after"), [_content("after-conflict")], seen_at=LATER)
    after_authors = _snapshot(database, Author)
    assert [row for row in after_authors if row["remote_id"] not in {"outer-before", "outer-after"}] == before_authors
    after_contents = _snapshot(database, Content)
    assert [row for row in after_contents if row["remote_id"] != "after-conflict"] == before_contents
    assert len(after_contents) == 2


def test_dynamic_and_upload_same_numeric_id_keep_distinct_owners_and_stable_keys(database: Database) -> None:
    from media_sync.infrastructure.db.asset_identity import stable_asset_key

    first_author, upload_id = _seed(database)
    with database.session() as session:
        second_author, contents = AuthorRepository(session).upsert_with_contents(
            _author("dynamic-author"), [_content(remote_type="dynamic")], seen_at=NOW
        )
        assert second_author.id != first_author
        assert contents[0].id != upload_id
    rows = _snapshot(database, Content)
    assert {(row["remote_id"], row["remote_type"]) for row in rows} == {("123456", "content"), ("123456", "dynamic")}
    keys = {
        stable_asset_key(
            platform="bili",
            content_remote_type=remote_type,
            content_remote_id="123456",
            kind="image",
            position=0,
            remote_id="123456:image:0",
        )
        for remote_type in ("content", "dynamic")
    }
    assert len(keys) == 2


def test_platform_remains_part_of_content_identity(database: Database) -> None:
    _seed(database)
    with database.session() as session:
        AuthorRepository(session).upsert_with_contents(replace(_author(), platform="wb"), [_content()], seen_at=NOW)
    assert len(_snapshot(database, Content)) == len(_snapshot(database, Author)) == 2


@pytest.mark.parametrize("same_creator", [False, True])
def test_concurrent_initial_writers_share_one_content_and_never_reassign(
    database: Database, same_creator: bool
) -> None:
    start = Barrier(2)

    def ingest(label: str) -> tuple[str, str, str]:
        worker = Database(database.url)
        try:
            start.wait(timeout=10)
            with worker.session() as session:
                try:
                    author, contents = AuthorRepository(session).upsert_with_contents(
                        _author("shared-author" if same_creator else label, label=label),
                        [_content(label=label)],
                        seen_at=NOW,
                    )
                except RepositoryError as error:
                    _assert_conflict(error)
                    return "conflict", "", ""
                return "success", author.id, contents[0].id
        finally:
            worker.dispose()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(ingest, ("first-worker", "second-worker")))
    assert [result[0] for result in results].count("success") == (2 if same_creator else 1)
    winners = [result for result in results if result[0] == "success"]
    assert len({result[1:] for result in winners}) == 1
    authors, contents = _snapshot(database, Author), _snapshot(database, Content)
    assert len(authors) == len(contents) == 1
    assert contents[0]["author_id"] == winners[0][1]
    assert contents[0]["id"] == winners[0][2]
    assert contents[0]["title"] == authors[0]["display_name"]


@pytest.mark.parametrize("commit_first", [False, True])
def test_waiting_first_discovery_follows_committed_owner_or_rolled_back_absence(
    database: Database, commit_first: bool
) -> None:
    attempted = Event()
    contender = Database(database.url)
    first = database.session_factory()
    winner_author, winner_contents = AuthorRepository(first).upsert_with_contents(_author(), [_content()], seen_at=NOW)
    winner_ids = winner_author.id, winner_contents[0].id

    def before_execute(_connection: object, _cursor: object, statement: str, *_args: object) -> None:
        if statement.startswith("INSERT INTO authors"):
            attempted.set()

    event.listen(contender.engine, "before_cursor_execute", before_execute)

    def insert_contender() -> tuple[str, str, str]:
        with contender.session() as session:
            try:
                author, contents = AuthorRepository(session).upsert_with_contents(
                    _author("second-author", label="Second"), [_content(label="Second")], seen_at=LATER
                )
            except RepositoryError as error:
                _assert_conflict(error)
                return "conflict", "", ""
            return "success", author.id, contents[0].id

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(insert_contender)
            try:
                assert attempted.wait(timeout=5), "contender did not reach its native author INSERT"
                assert not future.done()
                first.commit() if commit_first else first.rollback()
            finally:
                # Always release the first transaction before joining a waiting worker.
                first.rollback()
            outcome = future.result(timeout=10)
    finally:
        first.close()
        contender.dispose()
    assert outcome[0] == ("conflict" if commit_first else "success")
    authors, contents = _snapshot(database, Author), _snapshot(database, Content)
    assert len(authors) == len(contents) == 1
    assert (contents[0]["author_id"], contents[0]["id"]) == (winner_ids if commit_first else outcome[1:])


def test_stale_orm_owner_does_not_override_current_database_owner(database: Database) -> None:
    original_author_id, content_id = _seed(database)
    with database.session() as session:
        new_owner = AuthorRepository(session).upsert(_author("legacy-owner"), seen_at=NOW)
        new_owner_id = new_owner.id
    stale = database.session_factory()
    try:
        cached = stale.get(Content, content_id)
        assert cached is not None and cached.author_id == original_author_id
        stale.commit()
        # Simulate a committed historical/out-of-band writer in this isolated test DB.
        with database.engine.begin() as connection:
            connection.execute(update(Content).where(Content.id == content_id).values(author_id=new_owner_id))
        assert cached.author_id == original_author_id
        before = _snapshot(database, Content)
        with pytest.raises(RepositoryError) as caught:
            AuthorRepository(stale).upsert_with_contents(_author(), [_content(label=SENTINEL)], seen_at=LATER)
        _assert_conflict(caught.value)
        stale.commit()
        assert _snapshot(database, Content) == before
    finally:
        stale.close()


def test_same_author_upsert_refreshes_existing_orm_instance(database: Database) -> None:
    author_id, content_id = _seed(database)
    with database.session() as session:
        cached = session.get(Content, content_id)
        assert cached is not None
        _, contents = AuthorRepository(session).upsert_with_contents(
            _author(), [_content(label="Fresh result")], seen_at=LATER
        )
        assert contents[0] is cached
        assert cached.title == "Fresh result"
        assert cached.author_id == author_id


def test_actual_native_conflict_statement_fences_owner_in_update_predicate(database: Database) -> None:
    _seed(database)
    statements: list[str] = []

    def before_execute(_connection: object, _cursor: object, statement: str, *_args: object) -> None:
        if statement.startswith("INSERT INTO contents"):
            statements.append(statement)

    event.listen(database.engine, "before_cursor_execute", before_execute)
    try:
        with database.session() as session:
            AuthorRepository(session).upsert_with_contents(
                _author(), [_content(label="Same-author refresh")], seen_at=LATER
            )
    finally:
        event.remove(database.engine, "before_cursor_execute", before_execute)
    assert len(statements) == 1
    sql = " ".join(statements[0].split())
    assert "ON CONFLICT (platform, remote_type, remote_id) DO UPDATE SET" in sql
    assert "WHERE contents.author_id =" in sql
    update_assignments = sql.partition("DO UPDATE SET")[2].partition(" WHERE ")[0]
    assert "author_id =" not in update_assignments
    assert sql.partition(" RETURNING ")[2].split(",", maxsplit=1)[0] in {"id", "contents.id"}


@pytest.mark.parametrize("dialect", [sqlite.dialect(), postgresql.dialect()], ids=["sqlite", "postgresql"])
def test_native_content_statement_compiles_owner_predicate_offline(dialect: object) -> None:
    """Compilation coverage does not claim a real PostgreSQL transaction ran."""
    session = Mock(spec=Session)
    session.get_bind.return_value = SimpleNamespace(dialect=dialect)
    session.scalars.return_value.one_or_none.return_value = None
    author = Author(id=str(uuid4()), platform="bili", remote_id="first-author", display_name="Original")
    with pytest.raises(ContentOwnershipConflictError) as caught:
        AuthorRepository(session)._upsert_content(author, _content(), seen_at=NOW)
    _assert_conflict(caught.value)
    statement = session.scalars.call_args.args[0]
    compiled = statement.compile(dialect=dialect)
    sql = " ".join(str(compiled).split())
    assert "ON CONFLICT (platform, remote_type, remote_id) DO UPDATE SET" in sql
    assert "WHERE contents.author_id =" in sql
    assert "author_id =" not in sql.partition("DO UPDATE SET")[2].partition(" WHERE ")[0]
    assert compiled.params["author_id"] == author.id
    assert list(compiled.params.values()).count(author.id) == 2  # Initial owner and conflict predicate.
    assert statement.get_execution_options()["populate_existing"] is True
    session.scalar.assert_not_called()  # No SELECT-then-overwrite race.


def test_postgresql_author_creation_uses_native_upsert_offline() -> None:
    session = Mock(spec=Session)
    session.get_bind.return_value = SimpleNamespace(dialect=postgresql.dialect())
    author = Author(id=str(uuid4()), platform="bili", remote_id="first-author", display_name="Original")
    session.scalars.return_value.one.return_value = author
    assert AuthorRepository(session).upsert(_author(), seen_at=NOW) is author
    statement = session.scalars.call_args.args[0]
    sql = " ".join(str(statement.compile(dialect=postgresql.dialect())).split())
    assert "INSERT INTO authors" in sql
    assert "ON CONFLICT (platform, remote_id) DO UPDATE SET" in sql
    assert statement.get_execution_options()["populate_existing"] is True
    session.scalar.assert_not_called()


def test_other_dialect_fallback_locks_and_rejects_a_different_current_owner() -> None:
    session = Mock(spec=Session)
    session.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="other"))
    previous = Content(
        id=str(uuid4()),
        author_id=str(uuid4()),
        platform="bili",
        remote_id="123456",
        remote_type="content",
        kind="video",
        title="Original",
        tombstoned_at=NOW,
    )
    session.scalar.return_value = previous
    contender = Author(id=str(uuid4()), platform="bili", remote_id="second-author", display_name="Contender")
    with pytest.raises(ContentOwnershipConflictError):
        AuthorRepository(session)._upsert_content(contender, _content(label=SENTINEL), seen_at=LATER)
    statement = session.scalar.call_args.args[0]
    assert str(statement.compile(dialect=postgresql.dialect())).endswith("FOR UPDATE")
    assert statement.get_execution_options()["populate_existing"] is True
    assert previous.author_id != contender.id and previous.title == "Original" and previous.tombstoned_at == NOW
    session.add.assert_not_called()
    session.flush.assert_not_called()
