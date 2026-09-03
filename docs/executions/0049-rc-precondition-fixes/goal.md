**English** | [中文](goal.zh.md)

# Execution 0049 goal

- Status: RC-precondition fixes complete; runtime verification stays with phase B
- Date: 2026-09-03
- Predecessor: Execution 0048 closeout `0eb3f895b02137cbfe231c705ba34aa1ce86a9f4`
- Scope: The release-candidate precondition review fixes — no new product features
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Outcome

1. The container image materializes the MediaCrawler checkout at the exact lock-relative path (`/app/.upstream/MediaCrawler`) with its `.git` directory intact, so the existing verifier accepts it and the doctor preflight can pass inside the container.
2. Playwright browsers install into a fixed shared path (`PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright`) owned by the runtime user, and the build manifest records the actual Chromium version launched as that user rather than a derived path.
3. A failed or blocked asset download now finishes its background operation with `error_code` set (state `failed`) instead of a green `succeeded`; the endpoint and console button are labeled "download/verify" to match the verified-asset `already_verified` semantics.
4. Every API background thread uses the settings captured by `create_api_app()` instead of re-reading the global settings getter, so the test client and runtime share one database; the login-status read path does the same.
5. The download endpoint gains lifecycle coverage against a real Asset: running→succeeded, blocked→failed with a fixed code, and the verified-asset no-op semantics.
6. The docs readme files lose their accidentally duplicated second halves; the single index reflects 0043 deferral, 0044 absorption into 0048/0049, and the 0047 canary-first restructure; the documentation checker additionally rejects duplicate H1/H2 headings, stray language switchers, and English/Chinese heading-structure divergence.
7. 0043's plan status syncs to its deferral; 0044 receives an explicit absorbed-by-0048 close-out record; the architecture note states the delivered ffmpeg stream-copy mux/remux/concat reality; the third-party notice describes the operator-built Docker image accurately; the deployment guidance records digest-pinned base-image builds and both-service bind-mount notes.
8. The parent process preserves the fixed completion-receipt reason codes (`unsafe_path`, `output_mismatch`, …) in redacted diagnostics, and the authoring-station failure list is captured as a sanitized junit-derived node-ID artifact for the phase-B Linux diff.

## Acceptance boundaries

- No schema migration, no new endpoints beyond relabeling, no live rows claimed. Docker build/run itself stays `NOT_RUN` on this station (no Docker) and is the first phase-B step.
- All fixes are statically checkable or covered by offline tests on this workstation.

## Explicitly deferred

Linux phase B (digest-pinned image build, the doctor preflight inside the container, Chromium launch as the runtime user, restart persistence, backup-restore drill) and every live qualification row stay with execution 0047 / the release checklist.
