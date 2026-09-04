from __future__ import annotations

import pytest

from media_sync.application.media_server_publication import (
    MediaServerPublicationTarget,
    _join_server_path,
    media_server_publication_fingerprint,
    media_server_selector_fingerprint,
)
from media_sync.exporters.emby import ExportAuthor, PublishedIdentity
from media_sync.ports.media_server import MediaServerLookupTarget


@pytest.mark.parametrize(
    ("root", "expected_style", "expected_path"),
    [
        ("/srv/media", "posix", "/srv/media/xhs-creator-author"),
        ("C:/Media", "windows", r"C:\Media\xhs-creator-author"),
        (r"\\server\share\Media", "windows", r"\\server\share\Media\xhs-creator-author"),
    ],
)
def test_server_path_join_uses_explicit_remote_syntax(
    root: str,
    expected_style: str,
    expected_path: str,
) -> None:
    assert _join_server_path(root, "xhs-creator-author") == (expected_style, expected_path)


@pytest.mark.parametrize(
    "root",
    [
        r"/srv/media\mixed",
        r"C:\Media/mixed",
        "//server/share/ambiguous",
        "relative/media",
    ],
)
def test_server_path_join_rejects_mixed_ambiguous_and_relative_roots(root: str) -> None:
    with pytest.raises(ValueError):
        _join_server_path(root, "xhs-creator-author")


def test_publication_target_repr_omits_raw_selectors() -> None:
    target = MediaServerPublicationTarget(
        author_id="00000000-0000-0000-0000-000000000001",
        publication_job_id="00000000-0000-0000-0000-000000000002",
        platform="xhs",
        provider_key="media-sync-xhs-creator",
        provider_value="private-remote-id-sentinel",
        author_relative_directory="private-author-directory-sentinel",
        server_path="/private/server/path/private-author-directory-sentinel",
        server_path_style="posix",
        publication_fingerprint="a" * 64,
        selector_fingerprint="b" * 64,
        managed_file_count=3,
    )

    rendered = repr(target)
    assert isinstance(target, MediaServerLookupTarget)
    assert str(target) == rendered
    assert target.provider_value == "private-remote-id-sentinel"
    assert target.remote_id == "private-remote-id-sentinel"
    assert "private-remote-id-sentinel" not in rendered
    assert "private-author-directory-sentinel" not in rendered
    assert "/private/server/path/private-author-directory-sentinel" not in rendered
    assert "media-sync-xhs-creator" in rendered


def test_publication_fingerprint_has_a_stable_canonical_vector() -> None:
    fingerprint = media_server_publication_fingerprint(
        author_id="00000000-0000-0000-0000-000000000001",
        publication_scope="d" * 64,
        author=ExportAuthor("xhs", "remote-author", "Display", "@handle"),
        current_source_fingerprint="a" * 64,
        publication_job_id="00000000-0000-0000-0000-000000000002",
        predecessor_job_id=None,
        publication_identity=PublishedIdentity("a" * 64, "b" * 64, "c" * 64),
        managed_file_count=3,
    )

    assert fingerprint == "c407661f33c6c61576f7f6391230840f22ba139ee07af59591d82fad0d9eb961"


def test_selector_fingerprint_is_stable_and_binds_raw_selector_fields() -> None:
    baseline = MediaServerLookupTarget(
        provider_key="media-sync-xhs-creator",
        provider_value="remote-author",
        server_path="/srv/media/xhs-author",
    )
    expected = media_server_selector_fingerprint(
        profile_fingerprint="e" * 64,
        publication_fingerprint="f" * 64,
        target=baseline,
    )

    assert expected == "e7aed626745f6a899bd828cc980f655165cc654932a23b90a2c670c6652173e2"
    assert (
        media_server_selector_fingerprint(
            profile_fingerprint="e" * 64,
            publication_fingerprint="f" * 64,
            target=baseline,
        )
        == expected
    )
    assert (
        media_server_selector_fingerprint(
            profile_fingerprint="e" * 64,
            publication_fingerprint="f" * 64,
            target=MediaServerLookupTarget(
                provider_key="media-sync-xhs-creator",
                provider_value="other-author",
                server_path=baseline.server_path,
            ),
        )
        != expected
    )
    assert (
        media_server_selector_fingerprint(
            profile_fingerprint="e" * 64,
            publication_fingerprint="f" * 64,
            target=MediaServerLookupTarget(
                provider_key="media-sync-xhs-creator",
                provider_value=baseline.provider_value,
                server_path="/srv/other/xhs-author",
            ),
        )
        != expected
    )
