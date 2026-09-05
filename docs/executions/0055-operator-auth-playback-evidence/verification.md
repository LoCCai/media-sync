**English** | [中文](verification.zh.md)

# Execution 0055 Phase A verification

- Status: Backend-auth complete local offline gates pass; Web auth, playback evidence, Docker, and real-PostgreSQL gates pending
- Date: 2026-09-05
- Planning baseline: `d0a8cc2`; implementation baseline: `4564b2a`
- Planned revision: `0008_playback_evidence`

## Evidence policy

Planning checks establish only that the slice is scoped and based on current code. The focused evidence below proves the implemented backend authentication contracts, but does not yet prove a working Web login surface, playback evidence, real-server compatibility, or authorized human playback. Implementation evidence and live qualification remain separate.

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

## Backend authentication implementation evidence

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

## Verification attempt log

1. The first `git fetch --prune origin` failed with a transient GitHub TLS unexpected EOF; the immediate retry completed successfully and the divergence check remained clean.
2. `docker compose ... config --quiet` could not start because this Windows workstation has no Docker executable. A fallback PyYAML parser was also unavailable. The policy and manifest wiring are covered by unit tests and read-only inspection, but a real Compose parse/start remains explicitly `NOT_RUN`.
3. The isolated `uv build` itself succeeded on its first run. The first wrapper assertion counted uv's generated `.gitignore` as a package and exited nonzero; the corrected filter verified exactly one wheel and one sdist. A first content assertion incorrectly expected the Docker-only Console v2 copy in the standalone wheel; the corrected distribution contract verified the included legacy console while the separate Web production build verified Console v2.
4. The first tracked-output denylist was too broad and classified the legitimate documentation directory `docs/archive/` and Web route `routes/jobs/` as runtime roots. The corrected root-aware scan checked 800 indexed files and found zero forbidden generated/runtime output. Separate staged-diff scans found zero workstation path, private-key, GitHub/OpenAI/AWS token, or assigned production operator-secret match.

## Review findings closed

1. Login now reads and compares the browser digest under the same lock used by credential rotation. The deterministic concurrency regression proves that a login begun with the old credential cannot leave a valid session after rotation completes; Bearer reads are locked too.
2. Explicit wildcard/container bind no longer forces HTTPS merely because the internal bind is non-loopback. Each browser origin remains independently canonicalized: HTTP is accepted only for loopback, non-loopback HTTP is rejected, mixed schemes are rejected, and Secure cookies follow the single accepted scheme.
3. Login catches bounded deep-JSON recursion and returns the fixed 400 response. Its manually parsed request is represented in OpenAPI as one required, additional-property-free, write-only credential field.
4. The outer boundary removes every downstream HEAD body while preserving representation headers; its own rejected HEAD retains the GET representation length and emits no body. Health, readiness, and archive GET/HEAD registrations are split to avoid duplicate OpenAPI operation IDs.
5. The shared authenticated test client no longer attaches CSRF headers to safe methods, removing false evidence for browser primitives that cannot set custom headers.

## Required implementation evidence

The remaining exit gate requires exact passing evidence for:

1. Implement and verify the Web login/session/logout/expiry lifecycle, in-memory CSRF injection, centralized 401 reset, and cookie-only EventSource/direct-media behavior.
2. Complete a real Docker/Compose configuration and startup check on a host with Docker available.
3. Re-run the 11 real-PostgreSQL races on a configured host and add the planned PlaybackEvidence races after revision 0008 exists.
4. Preserve credential/session/CSRF/reference non-retention through the final repository/publication scans.
5. Observation-fingerprint stability/domain separation and every authority-context drift.
6. Resolve → unique lookup → resolve TOCTOU closure and zero-write failure paths.
7. Append-only revision 0008 constraints, natural replay, SQLite/PostgreSQL concurrency, RESTRICT parents, and guarded downgrade.
8. Qualification schema v3 truth: no evidence is `IMPLEMENTED/NOT_RUN`, exact current evidence may be PASS, stale evidence never is, provider completion and automatic scan stay unimplemented.
9. Web explicit matched-only playback-attestation interaction, including accessibility and truthful wording.
10. Re-run complete Python/Web and all quality/package/documentation/upstream/generated-output/host-path/secret/whitespace gates after the remaining implementation, then complete the Git publication gate.

## Live qualification

No 0055-A live authentication or real Emby/Jellyfin playback has run. Planning, mocks, generated media, database rows created by tests, and item observation cannot produce a checked-in human PASS. Live playback remains `NOT_RUN` until an authorized operator actually plays and explicitly confirms an exact current item.

## Exit gate

Phase A may close only after all frozen local requirements have exact evidence, no P0/P1/P2 review finding remains, migration/rollback is safe, every non-public route is denied by default, and retained outputs contain no credential/session/CSRF/raw selector. Closeout must still state the unexecuted 0047 live rows and every excluded 0055 administration feature.
