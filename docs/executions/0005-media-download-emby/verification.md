**English** | [中文](verification.zh.md)

# Execution 0005 verification

- Verification date: 2026-08-30 10:45 +08:00
- Network/account policy: offline mock transports and generated files only
- Result: PASS for the complete offline scope

## Behavior evidence

The root closeout run executed the full suite and all focused gates below. Every listed behavior scope passed; exact aggregate counts and timings are recorded in the quality-gate table.

| Scope | Command or evidence | Final status |
| --- | --- | --- |
| Asset identity, replay and DB lifecycle | `tests/integration/test_database.py`, `tests/integration/test_sync_pipeline.py`, `tests/integration/test_mediacrawler_db_ingestion.py` | PASS |
| Legacy migration backfill and downgrade/re-upgrade identity cleanup | `tests/integration/test_packaged_migrations.py` | PASS |
| Locator and network boundary | `tests/unit/test_media_locator.py tests/unit/test_media_network.py` | PASS |
| Resume, limits, probe and archive | `tests/unit/test_media_downloader.py tests/unit/test_media_probe.py` | PASS |
| Download lock/scope, lease/reclaim and finalization recovery | `tests/unit/test_download_application.py tests/integration/test_asset_download_orchestration.py` | PASS |
| Emby layout, trusted predecessor and filesystem transaction | `tests/unit/test_emby_layout.py tests/contract/test_emby_export_contract.py` | PASS |
| DB publication chain, intent/result and empty/concurrent recovery | `tests/integration/test_emby_application.py` | PASS |
| Unified offline pipeline | `tests/integration/test_offline_media_pipeline.py` | PASS |
| CLI behavior | `tests/unit/test_cli.py` | PASS |
| Composite-key and credential-path secret sinks | `tests/unit/test_security.py tests/unit/test_media_locator.py tests/integration/test_secret_sinks.py tests/integration/test_packaged_migrations.py` plus final sentinel scan | PASS |

## Final quality gates

| Check | Exact final command | Status and evidence |
| --- | --- | --- |
| Locked dependencies | `uv sync --all-groups --locked` | PASS — 58 resolved, 43 audited |
| Lint | `uv run ruff check .` | PASS |
| Format | `uv run ruff format --check .` | PASS — 127 files |
| Strict types | `uv run mypy src/media_sync` | PASS — 57 source files |
| Full tests and coverage | `uv run pytest --cov=media_sync --cov-report=term` | PASS — 540 passed in 126.44s; 79% branch-aware total |
| Focused asset/downloader gate | `uv run pytest tests/integration/test_database.py tests/integration/test_sync_pipeline.py tests/integration/test_mediacrawler_db_ingestion.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_media_downloader.py tests/unit/test_media_probe.py tests/unit/test_download_application.py tests/integration/test_asset_download_orchestration.py -q` | PASS — 165 passed in 15.12s |
| Focused Emby/export gate | `uv run pytest tests/unit/test_emby_layout.py tests/contract/test_emby_export_contract.py tests/integration/test_emby_application.py tests/integration/test_offline_media_pipeline.py -q` | PASS — 88 passed in 34.44s |
| Focused CLI/secret gate | `uv run pytest tests/unit/test_cli.py tests/unit/test_security.py tests/integration/test_secret_sinks.py -q` | PASS — 132 passed in 7.06s |
| Build | `uv build` | PASS — sdist and wheel |
| Packaged migrations | `uv run pytest tests/integration/test_packaged_migrations.py -q` (includes source and unpacked-wheel checks | PASS — 5 passed in 6.21s |
| Documentation links | `uv run python scripts/check_docs.py` | PASS — 36 Markdown files |
| Pinned upstreams | `uv run python scripts/check_upstreams.py` | PASS — 2 locked checkouts |
| Patch whitespace | `git diff --check` | PASS — no output |
| Targeted sentinel behavior | `uv run pytest tests/integration/test_secret_sinks.py tests/integration/test_emby_application.py::test_export_omits_raw_locator_and_signed_url_sentinel tests/integration/test_asset_download_orchestration.py::test_transport_exception_sentinel_never_reaches_error_or_persistence -q` | PASS — 8 passed in 1.37s |
| Final artifact sentinel | Reproducible retained-artifact gate below | PASS — 7 passed; both byte scans zero-match |
| Runtime artifacts untracked | `git ls-files -- archive exports jobs .media-sync dist` and `git status --short -- archive exports jobs .media-sync dist` | PASS — both produced no tracked/scoped status output; retained gate root is ignored |

## Retained artifact sentinel gate

The root closeout retained all generated evidence below `.media-sync/verification/0005-final-sentinel-root`. It contains six SQLite files, one immutable archive tree, one Emby `library` export tree and captured pytest/operator output. The directory contains 21 files, 29 directories and 1,326,956 bytes. No real platform, CDN or Emby service was contacted.

```powershell
$verificationRoot = Join-Path $PWD '.media-sync\verification\0005-final-sentinel-root'
$pytestRoot = Join-Path $verificationRoot 'pytest-artifacts'
$outputPath = Join-Path $verificationRoot 'pytest-output.txt'
if (Test-Path -LiteralPath $verificationRoot) { throw "Verification root unexpectedly exists: $verificationRoot" }
New-Item -ItemType Directory -Path $verificationRoot | Out-Null
$started = Get-Date
uv run pytest tests/integration/test_secret_sinks.py tests/integration/test_offline_media_pipeline.py -q --basetemp $pytestRoot 2>&1 | Tee-Object -FilePath $outputPath
$pytestExit = $LASTEXITCODE
$elapsed = (Get-Date) - $started
if ($pytestExit -ne 0) { throw 'Sentinel tests failed' }
rg -a -F -- 'SENTINEL-runtime-signed-query-0005' $verificationRoot
$runtimeScanExit = $LASTEXITCODE
rg -a -F -- 'sentinel-secret-value' $verificationRoot
$secretSinkScanExit = $LASTEXITCODE
if ($runtimeScanExit -ne 1 -or $secretSinkScanExit -ne 1) { throw 'Sentinel scan matched or failed' }
git check-ignore -v -- .media-sync/verification/0005-final-sentinel-root
git status --short --untracked-files=all -- .media-sync/verification/0005-final-sentinel-root
git ls-files -- .media-sync/verification/0005-final-sentinel-root
```

Observed results:

```text
7 passed in 1.60s
pytest_exit=0
elapsed_seconds=2.49
runtime_scan_exit=1
secret_sink_scan_exit=1
.gitignore:31:.media-sync/  .media-sync/verification/0005-final-sentinel-root
```

For `rg`, exit `1` means a successful scan with zero matches; exit `0` would mean a leak and exit `2+` a scan failure. Scoped `git status` and `git ls-files` emitted no lines. The retained SQLite/archive/export roots and captured output therefore contain neither exact sentinel and are not tracked.

## Required behavioral conclusions

- Discovery replay preserves downloader-owned verified bytes; semantic replacement performs one explicit fenced generation reset.
- Complete legacy verified rows remain usable after `0003`; transient or incomplete legacy downloader state resets safely with `legacy_asset_reset`.
- Downgrading `0003` clears every asset download FK and generation-bound `asset_download` Job. A re-upgrade can create the same natural generation identities afresh. Succeeded Emby chain state and structurally valid closed publication-intent recovery state survive, while other non-succeeded Emby Jobs/records do not poison the next export.
- A same-work-root asset lock is held before database mutation through finalization. Lock contention and I/O-scope mismatch consume no attempt and change no job or asset state; durable scope fingerprints disclose no local path.
- Network work holds no SQLite transaction; stale lease/generation owners cannot verify an asset. An exact expired-but-unreclaimed token may renew, but renewal versus reclaim has only one CAS winner.
- Every redirect and resolved address is validated; resume and restart never append incompatible bytes.
- Audio/video cannot become verified without bounded structural `ffprobe` evidence.
- The archive ownership guard runs after copy/fsync/rehash and immediately before commit, including existing-blob reuse. Archive blobs are immutable and content-addressed; path/link violations present at operation time and detected leaf-identity replacement fail closed. Runtime roots and ancestors are trusted operator-controlled boundaries; malicious same-permission parent swaps are outside the 0.x threat model.
- A filesystem commit followed by database-finalization failure is recoverable from exact generation-bound evidence without network or a new attempt. `.part` cleanup happens only after atomic verification and cannot reverse success.
- A succeeded `export.emby` Job result, not a disk-discovered manifest, anchors publication scope, source/tree/manifest hashes, managed count and exact predecessor. The unique Job chain rejects forks/cycles/broken ancestry and supports `A → B → A`.
- First publication rejects an unexpected managed manifest. A self-consistent forged manifest cannot claim an unmanaged user file. Already-exported replay verifies the database-anchored manifest identity and every managed byte.
- Pre-publish Job intent permits exact publish-success/database-finalize recovery. Empty snapshots remain anchored with zero ExportRecords; concurrent sibling publications leave one winner and one retryable stale loser.
- Repeated Emby export is byte-deterministic. Before success, journaled publication revalidates every desired managed file and the manifest while the author lock and recovery evidence remain held. Interrupted-transaction roll-forward applies the same complete-tree rule; mismatch retains the journal and `RECOVERY_REQUIRED`. Concurrent or user-modified target/manifest files are never silently overwritten or deleted, including rollback paths.
- Composite API/access-key mapping names are redacted across snake_case, kebab-case, camelCase and provider-prefixed forms without erasing ordinary `key`, `public_key` or `key_id` values. Credential-marker URL paths are removed in raw, encoded and double-encoded forms, rejected by `direct` and source-hint derivation, and converted to secret-free `adapter_refresh` state during both current ingestion and `0003` legacy backfill. Injected values do not survive into SQLite bytes, archive/export trees or operator errors. Benign redacted raw envelopes remain deliberately stored in SQLite for re-normalization, but raw envelopes and locators are never exported.
- Unsupported refresh and missing mandatory probe CLI preflights return `blocked`/`not_started` with unchanged `persisted_status`, create no Job and mutate no Asset.

## Live qualification

| Target | Status | Reason |
| --- | --- | --- |
| XHS, Douyin, Kuaishou, Bilibili, Weibo, Tieba and Zhihu QR/Cookie/saved-session login and creator sync | `NOT_RUN` | No user-authorized account or interactive challenge was used |
| Seven-platform signed-locator refresh and live CDN download | `NOT_RUN` | No CDN traffic was authorized; MediaCrawler refresh is not implemented |
| Emby/Jellyfin rescan and playback | `NOT_RUN` | No server was started or modified |

Automated downloader/export tests must never promote these rows.

Phone login exposure, MediaCrawler refresh, platform-specific DASH/multi-part/subtitle/danmaku or slideshow/mux derivatives, scheduler/rate limiting/backoff, REST operations, Docker and production operations are unavailable or deferred implementation scope, not `NOT_RUN` qualification results.
