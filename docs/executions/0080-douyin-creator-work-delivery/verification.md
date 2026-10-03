**English** | [中文](verification.zh.md)

# Verification: durable Douyin creator-work delivery (0080)

Planning baseline: the frozen plan in this folder (commit `d5cddd8`). Implementation recorded at this slice's `feat` commit.

## Final results

| Gate | Result | Evidence and boundary |
| --- | --- | --- |
| Douyin scan-state unit tests | `PASS` | `tests/unit/test_douyin_creator_work.py` → `9 passed`. Canonical cursor round trips, three opaque cursor steps ending only in a real `has_more != 1`, empty-page stall, access-restriction ≠ source end, unit-cap witness retention, failed-detail isolation, head drift re-reconciliation, binding-mutation rejection, upstream page size 18. |
| Continuation policy unit tests | `PASS` | `tests/unit/test_douyin_scan_continuation.py` → `5 passed`. Closed delay domain (0/60…604800), bounded defaults, malformed upstream SHA rejection, fail-closed lock fallback. |
| Capture shim contract tests | `PASS` | `tests/contract/test_douyin_creator_capture.py` → `8 passed`. Page parser reduces listings to bounded identities (no `desc` leakage), ambiguous-progress rejection (string `has_more`, out-of-domain values, malformed/duplicate `aweme_id`), shim sealing coverage with failed-detail isolation, rejected store-write isolation, list restriction blocked with `access_restricted` and no source end. |
| Ingestion integration | `PASS` | `tests/integration/test_douyin_creator_work_ingestion.py` → `3 passed`. One-commit page/cursor/run/contents publication with zero-work replay; access restriction commits nothing durable but records the stop reason; records not proven by the sealed page are rejected with no state change. |
| Migration round trips | `PASS` | `tests/integration/test_douyin_creator_work_migration.py` → `3 passed`. Empty-by-default upgrade adding exactly `douyin_subscription_progress`, metadata/migration shape parity, history-refusing and authority-demanding downgrade. |
| Delivery transitions | `PASS` | `tests/integration/test_douyin_creator_work_delivery.py` → `3 passed`. Backfill source-end produces the evidence triple and flips the subscription cursor to the head lane; one stable head reconciliation closes the baseline into incremental with `baseline_snapshot_complete`; a restricted list unit blocks with the fixed `douyin_access_restricted` code; a terminal pipeline failure blocks with the exact code. |
| Head-pinned regression updates | `PASS` | `test_packaged_migrations` (14 passed; wheel carries 0015 and 0016), `test_cli` (revision/tables 26), `test_support_bundle`, `test_api_support_bundle`, `test_offline_media_pipeline`, `test_scheduled_offline_pipeline`, `test_deployment_provenance` (allowlist completed with 0015 + 0016). |
| Static gates | `PASS` | Ruff format/check clean across `src tests`; strict mypy: `Success: no issues found in 165 source files`; `compileall` clean; `scripts/check_docs.py` OK (800 files); `scripts/check_upstreams.py` OK (2 locked checkouts); `uv build` produced the wheel. |
| Complete Python suite | `PASS` | `7185 passed, 42 skipped, 1 warning in 1492.01s (~25 min)` on the final tree (40 skips are the existing Windows/POSIX and PostgreSQL-URL qualification branches). |
| Docker image / Linux gates | `NOT_RUN` | Operator-side work under the 0077 handoff; no deployment claim. |
| Real Douyin login, live creator canary, supervisor restart | `NOT_RUN` | No platform credential or live crawler was used; per the frozen plan these remain operator-run. |

## Source trace recorded (plan step 1)

- Pagination: `/aweme/v1/web/aweme/post/` with `sec_user_id`, fixed `count: 18`, server-echoed string `max_cursor` (starts empty), response `has_more` integer + `max_cursor` + `aweme_list` (`client.py::get_user_aweme_posts`).
- Upstream stop: `while posts_has_more == 1` — `has_more != 1` is the only genuine end; an empty `aweme_list` with `has_more == 1` makes no progress (modeled as `empty_page_stalled`).
- Signing: per-request `a_bogus` via the pinned `douyin.js` on the Playwright page (`client.py` pre-request hook); the child shim keeps this inside the pinned runtime.
- Ban model: an empty or literal `"blocked"` body raises `account blocked` wrapped into `DataFetchError`; `IPBlockError` marks rate limiting. Both are access restrictions, never source ends.
- Identity/media: creator `sec_user_id` from `parse_creator_info_from_url`; work detail via `get_video_by_id` returning `aweme_detail`; media branches `_extract_note_image_list` (gallery) vs `_extract_video_download_url` (video).

## Commands run

```text
uv run pytest -q tests/unit/test_douyin_creator_work.py tests/unit/test_douyin_scan_continuation.py
uv run pytest -q tests/contract/test_douyin_creator_capture.py
uv run pytest -q tests/integration/test_douyin_creator_work_ingestion.py tests/integration/test_douyin_creator_work_migration.py tests/integration/test_douyin_creator_work_delivery.py
uv run pytest -q   # complete suite, final tree
uv run ruff format src tests && uv run ruff check src tests
uv run mypy --strict src
uv run python -m compileall -q src
uv run python scripts/check_docs.py
uv run python scripts/check_upstreams.py
uv build
git diff --check
```

## Design notes for reviewers

- **Why the shim anchors on the working directory.** The child process validates the checkout (`verify_manifest_checkout`) and `os.chdir`s into it before any shim installs; passing the root again through a parameter re-introduces an argv-derived taint the scanner rightly flags as a path-traversal entry. The shims therefore derive the root from `Path.cwd()` and only validate the output root for traversal segments.
- **Why list-level and detail-level failures differ.** A list failure means the feed endpoint itself rejected or failed the request — the machine blocks with `access_restricted` (never source end). A detail failure isolates to that one work (`detail_unavailable`), keeps the page witness, and lets unrelated works deliver — matching the per-Content visibility contract.
- **Why `max_cursor` is wrapped, not parsed.** Douyin echoes an opaque server cursor; any attempt to interpret it invites drift. The state machine stores it verbatim inside the canonical `dy-work-v1:` envelope and re-validates binding on every load.
