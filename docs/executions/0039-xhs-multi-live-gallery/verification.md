**English** | [中文](verification.zh.md)

# Execution 0039 verification

- Status: Static gates pass on the authoring workstation; complete-suite execution is deferred to the Linux deployment host per operator direction
- Date: 2026-09-03
- Predecessor: Execution 0038 closeout `064bdb1d4ab493ec2b31afb96a29032a8b939b2d`

## Environment

Windows 10 workstation, Git Bash, uv 0.12.9, Python 3.13.15. The operator moved product verification to a Linux Docker host; this record separates what actually ran here from what must run there.

## Implemented evidence

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Capture matrix | `uv run pytest -q tests/unit/test_xhs_live_capture.py` | 0 | `9 passed in 3.63s` |
| 0038 live regression (ingestion) | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py -k "xhs_live"` | 0 | `8 passed` (pre-0039 subset) |
| 0038 live regression (refresh) | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py -k "xhs_live"` | 0 | `3 passed` |
| 0038 live regression (integration) | `uv run pytest -q tests/integration/test_xhs_playable_video_pipeline.py::test_xhs_live_photo_reaches_emby_with_zero_work_replay` | 0 | `1 passed` after enabling Windows long paths (`LongPathsEnabled=1`); the staging paths exceed 260 characters without it |
| New-test collection | `uv run pytest --collect-only -q tests/unit/test_api_server.py tests/unit/test_xhs_live_capture.py tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_xhs_playable_video_pipeline.py` | 0 | `385 tests collected in 2.22s` |
| Strict mypy | `uv run mypy --strict src` | 0 | `no issues found in 87 source files` |
| Ruff and format | `uv run ruff check src/ tests/ scripts/`; `uv run ruff format --check src/ tests/ scripts/` | 0 | `All checks passed!`; `178 files already formatted` |
| Compileall | `uv run python -m compileall -q src/media_sync` | 0 | OK |
| Documentation links | `uv run python scripts/check_docs.py` | 0 | `342 Markdown files checked` |

## Deferred to the Linux deployment host

| Check | Command | Result |
| --- | --- | --- |
| New multi-live contract/refresh/integration tests | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_xhs_playable_video_pipeline.py` | `NOT_RUN` on this workstation; required on Linux |
| Complete suite | `uv run pytest -q` | `NOT_RUN` on this workstation; required on Linux |
| Build and upstream locks | `uv build`; `uv run python scripts/check_upstreams.py` | `NOT_RUN` here (`/.upstream/` not cloned on this workstation) |

Live qualification rows remain `NOT_RUN` and are the scope of the deployment execution, not this one.
