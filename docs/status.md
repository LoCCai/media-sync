**English** | [中文](status.zh.md)

# Unified project status (single source of truth)

The pushed planning baseline is execution 0055 commit `4564b2a`; the current working change partially implements [execution 0055 Phase A](executions/0055-operator-auth-playback-evidence/goal.md) (implementation reference: **pending in this change**). The backend now resolves a required typed operator credential before bind, supports an optional distinct Bearer credential, enforces exact Host/Origin policy, issues a rotating process-local HttpOnly `SameSite=Strict` session cookie, requires CSRF on unsafe cookie-authenticated methods, applies deny-by-default ASGI protection with an exact anonymous allowlist, accepts only strict bounded login JSON, and wires the credential/origin contract into Docker Compose. The 190-test auth/API focus and complete offline regression (`2811 passed, 14 skipped, 1 warning in 561.43s`) pass, as do 69 Web tests and all locally available static/build/docs/package gates. Three skips are Windows/POSIX differences; 11 real-PostgreSQL races and Docker validation were unavailable on this workstation and are not claimed. This is not the complete 0055 exit gate: Console v2 and `/legacy` do not yet implement login/session/CSRF integration, so the Web console is not currently an operable administration surface; revision `0008_playback_evidence` and playback-evidence persistence/API/UI are still absent. Playback evidence remains `NOT_IMPLEMENTED`, live playback remains `NOT_RUN`, and every execution 0047 live qualification row remains `NOT_RUN`. Provider task completion remains unsupported by the common APIs and is not a 0054-B or 0055-A claim. Execution 0047 remains the open P0 operator gate; absent capabilities are `NOT_IMPLEMENTED`, not unexecuted live rows. This table is the canonical status view; per-execution detail lives in [`executions/`](README.md) and evidence in each verification record. Update this page at every closeout.

## Milestone status

| Milestone | Status |
| --- | --- |
| Offline feature work | Platform shapes frozen at the 0039 boundary plus 0040/0044 operations and the 0050 Console v2 control-plane foundation; 0043 (danmaku/subtitles) remains deferred |
| REST API + web console | 0050–0053 foundations plus execution 0054 safe managed-tree paging, redacted media-server posture, durable acceptance-only and author-observation Operations, exact item lookup, qualification schema v2, and truthful Library/Settings/Jobs evidence are delivered; the 0055-A backend authentication boundary is implemented in the current change, but Web login/session/CSRF integration is pending and the console is not currently an operable administration surface |
| Operator authentication + playback evidence | The 0055-A backend single-operator boundary is implemented and its complete locally available offline gates pass (implementation reference **pending in this change**); Web authentication integration, revision `0008_playback_evidence`, playback-evidence persistence/API/UI and qualification schema v3 remain pending. Playback evidence is `NOT_IMPLEMENTED` and live playback is `NOT_RUN` |
| Docker packaging | Candidate image plus reproducibility hardening and the Node-free multi-stage Console v2 build delivered (0041, 0048–0050); the repaired operator image built/started with green doctor, deep readiness and Chromium launch |
| Operations docs / security review / release checklist | Delivered (0045, 0046) |
| Live qualification (final gate) | Open — execution 0047, operator-assisted on Linux |

## Verification matrix

| Dimension | State | Evidence / blocker |
| --- | --- | --- |
| Implementation (offline shapes) | 15+ frozen shapes across seven platforms | Executions 0013–0039 records |
| Offline complete suite | Current 0055 backend slice: `2811 passed, 14 skipped, 1 warning in 561.43s`; 3 skips are Windows/POSIX differences, 11 are real-PostgreSQL races without a configured URL, and the warning is the existing Starlette/httpx deprecation | Execution 0055-A verification; execution 0054 remains the latest real-PostgreSQL comparison |
| API/console tests | Current 0055 auth/config/seven-API focus passes `190 passed, 1 warning in 41.99s`; existing Web suite passes 69 tests plus format/check/build. No Web login/session/CSRF implementation or authenticated browser smoke is claimed | Execution 0055-A verification |
| Static gates (ruff/format/mypy/compileall/docs/frontend check/build) | Current 0055 whole-repository Ruff/format, strict mypy (104 files), compileall, 498-doc link check, two locked upstreams, Web format/check/build, distribution build and diff checks pass | Execution 0055-A verification |
| Docker image build | The 0050/0047 image preflight remains historical PASS. Current 0055 auth-aware Compose wiring is code-reviewed but `NOT_RUN` because Docker CLI is unavailable on this workstation | Executions 0050/0047 and 0055-A verification |
| Container readiness / restart persistence / backup-restore drill | Deep readiness `PASS`; restart persistence and backup/restore `NOT_RUN` | Execution 0047; docs/operations.md procedures ready |
| Live login (any platform) | `NOT_RUN` — operator (Phase C canary: Bilibili + XHS) | Execution 0047 |
| Live crawl / download / incrementality | `NOT_RUN` — operator (Phases C–E) | Execution 0047 |
| Real Emby/Jellyfin connection, Library discovery and targeted-refresh acceptance | `NOT_RUN` — implemented in 0054-A but no authorized server was used | Executions 0054 and 0047 |
| Provider/path item lookup and post-refresh item observation | `IMPLEMENTED / NOT_RUN` — local/mock gates pass, but no authorized real Emby/Jellyfin server was used | Execution 0054-B verification |
| Provider task completion | `NOT_IMPLEMENTED` — the common Emby/Jellyfin refresh APIs provide no durable task identity; phase B does not claim it | Execution 0054-B truth boundary |
| Operator access control | `IMPLEMENTED / offline verification PASS` — the backend fails before bind without its required typed credential, enforces exact Host/Origin plus deny-by-default route protection, and supports a rotating HttpOnly session with CSRF plus an optional distinct Bearer credential. The 190-test focus and complete locally available suite pass. Web login/session/CSRF integration remains pending, so no operable authenticated console or live qualification is claimed | Execution 0055-A [goal](executions/0055-operator-auth-playback-evidence/goal.md) and [verification](executions/0055-operator-auth-playback-evidence/verification.md); implementation reference **pending in this change** |
| Playback-evidence mutation / automatic post-export scan | `NOT_IMPLEMENTED` — the 0055-A playback-evidence plan is frozen but no code or revision `0008_playback_evidence` exists; automatic chaining is excluded from phase A and has no frozen assignment | Execution 0055-A [plan](executions/0055-operator-auth-playback-evidence/plan.md) and execution 0054 qualification boundary |
| External security audit | `NOT_RUN` — optional | docs/security-review.md residual risks |

## Release blockers (v0.1.0-rc1)

1. Linux-host baseline incomplete (complete suite, host-port review, restart persistence, backup-restore and process baseline) — Phase B.
2. Zero live rows recorded — Phase C canary (Bilibili + XHS) then remaining platforms.

Minimum 0.1 release condition: at least the two canary platforms reach **Supported** (login, sync, download, true incrementality, Emby rescan + sample playback), every other platform honestly classified (Experimental / Metadata-only / Blocked External / Unsupported), and the project describes itself as "seven-platform adapter framework; see the status matrix" rather than "supports seven platforms".
