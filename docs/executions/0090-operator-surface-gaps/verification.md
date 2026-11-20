**English** | [中文](verification.zh.md)

# Verification: surface the operator-visible gaps 0088 left behind

## Final result

| Gate | Result | Evidence and boundary |
| --- | --- | --- |
| API delay surface | `PASS` | `tests/unit/test_api_server.py::test_contract_surface_stays_bounded` asserts all seven `*_scan_continuation_delay_seconds` fields on `/api/v1/settings`. Before this change the endpoint reported four; a Weibo/Tieba/Zhihu pacing mismatch was invisible. |
| Deep readiness parity | `PASS` | `doctor --deep` `continuations` now reports `weibo_delay_seconds`, `tieba_delay_seconds` and `zhihu_delay_seconds` beside the four existing keys, asserted by `tests/unit/test_api_server.py` (the deep-readiness contract test enumerated all seven). |
| Console type parity | `PASS` | `web/src/lib/types/api.ts` declares all seven delays, so the console cannot render a subset silently; `svelte-check` reports 0 errors. |
| Dashboard window labelling | `PASS` | The KPI cards now say which window each count comes from (`最近 N 条任务中的…`, `最近 N 个资产中的…`) and mark the two genuinely complete arrays as 全量; `svelte-check` and the route-wiring test pass. |
| Jobs result label | `PASS` | `operationResultLabel` derives a closed label from the whitelisted projection only; `web/src/lib/utils/operations.test.ts` adds three cases (asset-download verified/exported/empty, export re-export vs fresh, login auth status). |
| Web gate set | `PASS` | `svelte-check` → `0 errors and 0 warnings`; `vitest` → `30 files / 849 tests` (846 before, +3); Prettier → clean; build → succeeds. |
| Python gates | `PASS` | `ruff check src tests` → `All checks passed!`; `ruff format --check` → `466 files already formatted`; `mypy --strict src` → `Success: no issues found in 182 source files`. |
| Documentation | `PASS` | `scripts/check_docs.py` → links OK (886 Markdown files). |
| Deployment / live rows | `NOT_RUN` | No deployment, login, platform request or CDN byte fetch. |

## What changed

1. `src/media_sync/interfaces/api.py` — `/api/v1/settings` reports all seven delays.
2. `src/media_sync/interfaces/cli.py` — `doctor --deep` `continuations` reports all
   seven keys.
3. `web/src/lib/types/api.ts` — `Settings` declares all seven delays.
4. `web/src/routes/+page.svelte` — KPI labels name their window; the two complete
   arrays are marked 全量.
5. `web/src/lib/utils/operations.ts` + `web/src/routes/jobs/+page.svelte` — a
   qualitative `operationResultLabel` replaces the constant
   "已有白名单摘要" for non-scheduler rows.

No platform behaviour, cursor, stop reason, migration or pinned upstream file was
touched.

## Boundary note

The dashboard still derives its numbers from bounded arrays. Adding true
aggregate endpoints is a new API surface and would need its own execution; this
change makes the existing evidence honest rather than claiming more than it has.
