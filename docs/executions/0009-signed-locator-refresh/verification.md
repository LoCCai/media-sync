**English** | [中文](verification.zh.md)

# Execution 0009 verification

- Verification state: `FUNCTION-FIRST MVP / PASSING OFFLINE FOCUSED GATES`
- Planning date: 2026-08-30
- Network/account policy: offline fake pinned-upstream modules, repository-owned local helpers and mock HTTP only; no browser connected to a platform, real credential, platform/CDN endpoint or Emby/Jellyfin server
- Implementation state: `MVP IMPLEMENTED` — provenance, cleanup, detail refresh, lazy runtime and CLI wiring verified offline

This file preserves the historical pause evidence and current results. Migration, ingestion, cleanup, functional locator refresh and CLI wiring are implemented; full-suite/build, retained-sentinel and live rows remain open.

This file is the frozen verification contract of execution 0009, not implementation evidence. The planning-baseline document checks are recorded separately; no migration, refresh, cleanup, signed-sentinel or live row is promoted before exact commands and results are recorded.

## Planning-baseline checks

The following rows qualify only the committed goal/plan/progress/verification baseline. They do not execute behavior.

| Check | Exact command | Result |
| --- | --- | --- |
| Documentation links | `uv run python scripts/check_docs.py` | PASS — `Documentation links OK (52 Markdown files checked).` |
| Locked upstreams | `uv run python scripts/check_upstreams.py` | PASS — `Upstreams OK (2 locked checkouts verified).` |
| Patch whitespace | `git diff --check` | PASS — exit `0`, no output |

## Executed pause-checkpoint checks

| Check | Exact command | Result |
| --- | --- | --- |
| Modified-source lint | `uv run ruff check src/media_sync/infrastructure/db/__init__.py src/media_sync/infrastructure/db/models.py src/media_sync/infrastructure/db/repositories.py src/media_sync/infrastructure/db/migrations/versions/0005_asset_refresh_sources.py src/media_sync/scheduler/mediacrawler_handler.py` | PASS — `All checks passed!` |
| Focused cleanup truth | `uv run pytest -q tests/integration/test_mediacrawler_scheduler_handler.py::test_empty_normalized_delta_is_a_successful_guarded_checkpoint tests/integration/test_mediacrawler_scheduler_handler.py::test_committed_sync_run_truth_wins_over_invalid_returned_summary` | PASS — `2 passed in 1.21s` |
| Strict types | `uv run mypy src/media_sync` | FAIL — 3 errors at handler lines 727/730/731: `SyncRun | None` assigned to `UUID | None`, then UUID accessed as `subscription_id` and `attempt` |
| Migration focused nodes | `uv run pytest -q tests/integration/test_database.py::test_alembic_upgrade_matches_metadata_and_downgrades tests/integration/test_packaged_migrations.py::test_programmatic_upgrade_uses_packaged_resources_and_handles_percent_path` | FAIL — `2 failed`; `DOMAIN_TABLES` omits `asset_refresh_sources`, and tests/CLI still hard-code head `0004_scheduler_control_plane` instead of `0005_asset_refresh_sources` |
| Full handler file | `uv run pytest -q tests/integration/test_mediacrawler_scheduler_handler.py` | FAIL — `9 failed, 43 passed in 25.27s`; seven platform cases still expect successful attempt roots retained, heartbeat reads a now-cleaned snapshot, and valid recovery expects the receipt retained |
| Patch whitespace | `git diff --check` | PASS — exit `0`, no output |

The full pytest/coverage suite, build, wheel smoke, signed sentinel and authoritative retained gate were deliberately not run before pausing. The 0009 retained root was not created; the 0007/0008 retained roots were not touched.

## Resumed tranche checks

| Check | Exact command | Result |
| --- | --- | --- |
| Merged lint | `uv run ruff check <12 changed migration/ingestion/cleanup source and test files>` | PASS — `All checks passed!` |
| Strict types | `uv run mypy src/media_sync` | PASS — `Success: no issues found in 65 source files` |
| Migration/ingestion/cleanup regression | `uv run pytest -q <4 migration nodes> tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_scheduler_handler.py tests/contract/test_mediacrawler_supervision.py` | PASS — `87 passed, 1 skipped in 44.51s`; the skip is the documented Windows/POSIX mode-bit boundary |
| Downloader re-resolution | `uv run pytest -q tests/unit/test_media_downloader.py` and `uv run pytest -q tests/unit/test_download_application.py tests/integration/test_asset_download_orchestration.py` | PASS — `45 passed` plus `39 passed`; adapter refresh re-resolves once after 401/403 and direct locators remain unchanged |
| Patch whitespace | `git diff --check` | PASS |

These checks qualify only the resumed provenance/cleanup tranche. They do not claim a working locator refresh, platform traffic, CDN download or Emby scan.

## Function-first refresh checks

| Check | Exact command | Result |
| --- | --- | --- |
| Detail refresher unit + fake-child contract | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py` | PASS — `20 passed` |
| Locator/normalizer/download regression | `uv run pytest -q tests/unit/test_media_locator.py tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_asset_download_orchestration.py` | PASS — `111 passed` |
| Lazy exact-source runtime | `uv run pytest -q tests/integration/test_mediacrawler_download_runtime.py` | PASS — `6 passed`; covers exact 1, 0/N, explicit mismatch, Cookie/policy context and zero-work construction |
| CLI asset download wiring | `uv run pytest -q tests/unit/test_cli.py -k "asset_download"` | PASS — `5 passed`; default-off, license block, ffprobe behavior and explicit lazy-refresher construction |
| Changed-code lint | `uv run ruff check src/media_sync/application/mediacrawler_download.py src/media_sync/integrations/mediacrawler/detail_runner.py src/media_sync/integrations/mediacrawler/refresh.py src/media_sync/interfaces/cli.py src/media_sync/media/errors.py tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/unit/test_cli.py` | PASS — `All checks passed!` |
| Strict types | `uv run mypy src/media_sync` | PASS — `Success: no issues found in 70 source files` |

All rows above are offline. The fake child imports a repository-owned fake checkout; no real platform browser, credential, CDN request, Emby/Jellyfin request or Git network operation occurred.

## Planned behavior evidence

| Scope | Required evidence | Status |
| --- | --- | --- |
| Migration and backfill | Head/round-trip/FKs/indexes; exact platform/author/adapter/stable-key unique inference; ambiguous/malformed/corrupt cases unbound; existing recovery identities preserved | `PASS (focused)` |
| Ingestion observation | Same transaction as Asset/checkpoint; wrong-run/cross-relation rollback; older-run replay cannot regress `(created_at,id)` last-run order/timestamps; multi-account; both replacement kinds advance generation; archive-reset eligibility | `PASS (focused)` |
| Source selector | No-Job 0/1/N; existing-Job authority; explicit mismatch; shared-lock second filesystem-block check catches post-first-read writer before SecretResolver/claim/attach/prepare/spawn; no FS I/O in transaction | `PASS (MVP 0/1/N + explicit)` — immutable existing-Job binding and full TOCTOU hardening deferred |
| Recovery ordering | Read-only inspection zero-mutation; valid verified result needs no source/profile/credential; prepared recovery only bound CAS/finalization; both zero child/HTTP/new attempt | `NOT_RUN` |
| Job source/config binding | Existing natural key and `run_id = NULL`; closed ID/platform/fingerprint payload omits observation kind; legacy-to-ingested upgrade preserves retry Job; retry/running/prepared source immutable; transactional config identities exact after secret resolution | `NOT_RUN` |
| Private child protocol | Dedicated pipe/handle; strict frame/error matrix; shared account lock spans child-tree join, HTTP/finalization and cleanup; every cleanup-block writer uses same fence; parent death/cancel | `PASS (MVP fake child)` — bounded stdout frame, cleanup and process supervision pass; dedicated side pipe/full lock matrix deferred |
| Platform selectors | Exact stored hint required; XHS creator secret/author/token/source, 4 x 30/120-second bound and fixed invalid/expired/not-found/schema/timeout dispositions; DY/KS/Bili shapes; WB/Tieba/Zhihu no spawn | `PASS (MVP shapes)` — DY/KS/Bili and explicit XHS detail URL; automatic XHS feed lookup deferred |
| Candidate identity | Child validates semantics; full-request fingerprint binds response; query-free hint selects exactly one; same-kind ambiguity and position-only matching fail closed | `NOT_RUN` |
| Downloader | Signed URL reaches mock HTTP only; one 401/403 re-resolve; direct unchanged; resume safe; metadata/redirect headers unchanged | `PASS (offline focused)` — functional MediaCrawler resolver wired |
| Terminal cleanup | Non-empty fresh/recovered sentinels and exact restart source; after real success commit inject malformed result, readback error/mismatch, all four states, repeated cancel/lease loss/restart and assert zero failure mutation/reingest; deterministic recovery identity and concurrent disappearance | `PASS (focused)` — exhaustive retained sentinel deferred |
| Secret sinks | Private-pipe + mock-request observation, then exact post-cleanup filesystem/SQLite/operator/JUnit zero-match with named negative exclusions | `NOT_RUN` |

## Planned quality gates

Exact focused nodes, case counts, timings and retained-sentinel statistics will be finalized only after implementation. Every result remains `NOT_RUN` until the final invocation and material output are recorded.

| Check | Planned command or scope | Status |
| --- | --- | --- |
| Locked dependencies | `uv sync --all-groups --locked` | `NOT_RUN` |
| Lint | `uv run ruff check .` | `PARTIAL` — all 0009 changed files PASS; whole tree still `NOT_RUN` |
| Format | `uv run ruff format --check .` | `NOT_RUN` |
| Strict types | `uv run mypy src/media_sync` | PASS — 70 source files |
| Full branch-aware suite | `uv run pytest --cov=media_sync --cov-report=term` | `NOT_RUN` |
| Focused refresh/cleanup gate | Exact unit/contract/integration/migration nodes | `PASS (function-first MVP)` — provenance, cleanup, refresh runtime and CLI wiring |
| Build and wheel smoke | `uv build` plus clean wheel install/import/CLI checks | `NOT_RUN` |
| Packaged migrations/resources | Head inventory and round-trip tests | `PASS (focused)` — `0005` head/resource/round-trip |
| Documentation | `uv run python scripts/check_docs.py` | PASS — 56 Markdown files |
| Pinned upstreams | `uv run python scripts/check_upstreams.py` | PASS — 2 locked checkouts |
| Patch whitespace | `git diff --check` | PASS |
| Runtime artifacts untracked | Scoped ignore, `git ls-files` and `git status` checks | `NOT_RUN` |
| Fresh retained sentinel | `.media-sync/verification/0009-refresh-sentinel-root` exact allowlist/scans | `NOT_RUN` |

## Planned retained-artifact rules

- The 0009 retained root must not exist before its one authoritative run and must never be deleted or recreated afterward. The 0007 and 0008 roots remain untouched read-only evidence.
- Use an exact safe-test allowlist, never module-level `-k` subtraction. Name every profile/quarantine/unresolved or deliberate raw-fixture case excluded from whole-tree zero-match evidence.
- Prove a generated signed sentinel entered the dedicated private pipe and mock HTTP request. Separately prove post-collection dynamic sentinels existed in non-empty fresh/recovered JSONL source roots before exact cleanup, and bind already-succeeded restart to the same exact source identity. Do not put values in source, pytest IDs, assertions, JUnit properties or operator strings.
- Validate every Windows pytest `current` alias as an existing same-parent in-root target and independently enumerate/scan every real target.
- Final traversal, content/path scan and SQLite main/sidecar/logical scan fail closed on any unreadable, locked, nonregular, reparse or traversal condition.

## Live qualification

| Platform | QR login | Cookie login | Saved session | Creator/detail refresh | Live CDN | Real Emby/Jellyfin |
| --- | --- | --- | --- | --- | --- | --- |
| `xhs` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `dy` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `ks` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `bili` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `wb` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `tieba` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `zhihu` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

Phone login remains unsupported. Offline fake-detail evidence never changes this table.

## Deferred implementation

The durable automatic `sync → download → Emby` DAG is execution 0010. QR UX, credential-bearing CDN headers, Bilibili playable derivatives, Weibo/Tieba/Zhihu Asset discovery, per-request upstream spacing, REST, resident supervision, Docker and HA/PostgreSQL remain deferred. Persistent unresolved cleanup blocks require later explicit operator repair/acknowledgement and are never silently cleared.
