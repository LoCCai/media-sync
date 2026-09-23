**English** | [中文](verification.zh.md)

# Execution 0078 verification

- Status: All authoring-workstation gates pass with fresh numbers; deployment and live rows remain operator items per the 0077 handoff
- Date: 2026-09-23
- Environment: Windows 10 authoring workstation, uv + Python (project venv), Node 22.14 for Web checks, ffmpeg/ffprobe and both `.upstream` checkouts present

## Implemented evidence

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Ruff | `uv run ruff check .` | 0 | All checks passed |
| Format | `uv run ruff format --check .` | 0 | 1203 files formatted (one bridge line reflowed pre-gate) |
| Strict mypy | `uv run mypy --strict src` | 0 | No issues in 162 source files (includes the bridge and settings extension) |
| Compileall | `uv run python -m compileall -q src/media_sync` | 0 | OK |
| Documentation | `uv run python scripts/check_docs.py` | 0 | `782 Markdown files checked` (checklist, execution records, backfilled index all link-clean) |
| Upstream locks | `uv run python scripts/check_upstreams.py` | 0 | `2 locked checkouts verified` |
| Web format | `npx prettier --check .` | 0 | Clean |
| Web types | `npx svelte-check --tsconfig ./tsconfig.json` | 0 | 0 errors, 0 warnings |
| Web tests | `npx vitest run` | 0 | `30 files / 833 tests` passed (new: native-qr-relay 5, artifact-layers 3) |
| Bridge unit tests | `uv run pytest -q tests/unit/test_webui_log_bridge.py` | 0 | `5 passed` (shape/forbidden/level-clamp/never-raise + real `LogStore` round-trip) |
| Log-center regression | `uv run pytest -q tests/unit/test_cli_log_center.py` | 0 | `3 passed` |
| API regression | `uv run pytest -q tests/unit/test_api_server.py` | 0 | `21 passed, 1 warning` |
| Complete Python suite | `uv run pytest -q` | 0 | `7145 passed, 42 skipped, 108 warnings in 1570.98s` (0078 adds 8 tests to 0077's 7140; skips are the recorded OS/PostgreSQL/`uv` qualification branches) |

## Operator rows (unchanged)

Docker build/run of the exact revision, migration `0015`, API/supervisor parity, the bounded XHS canary and every live platform row remain `NOT_RUN` on this workstation — they execute on the Linux host per the 0077 handoff, now condensed into [`handoff-checklist.md`](../../handoff-checklist.md).
