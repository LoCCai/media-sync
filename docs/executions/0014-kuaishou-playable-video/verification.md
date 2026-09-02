**English** | [中文](verification.zh.md)

# Execution 0014 verification

- Status: Offline implementation and closeout gates pass; live qualification remains `NOT_RUN`
- Environment: Windows, local workspace, Python environment resolved by `uv`
- Evidence date: 2026-08-31
- Plan commit: `95c7082`
- Implementation commit: `c4ab537`

## Starting baseline

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Existing ingestion, detail, refresh/runtime, downloader/network, Emby layout/application and generic offline pipeline | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/unit/test_media_downloader.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py tests/integration/test_emby_application.py tests/integration/test_offline_media_pipeline.py` | `0` | `PASS` — `211 passed in 27.81s` |

This baseline proves the predecessor Kuaishou normalizer/unit refresh cases and platform-neutral media machinery. It does not prove the pinned Kuaishou detail configuration, exact runtime provenance, video+cover transfer, Emby primary-media layout or platform-level replay.

## Focused implementation evidence

| Scope | Command | Exit | Result |
| --- | --- | ---: | --- |
| Kuaishou discovery/raw, pinned detail process, exact Account/Subscription refresh, video+cover download/probe/archive, Emby publication and replay | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_kuaishou_playable_pipeline.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py` | `0` | `PASS` — `228 passed in 25.49s` |

The focused gate proves exact video/cover remote IDs, positions, MIME/source hints and provenance; userinfo/query/fragment/nested-shape values absent from normalized raw, ORM and disposed SQLite/sidecars; a real fake checkout through the process runner; fixed missing/drift/duplicate outcomes; exact lazy Account/Subscription binding; the default request profile without Cookie or Authorization; deterministic MP4/PNG transfer, mandatory video probe, SHA-256 archive and Emby `.mp4`/poster/NFO/source publication. Query-only replay preserves generation and re-reads live counters to prove no second detail runner, HTTP, DNS or probe call.

## Complete root closeout gates

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Complete offline suite | `uv run pytest -q` | `0` | `PASS` — `1206 passed, 1 skipped in 269.21s` |
| Lint | `uv run ruff check .` | `0` | `PASS` — `All checks passed!` |
| Format | `uv run ruff format --check .` | `0` | `PASS` — `217 files already formatted` |
| Strict typing | `uv run mypy src/media_sync` | `0` | `PASS` — `Success: no issues found in 77 source files` |
| Documentation links | `uv run python scripts/check_docs.py` | `0` | `PASS` — `Documentation links OK (72 Markdown files checked)` |
| Pinned upstreams | `uv run python scripts/check_upstreams.py` | `0` | `PASS` — `Upstreams OK (2 locked checkouts verified)` |
| Source distribution and wheel | `uv build` | `0` | `PASS` — built `dist\media_sync-0.1.0.tar.gz` and `dist\media_sync-0.1.0-py3-none-any.whl` |
| Patch whitespace | `git diff --check` and `git diff --cached --check` | `0` | `PASS` — no output |

The single skip is `tests/contract/test_mediacrawler_supervision.py:556`: POSIX mode bits are not the Windows ACL boundary. It is environment-inapplicable, not a failed feature. No coverage command ran, so execution 0014 makes no coverage claim.

## Retained and ephemeral-data audit

The final read-only PowerShell audit enumerated tracked and standard-untracked files plus every real file below ignored `.media-sync` and `dist`. It rejected tracked/untracked runtime or credential paths, constructed three execution markers from split non-secret literals, byte-scanned Git-visible/runtime/build files without printing matched data, and verified that the frozen `0007`/`0008` sentinel roots still exist.

| Audit | Exit | Final counts |
| --- | ---: | --- |
| Git/runtime/build inventory and exact ephemeral-marker scan | `0` | `tracked=235`; `untracked=0`; `tracked_forbidden=0`; `suspicious_untracked=0`; `runtime_and_build_files=914`; `git_ephemeral_marker_hits=0`; `runtime_ephemeral_marker_hits=0`; `sentinel_roots_preserved=1` |

The end-to-end tests separately scan Author/Content/Asset raw and locators, Job/SyncRun payloads, disposed SQLite and sidecars, detail runtime, download/export work roots, archive, Emby library, source metadata and object representations. Dynamic known/unknown query, fragment, userinfo and nested-shape sentinels are absent from every durable sink.

## Live qualification

| Item | Status |
| --- | --- |
| Real QR/Cookie/saved-session login | `NOT_RUN` |
| Real creator scan and incremental rerun | `NOT_RUN` |
| Real detail and signed CDN transfer | `NOT_RUN` |
| Real platform bytes through FFmpeg/ffprobe | `NOT_RUN` |
| Real Emby/Jellyfin scan and playback | `NOT_RUN` |

Offline fake checkout, mock DNS/HTTP and synthetic bytes do not promote any live row. Same-ID/same-origin/path byte replacement and injected detail-cleanup failure remain the explicit limitations recorded in `goal.md` and `progress.md`.
