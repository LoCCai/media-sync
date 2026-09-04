**English** | [中文](status.zh.md)

# Unified project status (single source of truth)

Boundary: execution 0052 is delivered, frozen-verified and pushed at `be26cc7`; execution 0053 planning and pre-change baseline are complete and implementation is active. Execution 0047 remains the open P0 operator gate, and its Linux persistence/recovery/process checks plus every live login/crawl/CDN and real Emby/Jellyfin row remain `NOT_RUN`. This table is the canonical status view; per-execution detail lives in [`executions/`](README.md) and evidence in each verification record. Update this page at every closeout.

## Milestone status

| Milestone | Status |
| --- | --- |
| Offline feature work | Platform shapes frozen at the 0039 boundary plus 0040/0044 operations and the 0050 Console v2 control-plane foundation; 0043 (danmaku/subtitles) remains deferred |
| REST API + web console | SvelteKit 5 Console v2 foundation (0050), the capability-driven account/subscription workbench (0051), and the 0052 durable Operation/Event task center are delivered; 0053 is active for safe content/asset details, archive preview and catalogue routes |
| Docker packaging | Candidate image plus reproducibility hardening and the Node-free multi-stage Console v2 build delivered (0041, 0048–0050); the repaired operator image built/started with green doctor, deep readiness and Chromium launch |
| Operations docs / security review / release checklist | Delivered (0045, 0046) |
| Live qualification (final gate) | Open — execution 0047, operator-assisted on Linux |

## Verification matrix

| Dimension | State | Evidence / blocker |
| --- | --- | --- |
| Implementation (offline shapes) | 15+ frozen shapes across seven platforms | Executions 0013–0039 records |
| Offline complete suite | Execution 0052 frozen suite: `2315 passed, 3 skipped, 1 warning in 555.05s`; skips are the three Windows-inapplicable POSIX venv/permission cases and the warning is the existing Starlette/httpx deprecation. Linux phase B remains authoritative | Execution 0052 verification |
| API/console tests | Execution 0052 focused Operation/API integration `241 passed`; support service/HTTP `30 passed`; Web `17 passed`, Svelte check 0 errors/0 warnings and production build pass. Focused selections overlap; real Jobs-route browser interaction remains follow-up quality debt | Execution 0052 verification |
| Static gates (ruff/format/mypy/compileall/docs/frontend check/build) | 0052 whole-repository Ruff, 662-file format check, strict mypy over 94 source files, compileall, sdist/wheel, 466-file docs check, Web format/check/test/build, two locked upstreams, 733-file tracked-output audit and `git diff --check` all pass | Execution 0052 verification |
| Docker image build | `PASS` for build/runtime preflight: repaired image started; doctor and deep readiness are `ready`; runtime Chromium `151.0.7922.34` matches the build manifest | Executions 0050 and 0047 verification |
| Container readiness / restart persistence / backup-restore drill | Deep readiness `PASS`; restart persistence and backup/restore `NOT_RUN` | Execution 0047; docs/operations.md procedures ready |
| Live login (any platform) | `NOT_RUN` — operator (Phase C canary: Bilibili + XHS) | Execution 0047 |
| Live crawl / download / incrementality | `NOT_RUN` — operator (Phases C–E) | Execution 0047 |
| Real Emby/Jellyfin rescan + playback | `NOT_RUN` — mandatory for Supported tier (Phase E/F) | Execution 0047 acceptance rules |
| External security audit | `NOT_RUN` — optional | docs/security-review.md residual risks |

## Release blockers (v0.1.0-rc1)

1. Linux-host baseline incomplete (complete suite, host-port review, restart persistence, backup-restore and process baseline) — Phase B.
2. Zero live rows recorded — Phase C canary (Bilibili + XHS) then remaining platforms.

Minimum 0.1 release condition: at least the two canary platforms reach **Supported** (login, sync, download, true incrementality, Emby rescan + sample playback), every other platform honestly classified (Experimental / Metadata-only / Blocked External / Unsupported), and the project describes itself as "seven-platform adapter framework; see the status matrix" rather than "supports seven platforms".
