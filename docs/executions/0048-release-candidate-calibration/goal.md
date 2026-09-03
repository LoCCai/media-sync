**English** | [中文](goal.zh.md)

# Execution 0048 goal

- Status: Complete for the release-candidate calibration scope (documentation, hardening, 0044-minimal implementation, fresh offline numbers)
- Date: 2026-09-03
- Predecessor: Execution 0047 start records (0042–0047 series)
- Scope: Switch the project from feature-expansion mode to release-candidate verification mode per the external review: calibrate repository truth, harden build reproducibility, deliver the rescoped 0044 operations slice, restructure 0047 into a canary-first acceptance master phase, and re-establish fresh offline verification numbers at the current HEAD

## Outcome

1. **Repository truth**: both READMEs rewritten as slim status pages (version/status/latest verification/live status/blockers) pointing at the new single source of truth `docs/status.md`(+`.zh.md`); architecture docs updated so REST API/console/Docker/supervisor claims match reality; execution-index rows for 0042–0047 already delivered by the prior series.
2. **Scope calibration**: 0043 (danmaku/subtitles) explicitly deferred to 0.2; 0044 rescoped to the minimum operations-recovery slice and implemented; 0047 rewritten as the operator acceptance master phase with support tiers, canary ordering (Bilibili + XHS), per-platform sample matrices, the idempotent-vs-true-increment split, mandatory Emby checks and an allowed defect-fix loop.
3. **0044-minimal delivered**: `GET /api/v1/subscriptions/{id}` (schedule + recent runs + recent jobs), `GET /api/v1/scheduler/jobs/{id}`, `POST /api/v1/assets/{id}/download` as a tracked background operation; the CLI `asset download` body extracted into a shared `_execute_asset_download` so CLI and API drive identical gates; console gains the subscription detail drawer and per-asset re-download; offline API tests extended and passing.
4. **Build reproducibility**: uv pinned (`uv==0.12.9`); `BASE_IMAGE` ARG with documented digest-pinning procedure; `docker/mediacrawler-requirements.lock` compiled with hashes for linux/Python 3.13 from the pinned upstream requirements (78 packages, playwright pinned to 1.62.0 and thereby the Chromium revision); image build writes `/opt/BUILD-MANIFEST.txt` (Python/uv/ffmpeg/playwright/Chromium versions + both pip freezes); compose documents the Emby bind-mount pattern.
5. **Python support clarified by execution, not comments**: the 3.11/3.12/3.13 sync+test matrix ran on the authoring workstation; `requires-python` stays `>=3.11,<3.14` per the result.
6. **Real defect found and fixed by the fresh numbers**: the JSONL reader freezes inner lists to tuples, so the 0039 multi-live v2 branch (`isinstance(..., list)`) quarantined every real record — fixed to accept `(list, tuple)`; the affected tests (which had only been collected, never executed) now pass.

## Acceptance boundaries

- No deployment or live-platform verification is performed on any authoring machine (operator direction): Docker build/run and every live row remain Phase B+/0047 operator items on Linux.
- A small set of scheduler-handler process-protocol tests fail identically on a clean checkout of this workstation; they are recorded as workstation-suspect and the Linux-host suite rerun is the authoritative adjudicator (Phase B step 1).
- No schema migration; no new authority beyond the 0044 service-backed endpoints.

## Explicitly deferred

Danmaku/subtitles (0043 → 0.2), operations UI polish (0.2), Debian apt snapshot pinning, full SBOM tooling, CI dependency scanning, external security audit.
