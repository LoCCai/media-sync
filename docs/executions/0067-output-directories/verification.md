**English** | [中文](verification.zh.md)

# Verification

## Final current-source verification

- `.venv/Scripts/python.exe docs/executions/0067-output-directories/artifacts/verify_output_directories.py`:831 passed,2 skipped,1 warning in380.37seconds. The script defines the exact affected selection across policy/migration/CAS, real independent-worker output, all API files, auth, CLI, library/publication/support-bundle/Job diagnostics. The two skipped real PostgreSQL race cases lack MEDIA_SYNC_TEST_POSTGRESQL_URL; they are NOT_RUN. Warning: existing Starlette/httpx deprecation.
- `pnpm test`:23files,717passed in1.47seconds, including12 output-controller cases for CAS, preview invalidation, concurrency/late responses, preserved drafts, no replay and safe errors. This is not a live-browser form acceptance run.
- `pnpm check`:0errors/0warnings; build passed in7.87seconds; format check passed.
- Ruff check/format360files, mypy139source files, compileall, both locked upstreams, uv lock and diff checks passed. Documentation links are rechecked before commit; earlier check covered682Markdown files.
- `uv build` and0066 check_package_sources.py confirm both packages contain the new service/0012 migration and154application Python files byte-equal to source. RECORD/dependencies/entrypoints/members passed. Build under system Temp/media-sync-0067-build-d16e477767bf4b76887225424ed70450. Only docs changed afterwards: source qualification remains valid, but packages are not the final documentation snapshot. No installation/deployment.

## Failed initial runs and corrections

- Review reproduced allowed OS roots and wrong binding after old-scope/new-environment drift. After fixes, four system paths were rejected; mismatch returned migration_required with zero policy/binding rows, and restoring the old root succeeded without changing files.
- Nine old API-library test constructors lacked exporter_factory; only test seams changed, real new factory tests stayed intact. Initial four-file run:9failed/121passed; the nine reran green and all passed in the final combined selection.
- Four initial runtime/CLI failures were old head/table expectations; updated to0012/21tables. One new API/independent-worker assertion mistakenly expected html instead of the existing body.txt contract. Corrected assertions verify actual file bytes/NFO. The158-case focused run overlaps the final831; do not sum.
- Initial root API lint found four long test lines, formatting in two files and two mypy Literal-key dictionary mismatches. Formatting and explicit str mapping fixed these; final static checks pass.
- Storage56passed/2PGskips, library/server53passed, head/support82passed and rootAPI42passed are overlapping focused runs. The historical full six-thousand-plus project suite was not rerun.

## Read-only production inspection

Accounts and WB operation details were inspected following computer-use guidance; see[progress](progress.md). No new login/preflight/download/tick/deployment/credential actions. Four QR platforms still fail and exact historical failed actions were not archived. Current Linux container, PostgreSQL races and live capture/download/playback remain NOT_RUN; offline success or refined codes are not login success.

## Git

Frozen plan10742c9. A fresh pre-publication fetch confirmed origin/main still5948b91 without concurrent remote changes. Implementation/closeout use bilingual commits and normal push; exact publication commit belongs in the following closeout record, not a fabricated self-reference.

At freeze: clean local/remote `5948b91` verified. Implementation tests NOT_RUN. No production operation, credentials, directory move or deletion.
