**English** | [中文](status.zh.md)

# Unified project status (single source of truth)

Boundary: execution 0050 (Web Console v2 foundation). This table is the canonical status view; per-execution detail lives in [`executions/`](README.md) and evidence in each verification record. Update this page at every closeout.

## Milestone status

| Milestone | Status |
| --- | --- |
| Offline feature work | Platform shapes frozen at the 0039 boundary plus 0040/0044 operations and the 0050 Console v2 control-plane foundation; 0043 (danmaku/subtitles) remains deferred |
| REST API + web console | SvelteKit 5 Console v2 foundation implemented (0050): nine routed surfaces, real existing operations, content/library projections, one-time acknowledgement and `/legacy` rollback; persistence/SSE/logs remain follow-ups |
| Docker packaging | Candidate image plus reproducibility hardening and the Node-free multi-stage Console v2 build delivered (0041, 0048–0050); the 0050 image awaits its first real build/run on the operator host |
| Operations docs / security review / release checklist | Delivered (0045, 0046) |
| Live qualification (final gate) | Open — execution 0047, operator-assisted on Linux |

## Verification matrix

| Dimension | State | Evidence / blocker |
| --- | --- | --- |
| Implementation (offline shapes) | 15+ frozen shapes across seven platforms | Executions 0013–0039 records |
| Offline complete suite | Execution 0050 authoring-station run with uv + ffmpeg/ffprobe available: `2038 passed, 33 failed, 1 skipped`; all 33 belong to the Windows completion-receipt/process family already observed as nondeterministic (0048: 33/35 failures; 0049: one green run). Windows stays Experimental and Linux phase B remains authoritative | Execution 0050 verification and sanitized junit grouping; raw XML remains git-ignored under `artifacts/` |
| API/console tests | API `9 passed`; checkout/license focus `16 passed`; Svelte units `2 passed`; nine-route browser smoke and one-time acknowledgement interaction pass with zero console errors | Execution 0050 verification |
| Static gates (ruff/format/mypy/compileall/docs/frontend check/build) | Green for 0050 changed scope | Execution 0050 verification |
| Docker image build | `NOT_RUN` on authoring machine (no Docker); the operator builds the 0050 Dockerfile on Linux, then gates it with static-bundle manifest facts, the in-container doctor preflight and a `mediasync` Chromium launch | Phase B, first release blocker |
| Container health / restart persistence / backup-restore drill | `NOT_RUN` — operator (Phase B) | docs/operations.md procedures ready |
| Live login (any platform) | `NOT_RUN` — operator (Phase C canary: Bilibili + XHS) | Execution 0047 |
| Live crawl / download / incrementality | `NOT_RUN` — operator (Phases C–E) | Execution 0047 |
| Real Emby/Jellyfin rescan + playback | `NOT_RUN` — mandatory for Supported tier (Phase E/F) | Execution 0047 acceptance rules |
| External security audit | `NOT_RUN` — optional | docs/security-review.md residual risks |

## Release blockers (v0.1.0-rc1)

1. Linux-host baseline incomplete (image build, health, restart persistence, backup-restore drill) — Phase B.
2. Zero live rows recorded — Phase C canary (Bilibili + XHS) then remaining platforms.

Minimum 0.1 release condition: at least the two canary platforms reach **Supported** (login, sync, download, true incrementality, Emby rescan + sample playback), every other platform honestly classified (Experimental / Metadata-only / Blocked External / Unsupported), and the project describes itself as "seven-platform adapter framework; see the status matrix" rather than "supports seven platforms".
