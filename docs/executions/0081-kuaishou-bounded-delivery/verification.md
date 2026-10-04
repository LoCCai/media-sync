**English** | [中文](verification.zh.md)

# Verification: durable Kuaishou creator-work delivery (0081)

Planning baseline: the frozen plan in this folder (commit `47ea22e`). Implementation produced by the three-role workflow (backend engineer, frontend engineer, bug tester) and reviewed by the main session.

## Final results

| Gate | Result | Evidence and boundary |
| --- | --- | --- |
| Kuaishou scan-state unit tests | `PASS` | `tests/unit/test_kuaishou_creator_work.py`. Canonical `ks-work-v1:` cursor round trips, page-tail replay under `max_items` truncation, separate `no_more_echoed` / `empty_page_end` codes with server-echo precedence, `access_restricted` ≠ source end, stalled-echo blocked state, binding-mutation rejection. |
| Capture shim contract tests | `PASS` | `tests/contract/test_kuaishou_creator_capture.py`. Page-parse privacy, ambiguous-progress rejection, coverage sealing with signed-exchange replay fixtures (no offline signing), list restriction blocked without source end, detail-failure isolation, unsigned GraphQL detail contract. |
| Ingestion / migration / delivery integration | `PASS` | `tests/integration/test_kuaishou_creator_work_ingestion.py` (one-commit page/cursor/run/contents, restriction commits nothing, unproven records rejected), `test_kuaishou_creator_work_migration.py` (empty upgrade, metadata parity, guarded downgrade; `PARENT=0016_douyin_creator_work`, `HEAD=0017_kuaishou_creator_work`), `test_kuaishou_creator_work_delivery.py` (backfill → end evidence → reconcile → incremental, restricted blocking, terminal failure). |
| Head-pinned regression updates | `PASS` | `test_packaged_migrations` (wheel carries 0015/0016/0017), `test_cli`, `test_support_bundle`, `test_api_support_bundle`, `test_offline_media_pipeline`, `test_scheduled_offline_pipeline`, `test_deployment_provenance` (allowlist), `test_database.py` domain tables, `test_api_server.py` continuations. |
| Complete Python suite | `PASS` | `uv run pytest -q` exit 0 on the final tree inside the workflow's tester phase; 7261 tests collected. |
| Static gates | `PASS` | compileall, `ruff check src tests`, strict mypy (`Success: no issues found in 165+ source files`) — one fix round inside the run, green at close. |
| Web gates | `PASS` | `npm --prefix web run check` (svelte-check) exit 0, `vitest run` exit 0, `format:check` exit 0 — all executed by the workflow with `cmd /c npm` after the bare-name spawn failure was repaired. |
| Three-role process | `PASS` | Backend engineer (three implementation units with fast gates), frontend engineer (Douyin panel + reusable mapping), bug tester (independent classification of gate outputs; zero findings after routing). |
| Documentation gate | `PASS` | `scripts/check_docs.py` OK after these bilingual files. |
| Docker image / Linux gates | `NOT_RUN` | Operator-side work under the 0077 handoff; no deployment claim. |
| Real Kuaishou login, live creator canary, supervisor restart | `NOT_RUN` | No platform credential or live crawler was used. |
| Web production build (`vite build`) | `NOT_RUN` | Not executed inside this run; the deployment rebuild covers it. |

## Repair note

The first workflow run died at the tester phase on `world.run("npm", …)` — npm resolves to `npm.cmd` on Windows and a bare-name spawn fails. The amended run re-used everything the first run had written (all backend units and the frontend panel were already on disk) and re-ran only the verification/repair tail with `cmd /c npm` forms. The bare-name calls never reached a second attempt.

## Commands run

```text
uv run pytest -q                      # inside the workflow, final tree, exit 0
uv run pytest --collect-only -q       # 7261 tests collected
uv run python -m compileall -q src
uv run ruff check src tests
uv run mypy --strict src
cmd /c npm --prefix web run check | test | format:check
uv run python scripts/check_docs.py
git diff --check
```

## Design notes for reviewers

- **Why two source-end codes.** Upstream terminates either on a server-echoed `no_more` or on its own empty-page override (client.py:434, 436, 440-442). Merging them would hide which path closed the feed; keeping them separate preserves the stronger, server-attested evidence for reconciliation while still accepting the client-inferred end as upstream-terminal.
- **Why page-tail replay exists at all.** Kuaishou's list endpoint takes no count parameter, so the durable layer cannot clamp a unit to a known page size the way Douyin's 18-per-page contract does. Truncating a server page and advancing on its echo would permanently skip the tail; the contract therefore re-issues the identical request until the page is consumed.
- **Why the stalled-echo guard.** Upstream never compares the echoed `pcursor` with the requested one; a server that keeps re-echoing a non-empty page would spin the history lane forever. The durable layer counts such stalled units and blocks with `kuaishou_cursor_stalled` after a bounded number.
