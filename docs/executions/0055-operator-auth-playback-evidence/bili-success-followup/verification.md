**English** | [中文](verification.zh.md)

# Verification

Baseline: clean main at f9b343c, frozen plan b018979 and later Worker-display addendum 9602246. Exact deployed commit/image identity has not been independently verified. No login-account identifiers, credentials, full browser snapshots or private deployment details are added to Git.

## Executed Python gates

- Agent full login focus: `.venv/Scripts/python.exe -m pytest -q tests/unit/test_bilibili_login_confirmation.py tests/contract/test_mediacrawler_login.py tests/unit/test_browser_launch_diagnostics.py` — 160 passed, 72.90s. Includes seven-platform isolated-child lifecycle, synthetic profile reopening, post-update true/false/nonboolean/error/cancel and cleanup. Earlier overlapping subset: 46 passed, 45 deselected, 27.40s.
- Root backend focus: `.venv/Scripts/python.exe -m pytest -q tests/unit/test_login_diagnostics.py tests/unit/test_cli_login.py tests/unit/test_operation_payloads.py tests/integration/test_mediacrawler_login_application.py tests/integration/test_login_session_repository.py --junitxml=artifacts/bili-success-backend.xml` — 240 passed, one existing Starlette/httpx warning, 34.52s.
- Root controls: `.venv/Scripts/python.exe -m pytest -q tests/unit/test_login_preflight.py tests/unit/test_mediacrawler_login.py tests/unit/test_api_operations.py --junitxml=artifacts/bili-success-controls.xml` — 45 passed, the same existing warning, 11.43s. Reviewer-owned backend preflight file separately passed 14 tests, 4.26s; do not add this overlapping count.
- Ruff check and format of src/scripts/tests passed (257 files), mypy passed (110 source files), compileall passed. Both locked upstreams verified unchanged. No full Python suite, Docker build, PostgreSQL or package rebuild is claimed for this bounded increment.

## Web gates

Before the later Worker-display addendum, serial `pnpm format:check`, `pnpm test`, `pnpm check`, `pnpm build` passed: 208 tests / 12 files, 561ms; Svelte 0 errors/warnings; static build 8.04s. Account helper-focused tests: 78 / 3 files. Independent review found a null-response spinner risk; it was fixed and covered before these gates. Final post-addendum Web results are pending below. This turn did not run a rendered synthetic-browser fixture against the local patch; production browser work tests the deployed version, not these unpublished UI changes.

## Live result and residual diagnosis

The production canary is FAILED, not NOT_RUN or PASS: one explicitly authorized author sync, 18:53:18–18:57:14, failed_terminal Job and zero content. Worker completion and its failure summary were directly inspected. The operator's exact read-only join confirms schema_invalid Job + attached running Run with no error. The subscription is paused, no pending Jobs/active Operations were observed, and the operator stopped supervisor. No automatic retry, media download or Emby/Jellyfin action was performed. Saved-session reuse cannot be declared successful merely because the persisted account remains authenticated.

A separate agent synthetic experiment recreated this exact tuple using an in-memory SQLite database and a handler that attaches a running Run before waiting: injecting either RuntimeError or a typed SQLAlchemy OperationalError with SQLITE_BUSY into heartbeat yields failed_terminal/schema_invalid Job, running/no-error Run, cancelled handler, zero content and unchanged authenticated account. This is injected failure-path evidence, NOT an actual SQLite lock-contention test and NOT proof of the production root cause. Current heartbeat, malformed-result and fallback paths share schema_invalid. More precise closed diagnostics are needed before claiming a remedy for the capture failure.

Final post-addendum serial Web gates all passed: **269 tests / 13 files, 707ms**, Svelte **0 errors / 0 warnings**, formatting and static build passed (8.68s). The additive helper/operation/login-diagnostic subset separately passed 122 tests in 306ms; these overlapping runs are not summed. No completion-toast mechanism was added. Both upstreams passed again; fresh origin fetch at the two-plan checkpoint returned divergence 2 ahead / 0 behind.

Final docs/link check passed **562 Markdown files**; diff whitespace checks passed. Raw test XMLs remain ignored under artifacts. Future pasted-Cookie validation/persistence, other-platform live checks, true bounded Bili capture, download and playback remain pending. Publication identity will be recorded after the actual push.
