**English** | [中文](delivery-priorities.zh.md)

# Delivery priority addendum

- Date: 2026-09-05
- Input: user review of `main` at `13de3b7`, received during projection closeout
- Decision: finish and publish the already-tested increment first; the user has subsequently requested continuation into P0

## Scope and verified findings

The seven-platform login/subscription/capture and Emby/Jellyfin goal remains unchanged. Frozen goals/plans remain historical contracts; this addendum changes execution order, not safety requirements. Current main is a development integration checkpoint, not a complete upgrade-ready release. No new platform, media shape or operations subsystem is authorized by this closeout.

Static inspection confirms the missing login/session/CSRF frontend, runtime UID 1000, file-backed Compose credential mount, and `db init` before `serve`. A root-owned 0600 source can be unreadable to the runtime user under ordinary rootful Linux permissions. This is a conditional risk, not an observed failure on the user's host. Read projection and qualification v3 are now implemented, superseding that one outstanding item in the older review. Current-publication attestation remains separate from platform qualification and never proves playback telemetry.

## Ordered next work and exit conditions

| Priority | Bounded work | Exit evidence |
| --- | --- | --- |
| P0 | Safe usable console: login, session bootstrap, memory-only CSRF, logout, expiry/401 reset; credential-read and configuration preflight before upgrade mutations | Final image and real HTTP backend/browser: anonymous entry → login → accounts/tasks read → CSRF-protected mutation → QR/media/SSE → logout/expiry. Unreadable credentials fail preflight without migrating the database |
| P0 | Current Linux image baseline | Exact commit and image ID, runtime-user secret readability, configuration, migration boundary, startup, restart/volume persistence and backup restore; never reuse 0050 historical PASS |
| P0 | Bilibili and XHS authorized canaries | Account → subscription → sync → download → archive → media library, unchanged rerun, real new content, actual playback or supported image/text display. Keep redacted evidence and explicit per-step results in execution 0047 |
| P1 | Finish already-promised UI and semantics | Minimal current/history evidence display and attestation; distinguish refresh-request acceptance from first-import verification. New-content verification stays explicitly unimplemented until delivered |

Canaries may use existing CLI with user-authorized accounts/server access while frontend work is unfinished; extra qualification UI is not a prerequisite. Do not capture, request or commit raw credentials/cookies. Unknown live outcomes remain NOT_RUN or the applicable explicit failure state.

## Deployment and upgrade boundary

Keep the credential source restricted and align its owner/read access with the actual mapped runtime identity. Do not use world-readable modes, blanket recursive ownership changes or assumed Compose secret uid/gid/mode remapping. The [deployment guide](../../deployment.md) now gives a manual final-image read check that overrides the normal entrypoint. Rootless/user-namespace mappings need host-specific verification.

The current entrypoint still migrates before `serve` validates authentication. A failed server start does not prove an untouched database. Back up before upgrade; preflight without the normal entrypoint; respect populated revision-0008 downgrade refusal. Automated startup/pre-migration validation remains P0 work, not a completed fix.

## Truth and product semantics

Platform qualification is a version/platform live acceptance record. Author evidence is an attestation associated with one publication/remote observation. A publication change can make that attestation stale without rewriting platform qualification. Neither matching identity nor a ledger POST proves that video played.

Use three distinct concepts: submit library refresh (acceptance only), verify first import (previously absent author becomes a unique match), and verify new content (future per-publication-item capability). Existing absent-to-match logic is not a general incrementality check. Large API/CLI file decomposition follows the first real loop and is limited to touched shared construction/business entry points; no architecture rewrite is scheduled now.

## Verification and resumption

Current workstation results are in [projection verification](evidence-projection/verification.md). Docker, real PostgreSQL, current-image browser integration, live platform/media-server checks and restart/restore remain unexecuted here. The supplied review's GitHub Actions run-count observation was not independently rechecked; local tests are not CI runs. Inspect CI availability and add real frontend/backend and final-image coverage during P0 work.

The earlier pause request was superseded by the user's continuation request. After GitHub synchronization, inspect clean Git status/current remote and this addendum, then start the P0 console/credential checkpoint. Long-term roadmap items remain a backlog, not additional prerequisites to the first authorized real run or all mandatory 0.1 release gates.
