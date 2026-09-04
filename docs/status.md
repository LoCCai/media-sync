**English** | [中文](status.zh.md)

# Unified project status (single source of truth)

Boundary: execution 0054-A is delivered and frozen-verified from baseline `22b5864` and plans `793d33b`/`d913537`; execution 0054 remains open for a separately frozen phase B covering scan completion and provider/path item lookup. Execution 0047 remains the open P0 operator gate, and its Linux persistence/recovery/process checks plus every implemented live login/crawl/CDN/media-server row remain `NOT_RUN`. Absent capabilities are `NOT_IMPLEMENTED`, not unexecuted live rows. This table is the canonical status view; per-execution detail lives in [`executions/`](README.md) and evidence in each verification record. Update this page at every closeout.

## Milestone status

| Milestone | Status |
| --- | --- |
| Offline feature work | Platform shapes frozen at the 0039 boundary plus 0040/0044 operations and the 0050 Console v2 control-plane foundation; 0043 (danmaku/subtitles) remains deferred |
| REST API + web console | 0050–0053 foundations plus 0054-A safe managed-tree paging, redacted media-server posture, durable probe/targeted-refresh Operations and qualification evidence are delivered; 0054-B scan completion/item lookup is not yet frozen |
| Docker packaging | Candidate image plus reproducibility hardening and the Node-free multi-stage Console v2 build delivered (0041, 0048–0050); the repaired operator image built/started with green doctor, deep readiness and Chromium launch |
| Operations docs / security review / release checklist | Delivered (0045, 0046) |
| Live qualification (final gate) | Open — execution 0047, operator-assisted on Linux |

## Verification matrix

| Dimension | State | Evidence / blocker |
| --- | --- | --- |
| Implementation (offline shapes) | 15+ frozen shapes across seven platforms | Executions 0013–0039 records |
| Offline complete suite | Execution 0054-A frozen suite: `2620 passed, 3 skipped, 1 warning in 505.44s`; skips are the three Windows-inapplicable POSIX venv/mode cases and the warning is the existing Starlette/httpx deprecation. Linux phase B remains authoritative | Execution 0054 verification |
| API/console tests | Connector focus 52 passed; Operation modules 62 passed; 58 Web units, format, Svelte check, production build and local Library/Settings/Jobs browser smoke pass. Focused selections overlap; real platform/media-server qualification remains external | Execution 0054 verification |
| Static gates (ruff/format/mypy/compileall/docs/frontend check/build) | Execution 0054-A whole-repository Ruff and 213-file Python format check, strict mypy over 101 source files, compileall, sdist/wheel, 482-doc check, Web format/check/test/build, two locked upstreams, tracked-output/confidentiality audit and `git diff --check` all pass | Execution 0054 verification |
| Docker image build | `PASS` for build/runtime preflight: repaired image started; doctor and deep readiness are `ready`; runtime Chromium `151.0.7922.34` matches the build manifest | Executions 0050 and 0047 verification |
| Container readiness / restart persistence / backup-restore drill | Deep readiness `PASS`; restart persistence and backup/restore `NOT_RUN` | Execution 0047; docs/operations.md procedures ready |
| Live login (any platform) | `NOT_RUN` — operator (Phase C canary: Bilibili + XHS) | Execution 0047 |
| Live crawl / download / incrementality | `NOT_RUN` — operator (Phases C–E) | Execution 0047 |
| Real Emby/Jellyfin connection, Library discovery and targeted-refresh acceptance | `NOT_RUN` — implemented in 0054-A but no authorized server was used | Executions 0054 and 0047 |
| Scan completion and provider/path item lookup | `NOT_IMPLEMENTED` — separately frozen 0054-B scope; no human status | Execution 0054 qualification boundary |
| Playback-evidence mutation / automatic post-export scan | `NOT_IMPLEMENTED` — playback recording remains 0055; automatic chaining has no frozen assignment | Execution 0054 qualification boundary |
| External security audit | `NOT_RUN` — optional | docs/security-review.md residual risks |

## Release blockers (v0.1.0-rc1)

1. Linux-host baseline incomplete (complete suite, host-port review, restart persistence, backup-restore and process baseline) — Phase B.
2. Zero live rows recorded — Phase C canary (Bilibili + XHS) then remaining platforms.

Minimum 0.1 release condition: at least the two canary platforms reach **Supported** (login, sync, download, true incrementality, Emby rescan + sample playback), every other platform honestly classified (Experimental / Metadata-only / Blocked External / Unsupported), and the project describes itself as "seven-platform adapter framework; see the status matrix" rather than "supports seven platforms".
