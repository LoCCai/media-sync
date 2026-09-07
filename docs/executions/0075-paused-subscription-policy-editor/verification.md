**English** | [中文](verification.zh.md)

# Verification

Implementation revision: `aec3eac` (`feat(policy): add paused subscription policy editor`). Planning baseline: `32d1a3e`.

## Final results

| Gate | Result | Evidence and boundary |
| --- | --- | --- |
| Focused policy/API/CLI/auth regression | `PASS` | `40 passed, 2 skipped, 1 warning in 16.89s`. The two skips are the explicitly optional real PostgreSQL writer race and active-operation NOWAIT checks because `MEDIA_SYNC_TEST_POSTGRESQL_URL` is not configured. |
| Complete Python suite | `PASS` | `7067 passed, 43 skipped, 108 warnings in 1638.69s (0:27:18)`. Existing skips cover OS-specific and unconfigured PostgreSQL qualifications plus the in-suite `uv` PATH check; package construction separately used the configured absolute `uv` executable. Warnings remain the existing Starlette/httpx and Python 3.12+ SQLite adapter deprecations. |
| Complete media-sync Web suite | `PASS` | `27 files / 818 tests` passed on the final frontend source. |
| Svelte and production Web build | `PASS` | `svelte-check` reported 0 errors and 0 warnings. Vite transformed 4,087 server and 4,096 client modules and wrote the static build. |
| Frontend formatting | `PASS` | Repository Web Prettier check passed. |
| Rendered desktop/mobile interaction | `PASS` | Browser plugin was not available, so bundled Playwright 1.62.1 used installed Chrome against `http://127.0.0.1:8765/subscriptions`. Page identity/title, non-blank content and absence of framework overlay passed. Bilibili and XHS saves remained `paused`; XHS returned no `bili_scope`. Desktop 1440×900 and mobile 390×844 screenshots show the editor before/after save. Console warning/error, page error and failed-request counts were all zero. No live platform request was made. |
| Python lint/format/type/compile | `PASS` | Ruff lint passed; Ruff format reported 406 files already formatted after one formatting-only correction; strict mypy passed 156 source files; compileall passed `src`, `tests` and `scripts`. |
| Locked dependencies and upstreams | `PASS` | `uv lock --check` resolved 62 packages unchanged; `scripts/check_upstreams.py` verified both locked checkouts. MediaCrawler remains pinned at `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`. |
| Python packaging | `PASS` | A fresh 774,650-byte wheel (180 members) and 3,116,025-byte sdist (1,284 members) built successfully. Both contain `subscription_policy_update.py`; neither member list contains QA paths, screenshots, databases or environment files. |
| Documentation links/whitespace | `PASS` | The final bilingual closeout passed the documentation checker and `git diff --check`; exact document count is recorded by the closeout commit. |
| Docker/Linux deployment and live services | `NOT_RUN` | No image/container, real platform/CDN, host archive/library/NFO, media server or supervisor was touched. |

## Commands run

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/integration/test_subscription_policy_update.py tests/unit/test_api_subscription_policy.py tests/unit/test_cli.py::test_subscription_policy_cli_updates_only_a_paused_current_mediacrawler_subscription tests/unit/test_operator_auth_api.py -q --tb=short

pnpm --dir web run format:check
pnpm --dir web test
pnpm --dir web run check
pnpm --dir web run build

.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m ruff format --check src tests scripts
.\.venv\Scripts\python.exe -m mypy --strict src/media_sync
.\.venv\Scripts\python.exe -m compileall -q src tests scripts
& 'C:\Users\sueli\.local\bin\uv.exe' lock --check
.\.venv\Scripts\python.exe scripts/check_upstreams.py
.\.venv\Scripts\python.exe scripts/check_docs.py
git diff --check
& 'C:\Users\sueli\.local\bin\uv.exe' build --out-dir <temporary-directory>
```

## Qualification conclusion

The local policy-mutation seam is qualified for closed validation, optimistic concurrency, paused/idle ownership, exact preservation, fixed redaction-safe control surfaces and rendered Bilibili/XHS interaction. The same generic editor is wired for every MediaCrawler platform, but this does not qualify their source pagination, live collection or delivery. Real PostgreSQL and every deployment/live row remain explicit `NOT_RUN` work.
