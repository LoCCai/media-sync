**English** | [中文](verification.zh.md)

# Verification

Implementation revision: `47ca107`. Planning baseline: `295fa2c`.

## Final results

| Gate | Result | Evidence and boundary |
| --- | --- | --- |
| XHS cursor/capture/ingestion/delivery focus | `PASS` | Initial XHS-focused selection passed `47`; API workbench/exact-delivery baseline passed `42`, then `49` after fixed failure-state coverage; delay/progress passed `26`; capture/delivery/media passed `14`; all changed Python test files passed `462 passed, 2 skipped, 1 warning in 322.43s`; legacy runner compatibility follow-up passed `45`. These selections overlap and are not summed. |
| Corrected Bilibili and generic pipeline regressions | `PASS` | The final Bilibili continuation file passed `106`; the real output-directory worker case passed `1` with one existing warning. |
| Complete Python suite | `PASS` | `7128 passed, 42 skipped, 1 warning in 1657.69s (0:27:37)`. The skips are the documented Windows/POSIX and unconfigured real-PostgreSQL qualifications; the warning is the existing Starlette/httpx deprecation. |
| Complete media-sync Web suite | `PASS` | `27 files / 820 tests` passed. |
| Svelte and production Web build | `PASS` | `svelte-check` reported 0 errors and 0 warnings. Vite transformed 4,087 server and 4,096 client modules and wrote the static build. |
| Frontend formatting | `PASS` | Repository Web Prettier check passed. |
| Python lint/format/type/compile | `PASS` | Ruff lint passed; Ruff format reported 417 files formatted after two mechanical corrections; strict mypy passed 160 source files; compileall passed `src`, `tests` and `scripts`. |
| Locked dependencies and upstreams | `PASS` | `uv lock --check` resolved 62 packages unchanged; `scripts/check_upstreams.py` verified both locked checkouts. MediaCrawler remains pinned at `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`. |
| Python packaging | `PASS` | A fresh 797,475-byte wheel (185 members) and 3,184,476-byte sdist (1,309 members) built successfully. Both contain migration `0015` and the XHS capture, note and delivery-progress modules; neither contains a database, QA/screenshot path or real `.env` file. The committed `.env.example` remains intentionally present in the sdist. |
| Documentation links/whitespace | `PASS` | `scripts/check_docs.py` checked 764 Markdown files successfully; final `git diff --check` passed. |
| Docker/Linux, PostgreSQL and live services | `NOT_RUN` | No Linux image/container, real PostgreSQL instance, live XHS login/API/CDN, host archive/library/NFO, process restart, supervisor or media server was used. |

## Corrected findings

1. An early complete-suite attempt exposed a legacy structural runner fixture that did not define `xhs_scan`; optional attribute access fixed the compatibility boundary, followed by `45 passed`.
2. A later complete run reached `7104 passed, 42 skipped, 23 failed, 1 warning in 1616.63s`. Twenty-two failures shared one stale Bilibili test manifest that lacked the newly persisted creator fingerprint; the remaining output-directory failure came from unconditionally parsing MediaCrawler policy for a non-MediaCrawler adapter. Production parsing was narrowed to the correct adapter and the provenance fixture gained its exact field plus tamper coverage.
3. Focused reruns passed (`106` and `1`) before the final complete-suite gate. No failed run is represented as a pass.
4. Review also corrected exact API success reporting, zero-delay pacing semantics and child-side partial normalization before the complete run.

## Commands run

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_bili_scan_continuation.py -q
.\.venv\Scripts\python.exe -m pytest tests/integration/test_pipeline_output_directories.py::test_api_save_is_seen_by_existing_and_independent_workers_and_library_inspection -q

pnpm --dir web run format:check
pnpm --dir web test
pnpm --dir web run check
pnpm --dir web run build

.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m ruff format --check src tests scripts
.\.venv\Scripts\python.exe -m mypy --strict src/media_sync
.\.venv\Scripts\python.exe -m compileall -q src tests scripts
uv lock --check
.\.venv\Scripts\python.exe scripts/check_upstreams.py
.\.venv\Scripts\python.exe scripts/check_docs.py
git diff --check
uv build --out-dir <temporary-directory>
```

## Qualification conclusion

The local XHS creator-note path is qualified for page-tail preservation, opaque cursor replay, fresh-token detail gating, distinct blocked/partial states, exact Run-content delivery, source-end reconciliation, incremental zero-work replay and closed public projection. This remains deterministic offline evidence. Source-end evidence is time-bound observation, not permanent historical completeness, and no live or deployment row is inherited from older releases.
