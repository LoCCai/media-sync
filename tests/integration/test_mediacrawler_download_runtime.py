"""Runtime wiring tests for lazy, exact-source MediaCrawler refresh."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from uuid import UUID, uuid4

import pytest

from media_sync.application import mediacrawler_download as runtime
from media_sync.application.mediacrawler_download import LazyMediaCrawlerLocatorRefresher
from media_sync.domain import AssetKind, LoginMethod, Platform
from media_sync.infrastructure.db import (
    AccountRepository,
    AssetRefreshSourceRepository,
    AssetRepository,
    AssetUpsert,
    AuthorRepository,
    AuthorUpsert,
    ContentUpsert,
    Database,
    SubscriptionRepository,
)
from media_sync.infrastructure.db.asset_identity import asset_source_hint, stable_asset_key
from media_sync.integrations.mediacrawler import MediaCrawlerDetailRequest, MediaCrawlerDetailResult
from media_sync.media import AdapterRefreshLocator, MediaDownloadError
from media_sync.security import SecretProvider, SecretReference, SecretResolver, SecretScheme, SecretValue

UPSTREAM_SHA = "d6f7c5bb906b6dac40ddf343ef9e26438a3de092"
CONTENT_ID = "987654321"
ASSET_REMOTE_ID = f"{CONTENT_ID}:cover:0"
SIGNED_URL = "https://cdn.runtime.test/bili/cover.jpg?token=runtime-cookie-sentinel"
SOURCE_HINT = asset_source_hint(SIGNED_URL)
assert SOURCE_HINT is not None


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    instance = Database(f"sqlite+pysqlite:///{(tmp_path / 'runtime.sqlite3').as_posix()}")
    instance.create_schema()
    try:
        yield instance
    finally:
        instance.dispose()


class _RecordingSecretProvider(SecretProvider):
    scheme = SecretScheme.ENV

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = dict(values)
        self.calls: list[str] = []

    def resolve(self, reference: SecretReference) -> SecretValue:
        self.calls.append(reference.serialize())
        return SecretValue(self._values[reference.locator])


class _FakeMediaCrawlerDetailProcessRunner:
    payload: ClassVar[bytes]
    instances: ClassVar[list[_FakeMediaCrawlerDetailProcessRunner]] = []

    def __init__(self, **kwargs: object) -> None:
        self.constructor_kwargs = kwargs
        self.calls: list[MediaCrawlerDetailRequest] = []
        type(self).instances.append(self)

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        self.calls.append(request)
        return MediaCrawlerDetailResult(type(self).payload, UPSTREAM_SHA)

    @classmethod
    def reset(cls) -> None:
        cls.instances = []
        cls.payload = (
            json.dumps(
                {
                    "video_id": CONTENT_ID,
                    "video_type": "video",
                    "title": "Runtime fixture",
                    "video_cover_url": SIGNED_URL,
                },
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )


@pytest.fixture
def fake_detail_runner(monkeypatch: pytest.MonkeyPatch) -> type[_FakeMediaCrawlerDetailProcessRunner]:
    _FakeMediaCrawlerDetailProcessRunner.reset()
    monkeypatch.setattr(runtime, "MediaCrawlerDetailProcessRunner", _FakeMediaCrawlerDetailProcessRunner)
    return _FakeMediaCrawlerDetailProcessRunner


@dataclass(frozen=True, slots=True)
class _RuntimeSeed:
    asset_id: UUID
    locator: AdapterRefreshLocator
    account_id: UUID
    source_subscription_ids: tuple[UUID, ...]


def _policy(*, headless: bool = False, request_delay_seconds: float = 7.25) -> dict[str, object]:
    return {
        "mediacrawler": {
            "schema_version": 1,
            "allow_full_history": False,
            "request_delay_seconds": request_delay_seconds,
            "headless": headless,
        }
    }


def _seed(
    database: Database,
    *,
    source_count: int,
    login_method: LoginMethod = LoginMethod.COOKIE,
    platform: Platform = Platform.BILI,
    content_remote_type: str = "content",
    asset_kind: AssetKind = AssetKind.COVER,
    asset_position: int = 0,
    asset_remote_id: str = ASSET_REMOTE_ID,
    source_url: str | None = SOURCE_HINT,
) -> _RuntimeSeed:
    with database.session() as session:
        author, contents = AuthorRepository(session).upsert_with_contents(
            AuthorUpsert(
                platform=platform.value,
                remote_id="runtime-author",
                display_name="Runtime Author",
            ),
            (ContentUpsert(remote_id=CONTENT_ID, remote_type=content_remote_type, kind="video"),),
        )
        locator = AdapterRefreshLocator(
            adapter="mediacrawler",
            asset_key=stable_asset_key(
                platform=platform.value,
                content_remote_type=content_remote_type,
                content_remote_id=CONTENT_ID,
                kind=asset_kind.value,
                position=asset_position,
                remote_id=asset_remote_id,
            ),
        )
        asset = AssetRepository(session).upsert_for_content(
            contents[0].id,
            AssetUpsert(
                platform=platform.value,
                content_remote_type=content_remote_type,
                content_remote_id=CONTENT_ID,
                kind=asset_kind.value,
                position=asset_position,
                remote_id=asset_remote_id,
                source_url=source_url,
                locator=locator.as_dict(),
            ),
        )
        source_ids: list[UUID] = []
        first_account_id: UUID | None = None
        for index in range(max(source_count, 1)):
            account = AccountRepository(session).create(
                platform=platform.value,
                adapter="mediacrawler",
                display_name=f"runtime-account-{index}",
                login_method=login_method.value if index == 0 else LoginMethod.QR.value,
                credential_ref="env:MC_COOKIE" if index == 0 and login_method is LoginMethod.COOKIE else None,
                auth_status="authenticated",
            )
            subscription = SubscriptionRepository(session).create(
                account_id=account.id,
                author_id=author.id,
                policy=_policy(),
            )
            if first_account_id is None:
                first_account_id = UUID(account.id)
            if index < source_count:
                AssetRefreshSourceRepository(session).upsert_observation(
                    asset_id=asset.id,
                    subscription_id=subscription.id,
                )
                source_ids.append(UUID(subscription.id))
        assert first_account_id is not None
        return _RuntimeSeed(
            asset_id=UUID(asset.id),
            locator=locator,
            account_id=first_account_id,
            source_subscription_ids=tuple(source_ids),
        )


def _lazy(
    database: Database,
    seed: _RuntimeSeed,
    resolver: SecretResolver,
    tmp_path: Path,
    *,
    subscription_id: UUID | None,
) -> LazyMediaCrawlerLocatorRefresher:
    return LazyMediaCrawlerLocatorRefresher(
        database,
        asset_id=seed.asset_id,
        subscription_id=subscription_id,
        lock_path=tmp_path / "upstreams.lock.json",
        integration_root=tmp_path / "runtime",
        python_executable=tmp_path / "python",
        secret_resolver=resolver,
        license_acknowledged=True,
    )


def test_exact_single_source_builds_once_and_resolves_with_exact_runtime_scope(
    database: Database,
    tmp_path: Path,
    fake_detail_runner: type[_FakeMediaCrawlerDetailProcessRunner],
) -> None:
    seed = _seed(database, source_count=1)
    provider = _RecordingSecretProvider({"MC_COOKIE": "cookie=value; runtime-cookie-sentinel"})
    resolver = SecretResolver({SecretScheme.ENV: provider})
    refresher = _lazy(
        database,
        seed,
        resolver,
        tmp_path,
        subscription_id=seed.source_subscription_ids[0],
    )

    first = refresher.resolve(seed.locator)
    second = refresher.resolve(seed.locator)

    assert first.url == second.url == SIGNED_URL
    assert len(fake_detail_runner.instances) == 1
    runner = fake_detail_runner.instances[0]
    assert runner.constructor_kwargs == {
        "lock_path": tmp_path / "upstreams.lock.json",
        "integration_root": tmp_path / "runtime",
        "python_executable": tmp_path / "python",
        "license_acknowledged": True,
    }
    assert len(runner.calls) == 2
    request = runner.calls[0]
    assert request.account_id == seed.account_id
    assert request.subscription_id == seed.source_subscription_ids[0]
    assert request.platform is Platform.BILI
    assert request.content_remote_id == CONTENT_ID


@pytest.mark.parametrize(
    ("source_count", "explicit", "expected_code"),
    [
        (0, None, "locator_refresh_source_unavailable"),
        (2, None, "locator_refresh_source_ambiguous"),
        (1, uuid4(), "locator_refresh_source_mismatch"),
    ],
)
def test_zero_many_and_explicit_mismatch_sources_fail_with_fixed_codes_before_child_spawn(
    database: Database,
    tmp_path: Path,
    fake_detail_runner: type[_FakeMediaCrawlerDetailProcessRunner],
    source_count: int,
    explicit: UUID | None,
    expected_code: str,
) -> None:
    seed = _seed(database, source_count=source_count)
    provider = _RecordingSecretProvider({"MC_COOKIE": "cookie=value"})
    refresher = _lazy(
        database,
        seed,
        SecretResolver({SecretScheme.ENV: provider}),
        tmp_path,
        subscription_id=explicit,
    )

    with pytest.raises(MediaDownloadError) as caught:
        refresher.resolve(seed.locator)

    assert caught.value.code == expected_code
    assert fake_detail_runner.instances == []
    assert provider.calls == []


def test_cookie_and_subscription_policy_are_projected_into_the_detail_request(
    database: Database,
    tmp_path: Path,
    fake_detail_runner: type[_FakeMediaCrawlerDetailProcessRunner],
) -> None:
    seed = _seed(database, source_count=1)
    provider = _RecordingSecretProvider({"MC_COOKIE": "SESSDATA=runtime-cookie-sentinel"})
    refresher = _lazy(
        database,
        seed,
        SecretResolver({SecretScheme.ENV: provider}),
        tmp_path,
        subscription_id=seed.source_subscription_ids[0],
    )

    assert refresher.resolve(seed.locator).url == SIGNED_URL

    assert provider.calls == ["env:MC_COOKIE"]
    request = fake_detail_runner.instances[0].calls[0]
    assert request.login_method is LoginMethod.COOKIE
    assert request.cookie is not None
    assert request.cookie.reveal() == "SESSDATA=runtime-cookie-sentinel"
    assert request.headless is False
    assert request.request_delay_seconds == 7.25
    assert "runtime-cookie-sentinel" not in repr(request)


def test_construction_is_lazy_and_touches_neither_database_secret_nor_child(
    database: Database,
    tmp_path: Path,
    fake_detail_runner: type[_FakeMediaCrawlerDetailProcessRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = _RuntimeSeed(
        asset_id=uuid4(),
        locator=AdapterRefreshLocator(adapter="mediacrawler", asset_key="lazy-runtime-asset"),
        account_id=uuid4(),
        source_subscription_ids=(),
    )
    provider = _RecordingSecretProvider({"MC_COOKIE": "must-not-be-read"})

    def unexpected_session() -> None:
        raise AssertionError("database session opened before locator resolution")

    monkeypatch.setattr(database, "session", unexpected_session)
    refresher = _lazy(
        database,
        seed,
        SecretResolver({SecretScheme.ENV: provider}),
        tmp_path,
        subscription_id=None,
    )

    assert isinstance(refresher, LazyMediaCrawlerLocatorRefresher)
    assert provider.calls == []
    assert fake_detail_runner.instances == []


@pytest.mark.parametrize(
    (
        "platform",
        "content_remote_type",
        "asset_kind",
        "asset_position",
        "asset_remote_id",
        "source_url",
    ),
    [
        pytest.param(
            Platform.BILI,
            "content",
            AssetKind.COVER,
            0,
            f"{CONTENT_ID}:cover:0",
            None,
            id="bili-cover",
        ),
        pytest.param(
            Platform.BILI,
            "content",
            AssetKind.VIDEO,
            1,
            f"{CONTENT_ID}:video:1",
            None,
            id="bili-video-position-one",
        ),
        pytest.param(
            Platform.BILI,
            "article",
            AssetKind.VIDEO,
            0,
            f"{CONTENT_ID}:video:0",
            None,
            id="non-content-remote-type",
        ),
        pytest.param(
            Platform.BILI,
            "content",
            AssetKind.VIDEO,
            0,
            f"{CONTENT_ID}:video:wrong",
            None,
            id="wrong-video-remote-id",
        ),
        pytest.param(
            Platform.XHS,
            "content",
            AssetKind.VIDEO,
            0,
            f"{CONTENT_ID}:video:0",
            None,
            id="non-bili-video",
        ),
        pytest.param(
            Platform.BILI,
            "content",
            AssetKind.VIDEO,
            0,
            f"{CONTENT_ID}:video:0",
            SOURCE_HINT,
            id="bili-video-non-null-source",
        ),
    ],
)
def test_bili_progressive_source_shape_is_closed_before_secret_or_child(
    database: Database,
    tmp_path: Path,
    fake_detail_runner: type[_FakeMediaCrawlerDetailProcessRunner],
    platform: Platform,
    content_remote_type: str,
    asset_kind: AssetKind,
    asset_position: int,
    asset_remote_id: str,
    source_url: str | None,
) -> None:
    seed = _seed(
        database,
        source_count=1,
        platform=platform,
        content_remote_type=content_remote_type,
        asset_kind=asset_kind,
        asset_position=asset_position,
        asset_remote_id=asset_remote_id,
        source_url=source_url,
    )
    provider = _RecordingSecretProvider({"MC_COOKIE": "must-not-be-read"})
    refresher = _lazy(
        database,
        seed,
        SecretResolver({SecretScheme.ENV: provider}),
        tmp_path,
        subscription_id=seed.source_subscription_ids[0],
    )

    with pytest.raises(MediaDownloadError) as caught:
        refresher.resolve(seed.locator)

    assert caught.value.code == "locator_refresh_configuration_invalid"
    assert provider.calls == []
    assert fake_detail_runner.instances == []


def test_saved_session_detail_auth_expiry_is_fixed_and_persisted(
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ExpiredDetailRunner(_FakeMediaCrawlerDetailProcessRunner):
        def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
            self.calls.append(request)
            raise MediaDownloadError("locator_refresh_auth_expired")

    _ExpiredDetailRunner.reset()
    monkeypatch.setattr(runtime, "MediaCrawlerDetailProcessRunner", _ExpiredDetailRunner)
    seed = _seed(database, source_count=1, login_method=LoginMethod.SAVED_SESSION)
    refresher = _lazy(
        database,
        seed,
        SecretResolver({}),
        tmp_path,
        subscription_id=seed.source_subscription_ids[0],
    )

    with pytest.raises(MediaDownloadError) as caught:
        refresher.resolve(seed.locator)

    assert caught.value.code == "locator_refresh_auth_expired"
    request = _ExpiredDetailRunner.instances[0].calls[0]
    assert request.login_method is LoginMethod.SAVED_SESSION
    with database.session() as session:
        assert AccountRepository(session).require(str(seed.account_id)).auth_status == "expired"
