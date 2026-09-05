**English** | [中文](status.zh.md)

# Unified project status (single source of truth)

Delivered implementation boundary: execution 0054, including [phase B](executions/0054-media-library-server-integration/phase-b/plan.md), is delivered through implementation/verification commits `b4af46d`, `ff5da07`, `88f5ed0`, `22bd9ef`, `48ecbe9`, and `d8bbdf7`. It adds bounded exact provider/path lookup and truthful absent-to-unique-match post-refresh observation while preserving legacy acceptance-only refresh, then verifies Operation races against a real PostgreSQL service. The planning boundary now includes [execution 0055 Phase A](executions/0055-operator-auth-playback-evidence/goal.md), frozen against `d0a8cc2`, for fail-closed single-operator authentication followed by append-only authenticated playback evidence; implementation and implementation verification have not started. The current 51-route API remains anonymous, playback evidence remains `NOT_IMPLEMENTED`, and live playback remains `NOT_RUN`. Provider task completion remains unsupported by the common APIs and is not a phase-B or 0055-A claim. Execution 0047 remains the open P0 operator gate, and its Linux persistence/recovery/process checks plus every implemented live login/crawl/CDN/media-server row remain `NOT_RUN`. Absent capabilities are `NOT_IMPLEMENTED`, not unexecuted live rows. This table is the canonical status view; per-execution detail lives in [`executions/`](README.md) and evidence in each verification record. Update this page at every closeout.

## Milestone status

| Milestone | Status |
| --- | --- |
| Offline feature work | Platform shapes frozen at the 0039 boundary plus 0040/0044 operations and the 0050 Console v2 control-plane foundation; 0043 (danmaku/subtitles) remains deferred |
| REST API + web console | 0050–0053 foundations plus execution 0054 safe managed-tree paging, redacted media-server posture, durable acceptance-only and author-observation Operations, exact item lookup, qualification schema v2, and truthful Library/Settings/Jobs evidence are delivered; 0055-A authentication is frozen only as a plan and the current API remains anonymous |
| Operator authentication + playback evidence | 0055-A bilingual goal/plan/progress/verification are frozen at the planning boundary; implementation has not started, revision `0008_playback_evidence` does not exist, playback evidence is `NOT_IMPLEMENTED`, and live playback is `NOT_RUN` |
| Docker packaging | Candidate image plus reproducibility hardening and the Node-free multi-stage Console v2 build delivered (0041, 0048–0050); the repaired operator image built/started with green doctor, deep readiness and Chromium launch |
| Operations docs / security review / release checklist | Delivered (0045, 0046) |
| Live qualification (final gate) | Open — execution 0047, operator-assisted on Linux |

## Verification matrix

| Dimension | State | Evidence / blocker |
| --- | --- | --- |
| Implementation (offline shapes) | 15+ frozen shapes across seven platforms | Executions 0013–0039 records |
| Offline complete suite | Execution 0054 phase-B closeout suite with real PostgreSQL enabled: `2763 passed, 3 skipped, 1 warning in 544.08s`; skips are the three Windows-inapplicable POSIX venv/mode cases and the warning is the existing Starlette/httpx deprecation | Execution 0054 phase-B verification |
| API/console tests | Phase-B backend union 350 passed; qualification/Library/API focus 70 passed; Library application focus 12 passed; 69 Web tests across 7 files plus format, Svelte check and production build pass. Focused selections overlap; no phase-B browser smoke or real media-server qualification is claimed | Execution 0054 phase-B verification |
| Static gates (ruff/format/mypy/compileall/docs/frontend check/build) | Execution 0054 whole-repository Ruff/format, strict mypy, compileall, sdist/wheel, bilingual docs, Web format/test/check/build, two locked upstreams, tracked-output/confidentiality/host-path audit and `git diff --check` pass | Execution 0054 phase-B verification |
| Docker image build | `PASS` for build/runtime preflight: repaired image started; doctor and deep readiness are `ready`; runtime Chromium `151.0.7922.34` matches the build manifest | Executions 0050 and 0047 verification |
| Container readiness / restart persistence / backup-restore drill | Deep readiness `PASS`; restart persistence and backup/restore `NOT_RUN` | Execution 0047; docs/operations.md procedures ready |
| Live login (any platform) | `NOT_RUN` — operator (Phase C canary: Bilibili + XHS) | Execution 0047 |
| Live crawl / download / incrementality | `NOT_RUN` — operator (Phases C–E) | Execution 0047 |
| Real Emby/Jellyfin connection, Library discovery and targeted-refresh acceptance | `NOT_RUN` — implemented in 0054-A but no authorized server was used | Executions 0054 and 0047 |
| Provider/path item lookup and post-refresh item observation | `IMPLEMENTED / NOT_RUN` — local/mock gates pass, but no authorized real Emby/Jellyfin server was used | Execution 0054-B verification |
| Provider task completion | `NOT_IMPLEMENTED` — the common Emby/Jellyfin refresh APIs provide no durable task identity; phase B does not claim it | Execution 0054-B truth boundary |
| Operator access control | `NOT_IMPLEMENTED` — the baseline FastAPI application still has 51 anonymous routes; 0055-A freezes fail-before-bind single-operator session/CSRF and optional separate Bearer authentication, but no implementation test has run | Execution 0055-A [goal](executions/0055-operator-auth-playback-evidence/goal.md) and [verification](executions/0055-operator-auth-playback-evidence/verification.md) |
| Playback-evidence mutation / automatic post-export scan | `NOT_IMPLEMENTED` — the 0055-A playback-evidence plan is frozen but no code or revision `0008_playback_evidence` exists; automatic chaining is excluded from phase A and has no frozen assignment | Execution 0055-A [plan](executions/0055-operator-auth-playback-evidence/plan.md) and execution 0054 qualification boundary |
| External security audit | `NOT_RUN` — optional | docs/security-review.md residual risks |

## Release blockers (v0.1.0-rc1)

1. Linux-host baseline incomplete (complete suite, host-port review, restart persistence, backup-restore and process baseline) — Phase B.
2. Zero live rows recorded — Phase C canary (Bilibili + XHS) then remaining platforms.

Minimum 0.1 release condition: at least the two canary platforms reach **Supported** (login, sync, download, true incrementality, Emby rescan + sample playback), every other platform honestly classified (Experimental / Metadata-only / Blocked External / Unsupported), and the project describes itself as "seven-platform adapter framework; see the status matrix" rather than "supports seven platforms".
