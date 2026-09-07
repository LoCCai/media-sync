[**Chinese**](plan.zh.md) | **English**

# Plan

Status: **frozen before implementation**.

## 1. Freeze the mutation contract

- Add a typed policy-update command containing the five editable controls and `expected_schedule_revision`.
- Parse and validate the current closed MediaCrawler policy before mutation. Preserve full-history acknowledgement and the opaque creator reference exactly.
- Return fixed public error codes for not found, removed, enabled, busy, stale revision, unsupported adapter, and invalid policy/options.

## 2. Own one short database transaction

- Reserve the SQLite writer or lock the exact subscription row on PostgreSQL.
- Recheck active Job, non-terminal Run, and active operation ownership inside the transaction.
- Compare the revision, apply all fields atomically, and increment `schedule_revision` only for a real change.
- Assert through tests that checkpoints, watermarks, scan/delivery rows, timing evidence, failures, history, and files are untouched.

## 3. Share the service across control surfaces

- Add `PUT /api/v1/subscriptions/{id}/policy` with strict extra-field rejection and an allowlisted result.
- Add a `media-sync subscription policy` CLI command. Retain the existing Bilibili-scope compatibility command while routing new UI work through the general service.
- Keep all client-visible messages fixed and reference-free.

## 4. Replace the narrow detail editor

- Expand the subscription detail editor from Bilibili scope only to the complete closed policy set.
- Populate controls only from a validated fresh detail response, show why enabled subscriptions cannot be edited, and keep save disabled for malformed inputs or unchanged values.
- Fence the request by subscription identity, schedule revision, operator-session epoch, modal lifetime, and one in-flight generation. A successful save updates the visible detail and list but leaves the subscription paused.

## 5. Verify and publish

1. Add application/integration tests for atomicity, concurrency, idle fences, exact preservation, Bilibili delivery requalification, and no-op behavior.
2. Add API/CLI contracts and Web utility/source tests for strict validation, redaction, and stale-response behavior.
3. Run targeted Python and Web tests, then the complete repository gates in the established serial order.
4. Because the Browser plugin is not available in this session, use the repository's existing local server/Playwright workflow for rendered desktop and mobile checks and record that fallback.
5. Update bilingual progress, verification, roadmap, and unified status with exact results; commit and push each completed delivery checkpoint.

## After 0075

Audit the pinned XHS creator-note path and freeze its own bounded cursor, source-end, reconciliation, and incremental evidence contract before implementation. Offline fixtures remain design evidence only; live qualification remains `NOT_RUN` until operator-assisted deployment checks exist.
