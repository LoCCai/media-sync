**English** | [中文](verification.zh.md)

# Verification

Implementation revision: `d6db86a`. Planning revision: `dadd198`.

## Final results

| Gate | Result | Evidence and boundary |
| --- | --- | --- |
| Provenance/API/CLI focus | `PASS` | `13 passed, 1 warning in 2.35s` for the complete provenance file plus the exact deep-readiness API projection. The final doctor-focused selection passed `18`; pass and blocked deep CLI paths both emit the shared report, forward the explicit license acknowledgement and return the expected exit status. |
| Complete Python suite | `PASS` | `7140 passed, 42 skipped, 1 warning in 1379.51s (0:22:59)`. Skips are the documented Windows/POSIX differences and unconfigured real-PostgreSQL qualifications; the warning is the existing Starlette/httpx deprecation. |
| Complete media-sync Web suite | `PASS` | `28 files / 825 tests` passed; the new deployment-evidence projection alone passed `1 file / 5 tests`. |
| Svelte and production Web build | `PASS` | `svelte-check` reported 0 errors and 0 warnings. Vite transformed 4,088 server and 4,097 client modules and wrote the static build. |
| Frontend formatting | `PASS` | Repository Web Prettier check passed, including the Svelte page, TypeScript projection and tests. |
| Python lint/format/type/compile | `PASS` | Ruff lint passed; Ruff format reported 1,186 files already formatted; strict mypy passed 160 source files; compileall passed `src`, `tests` and `scripts`. |
| Locked dependencies and upstreams | `PASS` | `uv lock --check` resolved 62 packages unchanged; `scripts/check_upstreams.py` verified both locked checkouts. |
| Python packaging | `PASS` | A fresh 798,181-byte wheel (185 members) and 3,197,365-byte sdist (1,316 members) built successfully. Both contain migration `0015` and the current CLI; neither contains project Git metadata, `.mimosa`, runtime archive/export/job/log roots, a database or partial file. |
| Docker/Compose contract | `PASS` / `NOT_RUN` | Unit/static checks cover the source argument, closed validation, manifest line, OCI label, Compose forwarding and root `.git` exclusion. Prettier parsed the Compose YAML. Docker is not installed on this workstation, so Dockerfile execution, built-label inspection and Linux runtime behavior remain `NOT_RUN`. |
| Documentation links/whitespace | `PASS` | `scripts/check_docs.py` checked 774 Markdown files successfully; final `git diff --check` passed. |
| Deployment, PostgreSQL and live services | `NOT_RUN` | No server/container mutation, real PostgreSQL, platform request, Subscription execution, media download, host library read, restart or supervisor control occurred. |

## Findings corrected during closeout

1. The initial local implementation lacked the CLI half of the planned API/supervisor comparison. `doctor --deep` now calls `collect_deep_readiness_report` directly; focused tests prove the same payload and both success/blocked exit states.
2. The first CLI patch reused the ordinary `report` variable and widened its inferred type. Strict mypy rejected five downstream accesses; an isolated `deep_report` variable corrected the type without changing legacy `doctor --json`.
3. The first full Python run was deliberately interrupted after the CLI gap was found, and the next was interrupted immediately after the type correction. Neither partial run is counted as final evidence; only the clean final-source run above controls status.

## Qualification boundary

- The post-push [online observation](online-observation-2026-09-09.md) found a healthy pinned checkout/runtime but an authenticated UI without any 0077 source/migration/continuation field. It does not identify the running application commit or current database migration, so no live state is upgraded.
- A valid source SHA identifies build input; it does not prove a clean checkout, correct persistent mounts, a current database, a qualified upstream runtime or successful platform traffic. Those remain separate checks.
- `live_qualification` remains `NOT_RUN`. Follow the [deployment handoff](deployment-handoff.md) with the supervisor stopped before any XHS canary.
