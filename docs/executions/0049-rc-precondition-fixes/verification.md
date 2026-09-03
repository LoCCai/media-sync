**English** | [中文](verification.zh.md)

# Execution 0049 verification

- Status: Offline fixes pass all gates on this workstation; container runtime verification stays with phase B
- Date: 2026-09-03
- Predecessor: Execution 0048 closeout `0eb3f895b02137cbfe231c705ba34aa1ce86a9f4`
- Plan commit: `dcba270`

## Baseline (before any 0049 change)

| Check | Result |
| --- | --- |
| Pulled-tree static smoke (ruff, doc links, upstreams, new unit files) | `PASS` (recorded at pull time) |
| 0048's authoring-station complete-suite numbers | `33 failed, 2031 passed, 1 skipped`; rerun `35 failed` (flaky child-process sealing tests) |

## Implemented evidence

| Scope | Result |
| --- | --- |
| Container checkout path | `PASS` (static) — the checkout now clones to `/app/.upstream/MediaCrawler` with `.git` intact, matching the verifier's lock-relative resolution and git-identity requirements |
| Playwright shared path | `PASS` (static) — `PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright` is set before the install, the runtime user owns the cache, and the build manifest records a real `chromium.launch()` as `mediasync`; the in-container launch itself is phase B |
| Operation semantics | `PASS` — a blocked download finishes its operation `failed` with `locator_refresh_unsupported`; a hand-verified asset without its blob finishes `failed` with `asset_download_state_invalid` (no fake green); a completing executor drives `succeeded` using the app-captured settings |
| Settings capture | `PASS` — every background thread and the login-status path use the `create_api_app()` settings; the lifecycle test asserts the thread's state dir equals the factory's |
| Documentation integrity | `PASS` — both journal readmes are 156 lines with one H1/one switcher; the hardened checker (duplicate H1/H2, stray switchers, bilingual heading parity, code blocks excluded) passes over all 424 files |
| Receipt reason codes | `PASS` — completion failures now carry the fixed enum suffix in the redacted message (verified by the existing completion-failure suites staying green) |
| Reproducibility guidance | `PASS` — compose passes `BASE_IMAGE` through; deployment docs record the digest-pinned build and the doctor/Chromium preflight gates |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| API server suite | `uv run pytest -q tests/unit/test_api_server.py` | `PASS — 7 passed` |
| Stability rerun of 0048's flaky files | `uv run pytest -q tests/integration/test_mediacrawler_security_matrix.py tests/contract/test_mediacrawler_supervision.py` | `PASS — 28 passed, 1 skipped in 41.07s` |
| Complete suite (junit artifact) | `uv run pytest -q --junitxml=artifacts/pytest-windows-0049.xml` | `PASS — 2066 passed, 1 skipped in 472.81s`; artifact summary `tests=2067 failures=0 errors=0 skipped=1` |
| Ruff and format | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 604 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 87 source files` |
| Compileall and build | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — compiled; wheel and source distribution built` |
| Documentation and upstream locks | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 424 Markdown files; 2 locked clean checkouts` |
| Git/upstream audit | explicit status and tracked-path scans | `PASS — intended changes only; tracked runtime/upstream/dist 0; both upstream dirty counts 0` |

## Workstation failure-list honesty note

0048 recorded `33 failed, 2031 passed` and a rerun with `35 failed` on this station. This execution's full run passed **2066/2067 with zero failures** (the +2 are the new lifecycle tests), and a targeted rerun of the previously failing files also passed — confirming the divergences are **nondeterministic on this authoring station** (consistent with the review's AV/filesystem-race hypothesis), not deterministic product defects and not something this execution "fixed". The green junit artifact (`artifacts/pytest-windows-0049.xml`) therefore records a green run, not a failure list; the per-test Linux diff remains the phase-B authority, and Windows-native runs stay Experimental in the status pages until the flakiness is classified.

## Not claimed

No Docker build/run, in-container doctor preflight, Chromium-as-runtime-user launch, restart persistence or backup-restore drill is claimed (no Docker on this station; all phase B). No live qualification row is claimed.
