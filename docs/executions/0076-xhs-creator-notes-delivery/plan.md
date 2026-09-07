**English** | [中文](plan.zh.md)

# Plan

Status: **FROZEN FOR A LATER TURN**. This document authorizes no deployment, platform request or supervisor restart by itself.

## 1. Trace the XHS path end to end before writing state

- Follow the pinned XHS creator flow from the adopted Account profile through `parse_creator_info_from_url`, `get_creator_info`, `get_notes_by_creator` pagination, per-note `xsec_token` capture, `get_note_by_id` (and the HTML fallback) to the existing XHS store/normalizer shapes.
- Reuse the 0074 delivery skeleton (scan coverage, multi-step continuation, Job-scoped ingestion, downloader, archive, library writer) but re-derive every parameter from XHS evidence; record the pinned MediaCrawler SHA and the observed page shapes in the verification.
- Name the exact points where Bilibili assumptions would be wrong for XHS (opaque cursor, token gating, four stop reasons, ban states) and write each down as a contract with a test.

## 2. Durable cursor and stop-reason state

- Persist the opaque cursor verbatim, per Subscription and `notes` feed, next to bounded counters and timestamps. Extend the progress schema with the smallest migration only if the current table cannot represent it; upgrade/downgrade must preserve existing deployments.
- Record four distinct stop reasons: `has_more_false`, `empty_page_stalled`, `access_restricted`, `unit_cap_reached`. Only `has_more_false` may later qualify as source end, and only with the page evidence retained.
- Store the per-note `xsec_token` only as an opaque, bounded, non-exported capture bound to the Run that saw it; never in API payloads or logs.

## 3. Bounded continuation with fenced units

- Continue at most one page-bound unit per step after the prior unit's discovery and pipeline receipt are durably consistent; honor `max_items`, the configured continuation delay, pause/removal and auth/backoff state.
- Make API exact execution and the resident supervisor compete through the same durable ownership fence used by 0074/0075; duplicate submissions reuse the authoritative unit.

## 4. Reconciliation and incremental head checks

- After a retained `has_more_false` evidence, run one bounded head re-list: the recorded boundary must reproduce (same newest note set and a stable cursor shape) before entering incremental mode; drift re-opens reconciliation while keeping delivered data.
- Incremental cycles re-list bounded head pages with fresh tokens, deduplicate by stable `note_id`, fetch details only for unseen or changed notes, and treat token rejection as a bounded re-list trigger — never as cursor loss.

## 5. Delivery and publication per complete Content unit

- Map `normal` and `video` notes to Contents with all-or-nothing publication; unrelated notes are never blocked by one failed note; partial outcomes carry exact failed-note counts and fixed codes.
- Prove restart and zero-work replay preserve content-addressed bytes and deterministic NFO output.

## 6. Operator surface

- Subscription details expose the phase (backfill, reconciling, incremental, blocked), cursor-step counts, last source-end/reconciliation evidence, next eligible run and exact failed-note counts. No token, cursor blob, host path or raw response is exposed.

## 7. Verification sequence

1. Unit tests for cursor handling, the four stop reasons, token-bound detail gating and the closed public projection.
2. Integration test with a deterministic locked-runner fixture: three or more cursor steps, restart barriers, ban-state mid-history, source end, head drift, transition to incremental.
3. One-new-note and zero-work reruns through the real download/archive/NFO path with controlled fixtures.
4. Pause, removal, auth expiry, lease loss, duplicate ownership and migration round trips.
5. Complete Python and Web suites, Ruff, strict mypy, web build, documentation/upstream checks, package build and `git diff --check`; record exact bilingual results.
6. Linux host build, real XHS session adoption and a live creator canary stay `NOT_RUN` until the operator explicitly runs them.
