**English** | [中文](verification.zh.md)

# Verification

Fresh fetch: HEAD/origin `76165b0`, divergence0 0, clean worktree. Locked MediaCrawler d6f7c5bb906b6dac40ddf343ef9e26438a3de092 and bili-sync-up dcb5bb73b56ac45b2525da14b389e185b0ea6dbd remain unchanged. Read-only source discovery used local files and public GitHub/raw fixed-SHA files only, no target-platform requests or credentials. No new tests have run at plan freeze; 0061 results are historical and not inherited.

Exploratory PowerShell searches using literal wildcard path arguments were rejected by rg, and one guessed subscriptions.py path did not exist; corrected by listing actual files and reading subscription_policy.py. These were non-mutating source-discovery errors, not product test failures. Full verification results will be appended as work proceeds.

## Implementation checks and actual failures (not final-source full suite)

- Parallel bridge initially imported not-yet-written multifeed, blocking child pytest collection; recovered once the module landed. Parser tests first had3 strip expectation failures, then5 immutable mapping/tuple expectation failures; test expectations were corrected without changing domain semantics.
- Root first existing Bili bridge/ingestion/scheduler/CLI selection:77 passed,1 failed because rejecting a legacy policy raised a different exception; restored RepositoryError. New bridge selection first5 failed/32 passed (synthetic item omitted visible=True), then5 failed/5 passed (test reused a sealed attempt); using a separate continuation manifest yielded5 passed/8.90s.
- New scheduler first2 failed/22 passed: test runner was async and checked nonexistent outcome; corrected to real synchronous runner/status, then2 passed/7.99s. No production calls.
- Parser/capture/normalizer selection284 passed/4.47s; multifeed/policy/original-scan154 passed; initial refresh53 passed/1.84s and independent existing refresh checks70 passed/4.39s. These overlap and are implementation snapshots, never summed. Additional review repros still found missing buvid3 gate, unnecessary OPUS requests before unsupported rejection, repeated nav and generic unsupported classification, requiring corrections.
- Root dynamic+original CLI/scheduler selection23 passed/61.95s; scope successful-readback correction+original bounded ingestion32 passed/3.95s. Subsequent explicit scope/transaction fences require final rerun.
- Intermediate whole Web640 passed (the attempted file-filter argument did not narrow the selection); Svelte0 errors/0 warnings. More UI tests followed, so this is not the final Web count. Ruff line/import and mypy nullable errors were corrected incrementally. A succeeding static command following failed pytest in one shell invocation is not treated as a passing aggregate.

Final source freeze, latest regression, packaging, environmental skips and publication are recorded separately below. None of this qualifies Docker/Linux, PostgreSQL or real login/capture/download/Emby playback.

## Independent review corrections and directory snapshots

- Refresh-agent intermediate selection:480 passed/4 failed/120.49s; four tests expected the wrong exception at the new boundary. Corrected pipeline14 passed, then final refresh/detail/pipeline selection139 passed/10.65s. These overlap, not summed.
- Scope review reproduced stale v1 zero-record artifact publication after a v2 scope edit. CLI now explicitly checks v1 None and v2 scopes, and the transaction distinguishes omitted legacy direct-call scope from explicitly supplied None. The load-to-Run-creation race and successful replay after scope/max_items edits have regression coverage; intermediate scope/fences/capabilities/API52 passed/16.07s with one existing warning.
- Snapshot review reproduced an incomplete final digest blob after process death. Private complete-file fsync plus atomic no-replace publication and directory fsync replace direct final writes. Independent final selection72 passed/1 POSIX skip/17.98s includes real subprocess death before/after publication and mid-write; POSIX primitives are not executed on Windows.
- Final classification correction makes dynamic unsupported/identity/schema errors terminal without account-circuit impact;49 focused tests passed/1.31s.

Complete directories were started before the last snapshot/classification corrections, so all three reports are **intermediate directory snapshots**, not latest-source full-suite evidence:

| Directory command | Actual result | Local report |
| --- | --- | --- |
| `python -m pytest tests/unit -q --tb=short` |3303 passed,1 failed,1 skipped,1 existing warning /295.86s|`artifacts/directory-unit-snapshot.xml`|
| `python -m pytest tests/contract -q --tb=short` |812 passed,2 skipped /423.23s|`artifacts/directory-contract-snapshot.xml`|
| `python -m pytest tests/integration -q --tb=short` |1001 passed,33 skipped /384.55s|`artifacts/directory-integration-snapshot.xml`|

Each command also used `--junitxml` under this execution's artifacts directory; the original final-* names were renamed to directory-*-snapshot after source changes. The sole unit failure was the auth inventory assertion still expecting66 routes after adding route67. Corrected name/count retain the exact public allowlist and deny-by-default checks for every route; the full auth file then passed20/9.40s with one existing Starlette/httpx deprecation warning. Reports are retained locally under docs and ignored by the established artifact policy; reproducible commands, outcomes and the final file selection are committed. They contain no production execution evidence.

## Frozen-source static, Web and packaging gates

Final application-source freeze includes the snapshot crash and non-circuit classification changes. `bilibili_multifeed.py` SHA256 is `8b7ad3afca4876b8fc5b20e788b81c4ac7efa7287817724de6eeb2d525782509`.

- `ruff check src tests scripts`:PASS; `ruff format --check src tests scripts`:325 files unchanged; `mypy src/media_sync`:130 source files PASS; `python -m compileall -q src tests scripts`:PASS.
- `uv lock --check`:62 packages, unchanged; `python scripts/check_upstreams.py`:two locked clean checkouts PASS. No dependency/lock/schema migration changes.
- Final Web `pnpm check`:0 errors/0 warnings; `pnpm test`:642 passed; `pnpm build`:PASS (build9.55s); subsequent `pnpm format:check`:PASS. No later Web edits. No new browser or production interaction.
- Independent `uv build` in a fresh temporary directory built sdist then wheel from that sdist. Both contain all144 current application Python files (2,838,221 bytes), each byte-identical to source; missing/extra/mismatch0. Named source-tree digest:`a45097974b8417b8e87077e2791f39f796c80c611782680cb2ec3e621a0df35f`.
- Wheel:151 members,635,968 bytes,SHA256 `e1970bf9e8bd0a88c4b7526076a5e68390db5be99434147ec26d21d89f4f551d`. Sdist:1068 members,2,585,459 bytes,SHA256 `3128fe193618fd2743cbb7bf36a8b6aac3e10e6aa5943a4a23b849f8842b1d70`. CLI entry and Python>=3.11,<3.14 metadata match. Unsafe/member collisions/link/special/private-runtime-name candidates0; this is member-name/source-byte audit, not a comprehensive content-secret scan. Sdist docs are the build-time snapshot, not later verification additions. Temporary packages are not release attachments or deployment evidence.

Docker is unavailable and `MEDIA_SYNC_TEST_POSTGRESQL_URL` is unset. Linux/macOS native filesystem durability, real PostgreSQL races, current container, platform requests/CDN bytes, operator login, real capture, native Emby/Jellyfin playback and supervisor operation were NOT_RUN. Prior authorized failed Bili canary is not retested or relabeled PASS.

## Final frozen-source affected regression

The34 files in [affected-tests.txt](affected-tests.txt) ran together against the frozen application source: **1250 passed,15 skipped,1 existing warning in340.04s**. Skips are13 real-PostgreSQL ownership cases and2 Windows-inapplicable POSIX cases; warning is the existing Starlette/httpx deprecation. No failures. This includes all new0062 tests, upload compatibility, scope/edit/replay races, scheduler/ownership/security and the67-route auth inventory; it is not a fresh all-directory run. No source or test edits followed.

Reproduce from repository root in PowerShell (the committed file contains exactly the executed selection):

```powershell
$affectedTests = Get-Content docs/executions/0062-bili-dynamic-workflow/affected-tests.txt
.venv/Scripts/python.exe -m pytest @affectedTests -q --tb=short --junitxml=docs/executions/0062-bili-dynamic-workflow/artifacts/final-affected.xml
```

Local report SHA256:final affected `2353b945d6f39219d002721e7ed3adba19e7b206b0feaa1a4d36723f16d6a970`; directory unit `debdea55f1b594491dae229860f07e265ba6eaf02d3a2148d191f5e7ee8bc344`; contract `3c2e91f6d8032679e5d3e09012626d87c2b1bdf3f0068637fc327b3bb8530ec3`; integration `1d5ed212a96f99d762fa74cdd3616799aa75680594808231381a2fe8928dca01`. Timestamps/timing make future report hashes differ normally. `python scripts/check_docs.py` passed632 Markdown files and `git diff --check` passed. Fresh fetch before staging found local plan commit ahead1/behind0; publication follows separately.
