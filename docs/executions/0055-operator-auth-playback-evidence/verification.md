**English** | [中文](verification.zh.md)

# Execution 0055 Phase A verification

- Status: Backend authentication, observation identity/ledger and browser-only confirmation published; bounded author projection and qualification v3 pass full regression, with final publication gates in the child checkpoint
- Date: 2026-09-05
- Planning baseline: `d0a8cc2`; authentication implementation baseline: `4564b2a`
- Published authentication commit: `f19bfaa`
- Published persistence commit: `1d5b448`
- Published confirmation commit: `13de3b7`; projection frozen planning commit: `9fd74de`
- Current revision: `0008_playback_evidence`

## Evidence policy

Planning checks establish scope against the code at that time. The sections below retain historical authentication evidence for `f19bfaa`, observation identity/persistence for `1d5b448`, and confirmation writes for `13de3b7`; current focused/full-regression and publication evidence for bounded author projection and qualification v3 lives in the [child verification](evidence-projection/verification.md). Offline evidence does not prove the missing Web login/confirmation surface, current Linux-image usability, real-server compatibility or authorized playback. Historical no-P0/P1/P2 findings within those review scopes do not close the Web, credential-readability or pre-migration-validation issues in the [delivery review](delivery-priorities.md). Implementation evidence and live qualification remain separate.

## Planning baseline evidence

| Check | Command or source | Status |
| --- | --- | --- |
| Git synchronization | `git fetch --prune origin`; compare `HEAD...origin/main` | `PASS` — both at `d0a8cc2`, divergence `0 0` before planning edits |
| Initial worktree | `git status --short` | `PASS` — only pre-existing untracked `.mimosa/` after the 0054-B closeout |
| Prior frozen gate | Execution 0054-B verification | `PASS` — 2763 Python tests passed with 3 skips and 1 existing warning, including 11 real-PostgreSQL Operation races; 69 Web tests and all recorded quality gates passed |
| Route inventory | Inspect `create_api_app` and `app.routes` | `PASS` — 51 baseline routes; no auth dependency or middleware; sensitive route classes recorded in the goal/plan |
| Secret/redaction reuse | `config.py`, `security/secrets.py`, `security/redaction.py` | `PASS` — typed env/file/keyring references and value-safe wrappers exist; no operator auth setting exists |
| Publication/evidence reuse | Publication resolver, observation service, qualification schema v2, DB models/migrations | `PASS` — complete publication authority and safe item fingerprints exist; there is no authenticated playback ledger |
| Scope review | 0053/0054 remaining-work records and security review | `PASS` — operator authentication and playback evidence belong to 0055; destructive/writable administration remains separately unfrozen |
| Bilingual planning set | Review the four English/Chinese goal, plan, progress, and verification pairs | `PASS` — eight files preserve the same frozen scope and explicitly state that implementation has not started |
| Documentation and upstreams | `uv run --frozen python scripts/check_docs.py`; `uv run --frozen python scripts/check_upstreams.py` | `PASS` — 498 Markdown files have valid links and both locked upstream checkouts match their pins |
| Intended tracked set | Root generated/runtime denylist over the current 787 tracked files plus the eight new execution files | `PASS` — intended post-commit count is 795; no forbidden output is selected and pre-existing `.mimosa/` remains untracked |
| Confidentiality and workspace paths | Scan the 14 intended changed/new files for workstation paths, private-key/token forms, and assigned secret values | `PASS` — zero matches |
| Whitespace | `git diff --check` | `PASS` |

## Published backend authentication evidence

Every result in this section is retained as historical evidence for pushed commit `f19bfaa`. It must not be read as a completed full-regression claim for the newer commit-3 worktree.

| Check | Command or source | Status |
| --- | --- | --- |
| Remote refresh | `git fetch --prune origin`; compare before the implementation commit | `PASS` — retry succeeded after one transient GitHub TLS EOF; the planning commit remained the common baseline |
| Auth/config/API focused union | `uv run --frozen pytest -q` over config, three operator-auth modules, and all seven existing API modules | `PASS` — 190 passed in 41.99s; one pre-existing Starlette/httpx deprecation warning |
| Runtime/origin regressions | `tests/unit/test_operator_auth.py` | `PASS` — includes deterministic old-credential login versus rotation, exact loopback/non-loopback origin posture, Host/auth/CSRF/Bearer precedence, limiter, expiry/logout, strict extractors, and deny-before-handler behavior |
| API boundary regressions | `tests/unit/test_operator_auth_api.py` | `PASS` — 57 route objects enumerated; exact anonymous method/path table only, strict login body including recursive JSON, write-only OpenAPI input, cookie flags, browser-only routes, and raw-ASGI legacy HEAD body suppression |
| Browser-realistic API helper | `tests/unit/_api_client.py` plus the seven existing API modules | `PASS` — Origin/CSRF is injected only for unsafe methods; direct QR/archive GET/HEAD/Range and SSE paths rely on same-origin session cookies without Authorization or URL tokens |
| Fail-before-bind/Compose topology | `tests/unit/test_operator_auth_cli.py`; inspect `docker-compose.example.yml` | `PASS` for code — missing/unresolved/weak credentials and missing wildcard-bind origin stop before bind; explicit `0.0.0.0` plus host-loopback HTTP origin succeeds. Compose now mounts a credential secret and declares that origin |
| Docker Compose executable check | `docker compose -f docker-compose.example.yml config --quiet` | `NOT_RUN` — Docker CLI is not installed on this workstation; no container-start claim is made |
| Static typing | `uv run --frozen mypy --strict src/media_sync` | `PASS` — 104 source files, zero errors |
| Complete Python regression | `uv run --frozen pytest -q` | `PASS` — 2811 passed, 14 skipped, 1 warning in 561.43s. Three skips are Windows-inapplicable POSIX launcher/mode cases; 11 are existing real-PostgreSQL Operation races because `MEDIA_SYNC_TEST_POSTGRESQL_URL` is unset; the warning is the existing Starlette/httpx deprecation |
| Web regression and build | `npm run format:check`; `npm test -- --run`; `npm run check`; `npm run build` in `web/` | `PASS` — formatting clean, 7 files/69 tests pass, Svelte reports zero errors/warnings, and the static production build completes. These existing tests do not claim the still-unimplemented Web login client |
| Whole-repository quality | `uv run --frozen ruff check .`; `ruff format --check .`; strict mypy; `python -m compileall -q src tests` | `PASS` — all checks pass, 722 files formatted, 104 typed source files clean, and byte-compilation clean |
| Docs and locked upstreams | `scripts/check_docs.py`; `scripts/check_upstreams.py` | `PASS` — 498 Markdown files and both locked checkouts verified |
| Distribution | isolated `uv build --out-dir ...`; inspect wheel/sdist with `zipfile`/`tarfile` | `PASS` — one wheel and one sdist build; wheel has 121 entries including auth, legacy console, and migration template; sdist has 832 entries; neither contains `.env`/SQLite output |
| Pre-commit repository gate | explicit 46-file index; `git ls-files`; generated/runtime and sensitive-pattern scans; frozen goal/plan diff; `git diff --cached --check`; compare `HEAD...origin/main` | `PASS` — 800 indexed files, zero forbidden output or sensitive match, frozen goal/plan unchanged, divergence `0 0`, no unstaged tracked change, and only pre-existing `.mimosa/` remains untracked |

## Observation identity and persistent-ledger checkpoint evidence

This section retains historical evidence for `1d5b448` and the capability boundary during the following confirmation split; “current” here refers to that checkpoint, not this projection version. See the projection checkpoint below for the latest result.

| Check | Command or source | Status |
| --- | --- | --- |
| Authentication publication baseline | `git log`; published repository state | `PASS` — fail-closed single-operator authentication was committed and pushed as `f19bfaa` before commit-3 work began |
| Persistence publication | final fetch, staged-set audit, commit, push, and `HEAD...origin/main` comparison | `PASS` — 38 intended files were committed and pushed as `1d5b448`; divergence is `0 0`, `.mimosa/` remains untracked, and no staged or unstaged tracked change remains |
| Matched-only observation identity | `media_server_observation_fingerprint`; `MediaServerAuthorLookupResult`; Web `MediaServerAuthorLookup` discriminated type; observation unit/API regressions | `PASS` — the domain-separated v1 digest binds canonical author ID plus profile/publication/selector/item digests only for a unique `matched` result; `not_found` exposes neither item nor observation fingerprint, raw item ID is not retained, and Web types mirror the distinction without claiming a confirmation UI |
| Revision and ORM contract | `0008_playback_evidence.py`; `PlaybackEvidence`; migration/model regressions | `PASS` — schema version, canonical UUID, lowercase SHA-256, timestamp ordering, unique observation identity, author/time index, and Author/Job `RESTRICT` constraints are enforced in both migration and model metadata |
| Guarded downgrade | revision 0008 migration regressions | `PASS` — offline downgrade is refused, a populated ledger blocks downgrade, and only an online audited empty ledger can be removed |
| Natural replay | `PlaybackEvidenceRepository`; SQLite repository regressions | `PASS` — immutable natural identity replays the first durable row and timestamps; conflicting reuse of an observation fingerprint returns the fixed conflict code, and validation/FK/check failures do not become replay success |
| SQLite transaction and races | repository statement/rollback/concurrency regressions | `PASS` — the first natural-key read is protected by `BEGIN IMMEDIATE`, insertion is savepoint-scoped without committing the caller transaction, an unsafe existing deferred writer transaction is rejected, and concurrent identical/conflicting attempts leave one durable winner |
| PostgreSQL repository semantics | repository implementation and eight dedicated PostgreSQL race tests | `NOT_RUN` — the implementation uses the unique constraint plus savepoint rollback and winner re-read under `READ COMMITTED`, but all 8 executable race cases were skipped because `MEDIA_SYNC_TEST_POSTGRESQL_URL` is unset |
| Migration/repository subset | focused migration, SQLite repository, and PostgreSQL-race test selection | `PASS` — 42 passed and 8 skipped; all skips are the unconfigured PostgreSQL cases above |
| Commit-3 focused union | focused observation/API/migration/repository/PostgreSQL-race regression selection | `PASS` — 129 passed, 8 skipped, 1 pre-existing Starlette/httpx deprecation warning |
| Checkpoint documentation | `uv run --frozen python scripts/check_docs.py`; `git diff --check` over the four mutable 0055 progress/verification files | `PASS` — 498 Markdown files have valid links and the checkpoint documentation has no whitespace error |
| Complete current Python regression | `uv run --frozen pytest -q` | `PASS` — 2868 passed, 22 skipped, 1 pre-existing Starlette/httpx warning in 558.19s (`0:09:18`). The skips are 3 Windows/POSIX differences, 11 existing Operation PostgreSQL cases, and 8 new PlaybackEvidence PostgreSQL races; the 19 PostgreSQL cases remain `NOT_RUN` because `MEDIA_SYNC_TEST_POSTGRESQL_URL` is unset |
| Current Web regression and build | `npm run format:check`; `npm test -- --run`; `npm run check`; `npm run build` in `web/` | `PASS` — formatting is clean, 7 files/69 tests pass, Svelte reports 0 errors and 0 warnings, and the production build completes; this does not claim the unimplemented login/confirmation surfaces |
| Current code quality | `uv run --frozen ruff check .`; `ruff format --check .`; `uv run --frozen mypy --strict src/media_sync`; `python -m compileall -q src tests` | `PASS` — Ruff check passes, all 727 files pass format after one formatting-only correction, strict mypy passes over 105 source files, and byte-compilation is clean |
| Current distribution | isolated system-temporary `uv build`; inspect wheel/sdist with `zipfile`/`tarfile` | `PASS` — exactly one 123-entry wheel and one 837-entry sdist were produced; both include `playback_evidence_repository.py` and `0008_playback_evidence.py`, with zero `.env` or SQLite output |
| End-to-end capability boundary at that time | service/API/qualification/Web surfaces at the confirmation split | Historical `PARTIAL` — confirmation service/API existed while projection, qualification v3 and Web login/confirmation were absent; schema v2 then marked overall playback evidence `NOT_IMPLEMENTED`. This projection updates that backend state; Web and live acceptance remain incomplete |

## Confirmation service and browser-only POST checkpoint evidence

This section is historical evidence for published `13de3b7`, including the 2941-test/594.72s result; it does not substitute for current projection regression. That checkpoint intentionally split frozen commit boundary 4 for independent review of the security-sensitive write path, completing delivery item 10 and the POST half of item 11. The following by-author projection and qualification v3 are now implemented; see the next section.

| Check | Command or source | Status |
| --- | --- | --- |
| Confirmation authority | `PlaybackEvidenceService.confirm`; service unit and composition regressions | `PASS` — canonical request identity, one <=120-second absolute deadline, resolve A → one complete unique lookup → resolve B, exact target/profile/observation revalidation and zero-write rejection are enforced |
| Lock and transaction ordering | deterministic event/lock tests; read-only service review | `PASS` — the authority lock is always released after external work and before the short database transaction; create/replay commits before the success audit is emitted |
| Browser-only endpoint | `POST /api/v1/media-server/playback-evidence`; API/auth tests | `PASS` — exact Cookie/Origin/CSRF is required; Bearer-only and Cookie plus any Authorization are rejected before handler/body work with fixed 403 |
| Strict request and minimal response | endpoint/parser/OpenAPI tests | `PASS` — one JSON Content-Type, maximum 1 KiB, unique members, exact canonical UUID/lowercase digest fields and no `Idempotency-Key`; create/replay both return 201 with exactly six safe fields and no fingerprint/context selector |
| Fixed failure boundary | service/API failure matrix | `PASS` — invalid, non-confirmable, identity-conflict, confirmation-unavailable and store-unavailable paths use fixed non-reflecting codes; failed authority/store paths emit no success audit |
| Focused service/API gates | dedicated selections | `PASS` — service unit 18, SQLite composition 2, endpoint 51, service/API/auth union 108, media-server API 47, and broader union 289 passed with 8 expected PostgreSQL skips |
| Route inventory | exact `app.routes` enumeration | `PASS` — 58 route objects; anonymous allowlist unchanged and the new mutation is browser-only |
| Independent review | service/transaction, API/auth and final release-gate reviews | `PASS` — the first two reviews found no P0/P1/P2; the final gate found one default-runtime audit-visibility P2, which is now closed by the copied Uvicorn application-log configuration and no-socket subprocess regression. No finding remains open within that confirmation-write review scope; later delivery-review P0 work remains |
| Application and migration logging | copied Uvicorn log config; no-socket audit subprocess; embedded-Alembic root-inheritance subprocess | `PASS` — default `serve` gives `media_sync` a configured stderr handler while retaining Uvicorn defaults; fixed playback and operator-auth INFO codes are visible without reflecting a private sentinel. Programmatic Alembic INI runs do not replace the caller root level/handler or inherited INFO logging |
| Current Web and static gates | `pnpm format:check`; `pnpm test`; `pnpm check`; `pnpm build`; Ruff/format; strict mypy; compileall | `PASS` — Web 7 files/69 tests, 0 Svelte errors/warnings and production build; 731 formatted files, 106 typed source files and byte compilation pass |
| Docs/upstreams/distribution | docs/upstream checks; isolated `uv build` inspection | `PASS` — 498 Markdown files and both clean pinned upstreams pass; after explicitly ignoring `.mimosa/`, one 124-entry wheel and one 810-entry sdist include the service/repository/revision and exclude runtime/tool-history/database output |
| Docker and PostgreSQL execution | executable/environment checks | `NOT_RUN` — Docker executable is unavailable and `MEDIA_SYNC_TEST_POSTGRESQL_URL` is unset; source/tests do not substitute for execution |
| Complete Python regression after all logging fixes | `uv run --frozen pytest -q` | `PASS` — 2941 passed, 22 skipped and 1 existing Starlette/httpx warning in 594.72s (`0:09:54`). Three skips are Windows/POSIX differences; 11 Operation and 8 PlaybackEvidence PostgreSQL cases remain `NOT_RUN` because the test URL is unset |

## Current author projection and qualification v3 checkpoint evidence

Exact commands, attempt history and final documentation/package/Git gates are in [projection verification](evidence-projection/verification.md). This summary covers only the gates actually run for this increment.

| Check | Command or source | Status |
| --- | --- | --- |
| Bounded read and qualification scope | query service/API/SQLite/qualification regressions | `PASS` — Cookie/Bearer reads, strict UUID/query, default 20/max 50 historical rows, at most `limit + 2` materialized rows, independent exact-current selection, and 59-route auth inventory; no author means no ledger/remote query |
| Current authority and truncation | authority/deadline/transaction ordering/real SQLite SQL capture | `PASS` — only complete stable remote authority plus a durable row matching all immutable fields can yield scoped PASS; remote lookup truncation cannot PASS, history-page truncation does not invalidate the independent current row; uncertain history is unknown, complete absence is stale; all external work precedes the short read transaction, with no COUNT or writes |
| Final focused union | projection/confirmation/API/auth/qualification/SQLite selection | `PASS` — 220 passed, 1 existing warning in 51.09s |
| Complete Python regression | `uv run --frozen pytest -q` | `PASS` — 2999 passed, 22 skipped, 1 existing Starlette/httpx warning in 613.66s; 3 Windows/POSIX differences plus 11 Operation and 8 PlaybackEvidence PostgreSQL cases skipped for missing configuration; no real PostgreSQL execution is claimed |
| Web and confirmed static gates | `pnpm test`, `pnpm format:check`, `pnpm check`, `pnpm build`; strict mypy/format | `PASS` — 7 files/69 Web tests, zero Svelte errors/warnings, production build; 107 mypy source files and 743 formatted files. Only response types changed; no new login or confirmation UI is claimed |
| Live and deployment boundary | current workstation capability and checked-in qualification | `NOT_RUN` — Docker/real PostgreSQL/current-image browser integration/live platform and media-server workflows; test rows or scoped-PASS fixtures do not change live qualification |

## Verification attempt log

1. The first `git fetch --prune origin` failed with a transient GitHub TLS unexpected EOF; the immediate retry completed successfully and the divergence check remained clean.
2. `docker compose ... config --quiet` could not start because this Windows workstation has no Docker executable. A fallback PyYAML parser was also unavailable. The policy and manifest wiring are covered by unit tests and read-only inspection, but a real Compose parse/start remains explicitly `NOT_RUN`.
3. The isolated `uv build` itself succeeded on its first run. The first wrapper assertion counted uv's generated `.gitignore` as a package and exited nonzero; the corrected filter verified exactly one wheel and one sdist. A first content assertion incorrectly expected the Docker-only Console v2 copy in the standalone wheel; the corrected distribution contract verified the included legacy console while the separate Web production build verified Console v2.
4. The first tracked-output denylist was too broad and classified the legitimate documentation directory `docs/archive/` and Web route `routes/jobs/` as runtime roots. The corrected root-aware scan checked 800 indexed files and found zero forbidden generated/runtime output. Separate staged-diff scans found zero workstation path, private-key, GitHub/OpenAI/AWS token, or assigned production operator-secret match.
5. The commit-3 migration/repository selection discovered all eight dedicated PostgreSQL race tests but skipped them because `MEDIA_SYNC_TEST_POSTGRESQL_URL` is unset. Their existence and collection do not constitute execution, so PostgreSQL remains `NOT_RUN`.
6. The complete Python suite for the current commit-3 worktree finished with 2868 passes, 22 skips, and one existing warning in 558.19 seconds (`0:09:18`). This is separate from the historical 2811-pass `f19bfaa` result. The 3 Windows/POSIX skips and both unconfigured PostgreSQL groups—11 existing Operation cases plus 8 new PlaybackEvidence races—are retained explicitly; no PostgreSQL execution is claimed.
7. The first current Ruff format check identified one formatting-only difference. After that source was formatted, the repeated check passed all 727 files; Ruff check, strict mypy over 105 source files, and compileall also passed. No behavioral pass is inferred from the formatting correction alone.
8. The first distribution wrapper passed an unsupported `New-Item -LiteralPath` argument in this PowerShell environment. `uv build` nevertheless created the isolated output directory and succeeded; the corrected content check verified one wheel and one sdist without embedding a workstation path in artifacts or documentation.
9. The first complete confirmation-checkpoint suite reached 2938 passes and 22 expected skips but failed one audit-log assertion. The failure was order-dependent: an earlier Alembic INI migration configured logging with the standard library default that disables already-created loggers. The durable service result was correct, but silently losing its fixed audit event was not acceptable.
10. An initial mitigation preserved existing named loggers and produced a complete `2940 passed, 22 skipped, 1 warning in 578.68s` run. Independent review then found that embedded Alembic could still lower the caller root logger to `WARNING`; that passing run is retained as an intermediate result, not the publication result.
11. A subsequent complete-suite attempt was deliberately stopped near 7% once that residual root-logger risk was confirmed, so no stale implementation was allowed to consume the full gate. Alembic logging configuration is now limited to the standalone CLI (`cmd_opts` present); embedded programmatic `Config(alembic.ini)` retains caller logging. A subprocess regression proves root-handler identity, inherited INFO enablement and a real fixed audit record without contaminating the parent test process. The resulting frozen-environment rerun completed with 2940 passes, 22 expected skips and one existing warning in 588.32 seconds (`0:09:48`); it was the next publication candidate, later superseded by item 14.
12. The first new artifact-content assertion treated the intentionally shipped `.env.example` as though it were a secret `.env`. The corrected exact-name check passes and still rejects actual `.env`, SQLite files and runtime roots.
13. The expanded package denylist then found that Hatch included the untracked `.mimosa/` finding/history tree in the sdist because it was not ignored. `.mimosa/` is now explicitly present in `.gitignore` and `.dockerignore`; a fresh isolated build reduced the sdist from 841 to 810 entries, and the strict wheel/sdist scan plus ignore checks prove the tool-history root is absent from distributions and build context.
14. Final release review then proved that default Uvicorn logging did not make `media_sync.*` INFO audits visible. `serve` now passes a copied log configuration with its own validated-level stderr handler for that namespace while preserving Uvicorn defaults and disabled access logging. The no-socket audit regression passes, and the final complete suite after this correction passes 2941 tests with 22 expected skips and one existing warning in 594.72 seconds (`0:09:54`). This is the publication result.

## Review findings closed

1. Login now reads and compares the browser digest under the same lock used by credential rotation. The deterministic concurrency regression proves that a login begun with the old credential cannot leave a valid session after rotation completes; Bearer reads are locked too.
2. Explicit wildcard/container bind no longer forces HTTPS merely because the internal bind is non-loopback. Each browser origin remains independently canonicalized: HTTP is accepted only for loopback, non-loopback HTTP is rejected, mixed schemes are rejected, and Secure cookies follow the single accepted scheme.
3. Login catches bounded deep-JSON recursion and returns the fixed 400 response. Its manually parsed request is represented in OpenAPI as one required, additional-property-free, write-only credential field.
4. The outer boundary removes every downstream HEAD body while preserving representation headers; its own rejected HEAD retains the GET representation length and emits no body. Health, readiness, and archive GET/HEAD registrations are split to avoid duplicate OpenAPI operation IDs.
5. The shared authenticated test client no longer attaches CSRF headers to safe methods, removing false evidence for browser primitives that cannot set custom headers.
6. Final release review proved that Uvicorn's default configuration left `media_sync.*` INFO audits below the effective root threshold. `serve` now deep-copies rather than mutates Uvicorn's defaults, adds one non-propagating `media_sync` stderr handler at the validated application level, and retains disabled access logging. A no-socket subprocess emits both fixed playback and operator-auth codes and no private sentinel.

## Remaining implementation evidence

The current checkpoint closes the offline fingerprint, revision/model, guarded downgrade, natural replay, SQLite, confirmation authority, browser-only POST, bounded author projection and qualification v3 portions. P0 order is in the [delivery priority addendum](delivery-priorities.md). Remaining work still requires exact passing evidence for:

1. Complete credential-readability and pre-migration configuration validation; prove invalid/unreadable credentials fail before database changes rather than inferring an untouched database from a failed server start.
2. Prioritize Web login/session/logout/expiry, memory-only CSRF, centralized 401 reset and cookie-only EventSource/direct media; then finish accessible current/history display and matched-only attestation. The latter does not block authorized canaries through the existing CLI.
3. Verify configuration, runtime-user secret reads, migration boundary, startup, restart persistence and backup restore for the exact current commit/image on a Docker-capable Linux host, then prioritize authorized Bilibili/XHS canaries. Historical-image PASS does not substitute for the current version.
4. Run the eight PlaybackEvidence PostgreSQL races and re-run the previously skipped PostgreSQL coverage on a configured host; source inspection is not a substitute.
5. Preserve credential/session/CSRF/reference/raw-selector non-retention through final repository, package, and publication scans.
6. Re-run complete Python/Web and all quality/package/documentation/upstream/generated-output/host-path/secret/whitespace gates after the remaining implementation, then complete the Git publication gate.

## Live qualification

No 0055-A live authentication or real Emby/Jellyfin playback has run. Planning, mocks, generated media, database rows created by tests, and item observation cannot produce a checked-in human PASS. Live playback remains `NOT_RUN` until an authorized operator actually plays and explicitly confirms an exact current item.

## Exit gate

Phase A may close only after all frozen local requirements have exact evidence, no P0/P1/P2 review finding remains, migration/rollback is safe, every non-public route is denied by default, and retained outputs contain no credential/session/CSRF/raw selector. Closeout must still state the unexecuted 0047 live rows and every excluded 0055 administration feature.
