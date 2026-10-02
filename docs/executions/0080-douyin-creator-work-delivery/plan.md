**English** | [中文](plan.zh.md)

# Plan

Status: **FROZEN FOR THIS TURN'S IMPLEMENTATION**. This document authorizes no deployment, platform request or supervisor restart by itself.

## 1. Trace and record before writing state

- Follow the pinned Douyin creator flow from the adopted Account profile through `parse_creator_info_from_url`, `get_user_info`, `get_user_aweme_posts` pagination (`sec_user_id`, `count: 18`, server-echoed `max_cursor`), per-work `aweme_id` detail via `get_video_by_id`, and the media branches `_extract_note_image_list` / `_extract_video_download_url`.
- Reuse the 0076 delivery skeleton (scan unit/coverage, continuation policy, delivery progress repository, Job-scoped ingestion, downloader, archive, library writer) but re-derive every parameter from Douyin evidence; record the pinned MediaCrawler SHA and observed page shapes in the verification.
- Name the exact points where XHS or Bilibili assumptions would be wrong for Douyin (integer `has_more`, echoed `max_cursor`, empty-page stall, `a_bogus` signing, `blocked`-body detection) and write each down as a contract with a test.

## 2. Durable cursor and stop-reason state

- Migration `0016_douyin_creator_work` (revises `0015_xhs_creator_notes`) creates `douyin_subscription_progress` with the same constraint discipline as 0015: closed `phase` whitelist, the four fixed stop reasons (`has_more_false`, `empty_page_stalled`, `access_restricted`, `unit_cap_reached`), counter ranges, all-or-nothing evidence triples for delivery/source-end/reconciliation, `blocked_code` iff `phase = 'blocked'`, and guarded downgrade.
- Persist the server-echoed `max_cursor` verbatim, wrapped under the opaque `dy-work-v1:` cursor namespace. Store only bounded counters, fingerprints and timestamps; never raw responses, sign material or Cookies.

## 3. Bounded continuation with fenced units

- One page-bound unit per step after the prior unit's discovery and pipeline receipt are durably consistent; honor `max_items`, the configured continuation delay (default 300 s via `MEDIA_SYNC_DOUYIN_SCAN_CONTINUATION_DELAY_SECONDS`, identical in both services), pause/removal and auth/backoff state.
- API exact execution and the resident supervisor compete through the same durable ownership fence used by 0074/0076; duplicate submissions reuse the authoritative unit.

## 4. Reconciliation and incremental head checks

- After retained `has_more_false` evidence, run one bounded head re-list: the recorded boundary must reproduce (same newest work set, stable cursor echo) before entering incremental mode; drift re-opens reconciliation while keeping delivered data.
- Incremental cycles re-list bounded head pages, deduplicate by stable `aweme_id`, fetch details only for unseen or changed works, and treat empty-page stalls or restrictions as bounded retry states — never as cursor loss.

## 5. Delivery and publication per complete Content unit

- Gallery works publish only with every image present; video works publish only with the video bytes; unrelated works are never blocked by one failed work; partial outcomes carry exact failed-work counts and fixed codes.
- Prove restart and zero-work replay preserve content-addressed bytes and deterministic NFO output.

## 6. Operator surface

- Subscription details expose the phase, cursor-step counts, last source-end/reconciliation evidence, next eligible run and exact failed-work counts. No cursor blob, sign material, host path or raw response is exposed.

## 7. Verification sequence

1. Unit tests for cursor round-trip, the four stop reasons, page-tail replay, failed-detail advance, head drift and cursor-binding mutation rejection.
2. Contract tests for page parsing privacy, the capture shim sealing coverage, restriction ≠ source end, and the `douyin.js` signing fixture passing the pinned script via stdin.
3. Integration tests: three or more cursor steps with restart barriers, empty-page and blocked-body backoff, source end, head drift, transition to incremental, partial delivery, zero-work replay, one-commit ingestion, migration round trips pinned at `0016`.
4. Update every head-pinned test (packaged migrations, CLI/support-bundle revisions, table counts, offline/scheduled pipelines, deployment provenance).
5. Complete Python and Web suites, Ruff, strict mypy, documentation/upstream checks, package build and `git diff --check`; record exact bilingual results.
6. Linux host build, real Douyin session adoption and a live creator canary stay `NOT_RUN` until the operator explicitly runs them.
