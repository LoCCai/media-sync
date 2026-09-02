**English** | [中文](verification.zh.md)

# Execution 0019 verification

- Status: Frozen offline scope passes all final gates; live qualification `NOT_RUN`
- Date: 2026-09-02
- Predecessor: `4fb639a`
- Plan commit: `dc1714c`
- Implementation commit: `2edb9d763b4948c56cc182bcc5012914bcb644d1`

## Selection evidence

| Candidate | Decision | Evidence boundary |
| --- | --- | --- |
| Ordinary creator answer, exactly one static IMAGE | Delivered | Locked upstream already receives answer HTML but loses image attributes before JSONL; the verified shim captures the frozen one-image shape and successfully bounds creator execution. |
| Answer gallery | Deferred | Ordering, edit/replacement and partial-capture semantics are separate scope. |
| Article media | Deferred | The pinned default creator path disables article enumeration. |
| Zvideo playback/cover | Deferred pending fixture | Nested playable/cover shape remains unfrozen and no real redacted fixture exists. |

## Implemented offline evidence

| Scope | Result | Evidence |
| --- | --- | --- |
| Locked upstream loss boundary | `PASS` | Verifies pinned SHA, executes real `extract_text_from_html`, answer extractor/update/JSONL store, AST-binds the `content` include, answers-only dispatch, missing native cap and both child installation points. Real locked Pydantic content carries/consumes the private binding without exposing it through dump/JSON/repr. |
| Runtime shim and creator bound | `PASS` | Exact-object binding crosses `asyncio.gather` child → parent storage and remains task-isolated. Scheduled `max_items=23` produces two API requests and two callback invocations with page sizes `20 + 3`, exactly 23 callback-processed rows and one between-page pacing sleep; there is no third request or post-cap sleep. Empty, short non-terminal, repeated, malformed and cardinality-drift pages fail closed. |
| HTML and URL gate | `PASS` | Frozen attribute priority, duplicate/competing candidate rejection, multiple/playable/container-drift rejection, strict positive IDs and bounded canonical URLs are covered, including empty query/fragment delimiter rejection. |
| Durable identity and refresh | `PASS` | ARTICLE plus one `<content_id>:image:0` IMAGE, recursive private-field stripping, query-free SQLite hint, exact canonical answer authority, parent/child/current-locator revalidation and credential-free DEFAULT profile pass. Historical assetless answers remain compatible. |
| Static structural qualification | `PASS` | Zhihu IMAGE automatically enables the production gate. Qualified JPEG/PNG/WebP pass; GIF/APNG/animated WebP/AVIF fail. Normal, recovery and takeover paths preserve the flag. The gate is bounded structural/container qualification, not complete pixel decoding. |
| SQLite/archive/Emby composition | `PASS` | Exact provenance, fake detail, mock public DNS/HTTP, production byte gate, SHA-256 archive, poster/backdrop/gallery/body/NFO/source publication and query-only zero-work replay pass. Private/transient values are absent from SQLite/runtime/archive/export and WAL/SHM sidecars. |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Pre-edit focused baseline | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_asset_download_orchestration.py tests/integration/test_pipeline_runtime.py tests/unit/test_mediacrawler_refresh.py` | `PASS` — `255 passed in 48.32s` |
| First focused combined gate | `uv run pytest -q tests/unit/test_zhihu_media.py tests/contract/test_zhihu_upstream_answer_store.py tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_zhihu_answer_image_pipeline.py tests/contract/test_mediacrawler_bridge.py::test_full_history_acknowledgement_matches_audited_platforms` | `PASS` — `364 passed in 41.04s` |
| First isolated SQLite-to-Emby composition | `uv run pytest -q tests/integration/test_zhihu_answer_image_pipeline.py` | `PASS` — `1 passed` |
| Final expanded focused gate | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run pytest -q -p no:cacheprovider tests/unit/test_zhihu_media.py tests/contract/test_zhihu_upstream_answer_store.py tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_zhihu_answer_image_pipeline.py tests/integration/test_zhihu_scheduled_creator_bound.py tests/unit/test_media_downloader.py tests/integration/test_asset_download_orchestration.py tests/unit/test_media_locator.py tests/contract/test_mediacrawler_bridge.py::test_full_history_acknowledgement_matches_audited_platforms` | `PASS` — `505 passed in 48.82s` |
| Complete suite | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run pytest -q -p no:cacheprovider` | `PASS` — `1543 passed, 1 skipped in 318.39s`; skip is the Windows-inapplicable POSIX mode-bit boundary |
| Ruff | `uv run ruff check .` | `PASS` — all checks passed |
| Format | `uv run ruff format --check .` | `PASS` — `250 files already formatted` |
| Strict mypy | `uv run mypy src/media_sync` | `PASS` — no issues in 81 source files |
| Compileall | `uv run python -m compileall -q src/media_sync` | `PASS` |
| Upstream locks | `uv run python scripts/check_upstreams.py` | `PASS` — 2 locked checkouts verified |
| Build | `uv build` | `PASS` — wheel and source distribution built |
| Documentation | `uv run python scripts/check_docs.py` | `PASS` |
| Diff, retained-artifact and upstream audit | `git diff --check` plus secret-sentinel, SQLite/WAL/SHM, retained-tree and upstream-cleanliness checks | `PASS` — tracked `268`; untracked `0`; tracked runtime/upstream `0`; runtime/build files `914`; execution-0019 retained-marker hits `0`; frozen sentinel roots `2/2`; both upstream dirty-path counts `0` |
| Independent final review | `uv run pytest -q tests/unit/test_zhihu_media.py tests/contract/test_zhihu_upstream_answer_store.py tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_asset_download_orchestration.py tests/unit/test_media_downloader.py tests/integration/test_zhihu_scheduled_creator_bound.py tests/integration/test_zhihu_answer_image_pipeline.py` | `PASS` — `461 passed in 44.33s`; no P0/P1/P2 findings |

No coverage run is claimed.

## Source-bound evidence limit

The pinned-source contract and synthetic HTML prove the locked interception boundary and deterministic frozen shape without network access. There is no real redacted Zhihu answer/API fixture, so the evidence does not prove current live attributes, creator/detail API compatibility, real `zhimg.com` redirect/profile behavior or complete pixel decoding of every image. It does prove the bounded structural cases above, including rejection of the tested GIF, APNG, animated WebP and AVIF payloads.

## Git and live qualification

Implementation commit `2edb9d763b4948c56cc182bcc5012914bcb644d1` is reconciled across local `main`, `origin/main` and GitHub. The commit containing this record is the bilingual documentation closeout; its self-referential SHA is intentionally not embedded, and post-push local/tracking/GitHub reconciliation is reported in the task handoff.

| Live row | Result |
| --- | --- |
| Real Zhihu QR/Cookie login | `NOT_RUN` |
| Real creator answer pagination | `NOT_RUN` |
| Real answer detail lookup | `NOT_RUN` |
| Real `zhimg.com` bytes, redirects and DEFAULT profile | `NOT_RUN` |
| Real Emby/Jellyfin scan/display | `NOT_RUN` |

Offline mocks do not imply these live rows. Execution 0019 delivers only one ordinary answer with exactly one static IMAGE on the sixth media platform. Multiple images, articles, zvideo, complete Zhihu coverage, Tieba media and the broader seven-platform goal remain active work.
