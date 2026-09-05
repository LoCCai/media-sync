**English** | [中文](verification.zh.md)

# Verification

Baseline87ef7fd, frozen plan36e004d. Isolated local data only; no production Cookies.

## Python and static checks

- Complete offline checkpoint: .venv/Scripts/python.exe -m pytest -q --tb=short → 3972 passed,22 skipped,1 warning in852.47s. Skips are3 Windows/POSIX differences and19 unconfigured PostgreSQL cases; warning is existing Starlette/httpx deprecation. Previously skipped Pillow QR cases ran after adding the dependency.
- Final small hardening after full-suite startup (ORM revision refresh, unified UID cap, atomic-success tests) separately passed53 profile/effect/API tests in13.56s. Do not relabel the original run as a second full run of final source.
- The final expanded frozen-source selection is in [final-tests.txt](final-tests.txt), executed with the same Python prefix, every listed path and -q --tb=short: **575 passed, 1 warning in 109.47s**, exit 0. The 21-file union covers the new runner/process/upstream/avatar/API/effects/repository/migration and existing coordinator/auth/CLI/support/workbench/login/checkpoint/removal/package contracts.
- Runner selection: tests/unit/test_creator_profile_runner.py, tests/contract/test_creator_profile_process.py, tests/contract/test_creator_profile_upstream.py →68 passed/14.64s (56 protocol,9 real child-tree,3 actual pinned-module tests with substituted network/browser dependencies); no related residual processes.
- Avatar tests/unit/test_creator_avatar.py →31 passed/2.96s; API/Operation parameters124 passed/9.92s; DB/auth/alias175 passed/35.79s; corrected CLI/report/wheel-migration/API/effect143 passed/45.78s. These overlap and must not be summed as distinct coverage.
- Final closeout commands all exit 0: `.venv/Scripts/python.exe -m ruff check src tests scripts`; `-m ruff format --check src tests scripts` (281 files in this explicit scope); `-m mypy src/media_sync` (117 source files); `-m compileall -q src scripts`; `uv lock --check`; `.venv/Scripts/python.exe scripts/check_docs.py` (590 Markdown files); `.venv/Scripts/python.exe scripts/check_upstreams.py` (both locked checkouts); `git diff --check`. Python `-m` commands use the same virtual-environment executable. The earlier wider formatting checkpoint covered 871 files; these are different scopes.

## Distribution

At 2026-09-05 22:37:49 +08:00, `uv build --out-dir` into a new GUID temporary directory exited 0 and built the wheel from the sdist. Wheel: 566970 bytes / 137 members; sdist: 2329354 bytes / 977 members. `tar -tf` inspection verified all six new production modules in both: profile runner, service, avatar fetcher/worker, repository and migration 0010. Filename-only checks found zero private environment/database/secret/runtime/upstream/node_modules/cache/log artifacts; the public `.env.example` in the sdist is intentionally allowed.

Artifacts remain outside the repository at `C:/Users/LoCCai/AppData/Local/Temp/media-sync-0057-package-07741cfe-c951-4daf-9e44-b93f4b8ddd66`. SHA256: wheel `57721342871718d9ec0d28eaefF6ec56e1f0fa4b13add5c4b78a78dce31106af`; sdist `fc8b306c263d684063765f4932fe3de77c68dfbd6cc78db91a613f6ada494ffc`. Documentation was still being finalized when the sdist snapshot was built; production source was frozen. This is archive composition verification, not a content secret scan, fresh installed-wheel smoke, Docker build or live qualification. The 575-test union separately includes packaged-migration tests. Initial PowerShell archive inspection hit a syntax-only ParserError (exit 1); corrected inspection and the expanded filename audit exited 0 without modifying archives.

## Web and browser

- Final serial pnpm test, pnpm check, pnpm format:check, pnpm build →492 tests/19 files, zero check errors/warnings, format/build pass; existing build-performance notices only.
- Used the computer-use skill's preferred browser interface against an isolated loopback8767 fixture. Normal test login and browse-only onboarding without accepting the license. Entering a UID and blurring reproduced a generic query failure for a local gate rejection. Fixed to explicitly say no query started, keep the query button and preserve the automatic opportunity.
- A separate script preloaded synthetic successful profiles and a paused subscription without platform access. Visually checked list/detail nickname, separate note, avatar and actual observation times. No UI subscription creation/removal/restoration, QR, live lookup/capture, download/export or outbound homepage opening.
- Rebuilt the fix; the first refresh/recheck encountered additional page navigation, so this is not a completed browser recheck of the gate message. Dedicated controller tests cover the fix. Closed the dedicated browser tab. Verified the fixture process by its exact temporary script path and Python executable before stopping it; confirmed no listener on port 8767 and the server handle closed. Temporary synthetic files remain outside the repository; no production process was stopped.

## Failures, corrections and review

Initial avatar run29 passed/4 fixture errors came from huge bytes-based parameter IDs exceeding Windows temporary-path limits; fixed short IDs and precise exception assertions. Operation union161 passed/2 failures missed new-kind test parameters; auth44 passed/1 failure reflected route count62→65; broader177 passed/9 failures reflected table count17→19, new closed fields/kind and a0004 fixture incorrectly using current Account ORM with auth_revision. Corrected actual contracts; historical fixtures write historical columns without adding modern schema. DB agent's initial171 passed/2 failures also involved new tables and the historical migration target, then passed. Mistyped-path zero-collection commands do not count.

Independent review checked the shared lock, account isolation, auth ABA, retained avatars, Operation→Account lock order and safe migrations. Fixed the profile/Operation success window by committing both atomically; the second fence defines linearization time, refreshing ORM state avoids stale revisions, and read-side error allowlists reject arbitrary database errors. Added concurrent Author insert-if-missing protection. Actual PostgreSQL races remain unqualified.

## Unrun gates and publication

Docker is unavailable and no PostgreSQL test URL is configured. Docker build/production deployment and live profile/login/capture/archive/playback remain NOT_RUN. Six-platform/Cookie profiles remain NOT_IMPLEMENTED; pasted-Cookie login, correct bounded coverage and the overall goal stay open. No production action or supervisor restart. Implementation is not yet committed/pushed; record after final checks.
