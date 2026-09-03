**English** | [中文](verification.zh.md)

# Execution 0048 verification

- Status: Calibration scope passes all static gates; offline suites executed for real with honest numbers and a classified divergence list; deployment and live rows remain operator items
- Date: 2026-09-03
- Environment: Windows 10 authoring workstation, uv 0.12.9, Python 3.11.16/3.12.14/3.13.15 (uv-managed), ffmpeg/ffprobe N-126390 static build on PATH, both `.upstream` checkouts cloned at locked SHAs

## Static gates

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Ruff | `uv run ruff check src/ tests/ scripts/` | 0 | `All checks passed!` |
| Format | `uv run ruff format src/ tests/ scripts/` | 0 | `3 files reformatted, 175 left unchanged` then clean |
| Strict mypy | `uv run mypy --strict src` | 0 | No issues (87 source files, includes the 0044 endpoints and the extracted download helper) |
| Documentation | `uv run python scripts/check_docs.py` | 0 | All links resolve |
| Upstream locks | `uv run python scripts/check_upstreams.py` | 0 | `2 locked checkouts verified` |

## Python support matrix (executed, not commented)

| Version | `uv sync --all-groups --locked` | Complete suite |
| --- | --- | --- |
| 3.11.16 | OK | runs; same divergence set as 3.13 (see below) |
| 3.12.14 | OK | runs; same divergence set as 3.13 |
| 3.13.15 | OK | `33 failed, 2031 passed, 1 skipped in 481.91s` (one repeat run: 35 failed, 2031 passed, 1 skipped — 2 tests flaky across runs) |

`requires-python` stays `>=3.11,<3.14`; the earlier "3.12 rejects the lockfile" Docker comment was wrong and is replaced by the BASE_IMAGE note (the 3.12 container failure predates the mirrored/aliyun index alignment).

## Divergence classification (the 33–35 failures)

Every failing test spawns real child processes (bridge/receipt sealing, login child bounds, scheduler v3/v2 protocol, CLI ingest subprocess, security matrix child). A representative probe shows the child itself succeeding (`returncode=0`, 1270 bytes, 2 JSONL items) and failing only at output sealing (`completion_failed: "MediaCrawler child output could not be sealed safely"`). The identical failure set reproduces on a **clean checkout** of this workstation (verified via `git stash`), so it is not caused by execution 0048 changes; suspected local AV/filesystem behavior on child-output re-read. Authoritative adjudication: the Phase B Linux-host full-suite rerun (0047 plan step B-1); any reproduction there enters the defect loop as `0047-dN`.

## Defect fixed by the fresh numbers

The JSONL reader freezes inner lists to tuples; the 0039 multi-live branch accepted only `list`, so every real record quarantined (`invalid_record`). Fixed to accept `(list, tuple)`; all 28 live-gallery tests (capture matrix, contract drift matrix, per-position refresh, integration composition) now pass. Root cause recorded: those tests were committed collected-but-never-executed.

## 0044-minimal evidence

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| API tests | `uv run pytest -q tests/unit/test_api_server.py` | 0 | `5 passed` (detail endpoints, gates, 404s, background operations) |
| CLI extraction regression | `uv run pytest -q tests/integration/test_asset_download_orchestration.py` | 0 | `38 passed` |
| Live-gallery suites | `pytest -k "multi_live or xhs_live"` | 0 | `28 passed` |
| Pinned source contracts | zhihu/tieba store suites | 0 | `13 passed` (after cloning `.upstream`) |

## Secret scan (release checklist excerpt)

| Check | Result |
| --- | --- |
| `git grep -iE "set-cookie\|cookie:\|authorization:"` | Only type declarations/sentinels/redaction references; no real tokens |
| Tracked runtime artifacts (`git ls-files`) | None (`.env`/sqlite/browser_data/login-qr absent) |
| Working-diff sentinel scan | 0 matches |

## Operator rows (unchanged)

Docker build/run, container persistence, backup-restore drill, every live platform row: `NOT_RUN` on this workstation — Phase B+ on the Linux host per the restructured execution 0047.
