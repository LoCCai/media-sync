**English** | [中文](status.zh.md)

# Unified project status (single source of truth)

Boundary: execution 0048 (release-candidate calibration). This table is the canonical status view; per-execution detail lives in [`executions/`](README.md) and evidence in each verification record. Update this page at every closeout.

## Milestone status

| Milestone | Status |
| --- | --- |
| Offline feature work | Frozen at the 0039 boundary (multi-live gallery) plus 0040 (API/console) and the 0044-minimal operations endpoints; 0043 (danmaku/subtitles) deferred to 0.2 |
| REST API + web console | Implemented (0040, 0044-minimal); hardened operations UI deferred to 0.2 |
| Docker packaging | Candidate files + reproducibility hardening delivered (0041, 0048); the 0049 RC-precondition fixes (lock-relative checkout with `.git`, shared Playwright path, runtime-user Chromium launch in the manifest) await their first real build/run on the operator host |
| Operations docs / security review / release checklist | Delivered (0045, 0046) |
| Live qualification (final gate) | Open — execution 0047, operator-assisted on Linux |

## Verification matrix

| Dimension | State | Evidence / blocker |
| --- | --- | --- |
| Implementation (offline shapes) | 15+ frozen shapes across seven platforms | Executions 0013–0039 records |
| Offline complete suite | ``33 failed, 2031 passed, 1 skipped` (authoring workstation, execution 0048)` on the authoring workstation; Python 3.11/3.12/3.13 matrix `: sync green and suites run on 3.11.16/3.12.14/3.13.15; all 33 divergences are child-process tests failing identically on a clean checkout of that workstation` | Execution 0048 verification; Linux-host rerun required before RC per Phase B; sanitized node-ID artifact `artifacts/pytest-windows-0049.xml` (junit) captured for the per-test Linux diff; Windows-native runs are Experimental until the divergences are classified |
| API/console tests | Included in the complete suite | Execution 0048 verification |
| Static gates (ruff/format/mypy/compileall/docs) | Green at 0048 | Execution 0048 verification |
| Docker image build | `NOT_RUN` on authoring machine (no Docker); the operator builds on Linux from the 0049-fixed Dockerfile, gated by the in-container doctor preflight and a `mediasync` Chromium launch | Phase B, first release blocker |
| Container health / restart persistence / backup-restore drill | `NOT_RUN` — operator (Phase B) | docs/operations.md procedures ready |
| Live login (any platform) | `NOT_RUN` — operator (Phase C canary: Bilibili + XHS) | Execution 0047 |
| Live crawl / download / incrementality | `NOT_RUN` — operator (Phases C–E) | Execution 0047 |
| Real Emby/Jellyfin rescan + playback | `NOT_RUN` — mandatory for Supported tier (Phase E/F) | Execution 0047 acceptance rules |
| External security audit | `NOT_RUN` — optional | docs/security-review.md residual risks |

## Release blockers (v0.1.0-rc1)

1. Linux-host baseline incomplete (image build, health, restart persistence, backup-restore drill) — Phase B.
2. Zero live rows recorded — Phase C canary (Bilibili + XHS) then remaining platforms.

Minimum 0.1 release condition: at least the two canary platforms reach **Supported** (login, sync, download, true incrementality, Emby rescan + sample playback), every other platform honestly classified (Experimental / Metadata-only / Blocked External / Unsupported), and the project describes itself as "seven-platform adapter framework; see the status matrix" rather than "supports seven platforms".
