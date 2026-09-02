**English** | [中文](verification.zh.md)

# Execution 0032 verification

- Status: Frozen offline bounded Douyin note-gallery scope passes all final gates; live qualification `NOT_RUN`
- Date: 2026-09-02
- Predecessor: Execution 0031 closeout `2e9e3b5378dd8966f56e068dced5f799e115f92b`
- Plan commit: `286dac9`

## Baseline (before any 0032 change)

| Check | Result |
| --- | --- |
| 0031 focused regression | `PASS — 302 passed in 4.04s` |
| 0031 detail contracts | `PASS — 100 passed in 70.92s` |
| 0031 complete suite | `PASS — 1956 passed, 1 skipped in 408.57s` |
| Ruff, format, strict mypy, docs, upstreams | `PASS` (recorded in the 0031 verification) |

## Implemented evidence

| Scope | Result |
| --- | --- |
| Strict gallery parser | `PASS` — the comma-joined `note_download_url` accepts only string or JSON-frozen sequence input whose every item is one valid URL without embedded commas; duplicates, non-strings, empty items, invalid URLs, wrong types and galleries above 64 quarantine as `INVALID_RECORD`; empty/absent fields stay empty |
| Materialization | `PASS` — one image yields `ContentKind.IMAGE`, 2–64 yield `ContentKind.GALLERY` with ordered `{aweme_id}:image:0..N-1` IMAGE assets; the AUDIO/COVER companions of the fixture keep their positions |
| Frozen compatibility | `PASS` — the empty-field video/audio/text fallbacks, the tolerant video/music/cover parsing and the pinned crawler's image-over-video choice stay byte-compatible; only the drifted-gallery semantics changed from silently dropping items to quarantining (one pre-existing integration fixture updated accordingly) |
| Refresh | `PASS` — each gallery position re-resolves its current signed URL through one exact numeric-ID detail run; a replaced second path closes as `locator_refresh_asset_mismatch` |
| Download and publication | `PASS` — both images download through the DEFAULT-profile request (no Cookie/Authorization/Referer/Origin), pass the static PNG sniff gate, archive under distinct SHA-256 digests and publish Emby poster/backdrop/two gallery images/NFO with zero-work replay |
| Non-retention | `PASS` — the detail signature, its sentinel and both signed URLs appear nowhere in retained runtime/work/archive/export/library trees or SQLite artifacts |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Focused implementation regression | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_douyin_playable_pipeline.py` | `PASS — 316 passed in 5.09s` |
| Douyin DB-ingestion contracts | `uv run pytest -q tests/integration/test_mediacrawler_db_ingestion.py` | `PASS — 25 passed in 2.64s` |
| Gallery closeout rerun | `uv run pytest -q tests/integration/test_douyin_playable_pipeline.py::test_douyin_note_gallery_reaches_emby_without_persisting_signed_queries` | `PASS — 1 passed in 2.25s` |
| Complete suite | `uv run pytest -q` | `PASS — 1971 passed, 1 skipped in 390.84s`; the skip is the Windows-inapplicable POSIX mode-bit boundary |
| Ruff and format | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 459 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 84 source files` |
| Compileall and build | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — compiled; wheel and source distribution built` |
| Documentation and upstream locks | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 288 Markdown files; 2 locked clean checkouts` |
| Git/upstream audit | explicit status and tracked-path scans | `PASS — intended changes only; tracked runtime/upstream/dist 0; both upstream dirty counts 0` |

## Not claimed

No coverage run is claimed. No real account, login, creator feed, Douyin API, CDN byte or Emby/Jellyfin server interaction was performed; every live row stays `NOT_RUN`.
