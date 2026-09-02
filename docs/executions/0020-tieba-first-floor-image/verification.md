**English** | [中文](verification.zh.md)

# Execution 0020 verification

- Status: Frozen offline scope passes all final gates; authenticated/live qualification `NOT_RUN`
- Date: 2026-09-02
- Predecessor: `431fd855dafce502e83f74a055a4b27ae5c6f40b`
- Plan commit: `df7a38a6f9beee35c6c19336260b512ebc87ce0d`
- Implementation commit: `8a0e935624e944809af1a56b0f02186686433d95`

## Selection evidence

| Candidate | Evidence boundary | Decision |
| --- | --- | --- |
| Ordinary creator thread, exactly one first-floor static IMAGE | Locked `page_pc` passes full `first_floor.content` to the extractor, current public responses expose one integer type-3 item with `origin_src`, and the present text extractor discards it before JSONL. | Delivered |
| First-floor gallery | Real audited rows include multiple type-3 items, but ordering/replacement/partial-refresh semantics are a separate scope. | Deferred |
| Video/voice/emoji/link/rich card | Other integer content types exist in current responses; their exact schemas and Emby semantics are not frozen. | Deferred |
| Replies/comments media | This execution intercepts only `first_floor` note detail and note JSONL storage. | Deferred |

## Read-only current-response evidence

The following evidence was produced transiently on 2026-09-02 and is summarized without response bodies, personal data, signed query values or saved fixtures. It is useful for freezing the current contract but is not a reproducible offline test and does not qualify authenticated flows or future platform behavior.

| Check | Result |
| --- | --- |
| Signed anonymous `/c/s/pc/sync` | `PASS` — HTTP 200, `error_code=0`, public TBS returned transiently |
| Bounded `page_pc` sample scan | `PASS` — 18 candidate IDs requested; real zero-, one- and two-image rows observed; no body retained |
| One-image item keys | `PASS` — `type=3`; `origin_src`, `cdn_src`, `big_cdn_src`, `cdn_src_active`, `pic_id`, `bsize`, `origin_size`, `is_long_pic`, `show_original_btn` observed |
| Origin authority | `PASS` — HTTPS exact `tiebapic.baidu.com`, `/forum/pic/item/<40-hex>.jpg`, one `tbpicau` query key |
| Signed DEFAULT-profile byte check | `PASS for observed request only |
| Query-free comparison | `PASS as risk evidence |

## Implemented offline evidence

| Scope | Result | Evidence |
| --- | --- | --- |
| Locked loss boundary | `PASS` | The exact locked SHA is verified; real extractor/model/update/JSONL objects execute and prove that the unshimmed row loses type-3 locators. The real model carries then consumes the private object binding without dump/JSON/repr exposure; `.upstream` remains clean. |
| Current type-3 gate | `PASS` | The frozen gate accepts only a bounded text-plus-exactly-one-image list, exact ten-key integer type-3 structure, strict scalar bounds and signed `origin_src`; zero/multiple/other/drift shapes do not qualify an Asset. |
| Exact-object capture | `PASS` | Verified module origin, full/idempotent installation, partial/marker/field collision rejection, exact-object matching, gather-child → parent-store carry, nested-store-only `ContextVar` and concurrent isolation pass. |
| Scheduled creator cap | `PASS` | `max_items=23` produces detail and callback batches `20 + 3`, exactly 23 successful rows, one between-page sleep, no third request and no post-cap sleep. Empty/short non-terminal, repeated, malformed and identity/cardinality-drift pages fail closed. |
| Normalization and durable identity | `PASS` | ARTICLE gains exactly one position-zero `<note_id>:image:0` IMAGE; private fields are recursively stripped and SQLite/raw/archive/export retain only the query-free scheme/authority/path identity. Legacy zero-image ARTICLE rows remain compatible. |
| Exact detail refresh | `PASS` | SQLite canonical thread URL is the only detail authority. Refresh context, parent request and child loader revalidate its identity; upstream receives `TIEBA_SPECIFIED_ID_LIST=[<note_id>]`; one exact ARTICLE/IMAGE/hint match returns the newly validated signed locator under credential-free DEFAULT profile. |
| Static byte gate | `PASS` | Tieba IMAGE automatically enables the production bounded structural gate. Qualified JPEG/PNG/WebP pass; GIF/APNG/animated WebP/AVIF fail; normal, recovery and takeover preparation preserve `require_static_image=True`. This is not complete pixel decoding. |
| SQLite/archive/Emby composition | `PASS` | Exact provenance, fake detail, mock public DNS/HTTP, DEFAULT profile without Cookie/Authorization/Referer/Origin, production byte gate, SHA-256 archive and poster/backdrop/gallery/body/NFO/source publication pass. Query-only replay adds no detail/DNS/HTTP/archive/export work; SQLite/WAL/SHM/runtime/archive/export retain neither the private field nor transient `tbpicau`. |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Pre-edit focused baseline | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_asset_download_orchestration.py tests/integration/test_pipeline_runtime.py tests/unit/test_mediacrawler_refresh.py` | `PASS — 307 passed in 36.66s` |
| Upstream locks | `uv run python scripts/check_upstreams.py` | `PASS — Upstreams OK (2 locked checkouts verified)` |
| Upstream worktrees | `git -C .upstream/MediaCrawler status --short --branch` and bili-sync-up equivalent | `PASS — both clean on main...origin/main |
| Locked Tieba source contract | `uv run pytest -q tests/contract/test_tieba_upstream_first_floor_media.py` | `PASS — 6 passed in 3.34s` |
| Isolated SQLite-to-Emby composition | `uv run pytest -q tests/integration/test_tieba_first_floor_image_pipeline.py` | `PASS — 1 passed in 1.23s` |
| Focused implementation regression | `uv run pytest -q tests/unit/test_tieba_media.py tests/contract/test_tieba_upstream_first_floor_media.py tests/integration/test_tieba_first_floor_image_pipeline.py tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_asset_download_orchestration.py` | `PASS — 368 passed in 41.18s` |
| Complete suite | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run pytest -q -p no:cacheprovider` | `PASS — 1650 passed, 1 skipped in 310.82s`; skip is the Windows-inapplicable POSIX mode-bit boundary |
| Ruff | `uv run ruff check .` | `PASS — all checks passed |
| Format | `uv run ruff format --check .` | `PASS — 258 files already formatted` |
| Strict mypy | `uv run mypy src/media_sync` | `PASS — no issues in 82 source files |
| Compileall | `uv run python -m compileall -q src/media_sync` | `PASS` |
| Build | `uv build` | `PASS — wheel and source distribution built |
| Documentation | `uv run python scripts/check_docs.py` | `PASS — 96 Markdown files checked |
| Diff/retained-artifact audit | `git diff --check` plus explicit Git, retained-tree and upstream audit | `PASS — tracked 276; untracked 0; tracked runtime/upstream 0; upstream-tracked 0; retained artifact files 3; Tieba retained-marker hits 0; both upstream dirty-path counts 0 |

No coverage run is claimed.

## Git reconciliation

Implementation commit `8a0e935624e944809af1a56b0f02186686433d95` is reconciled across local `main`, `origin/main` and GitHub. The commit containing this record is the bilingual documentation closeout; its self-referential SHA is intentionally not embedded, and post-push reconciliation is reported in the task handoff.

## Live qualification

| Row | Result |
| --- | --- |
| Real Tieba QR/Cookie login | `NOT_RUN` |
| Authenticated creator enumeration and exact detail | `NOT_RUN` |
| Future real CDN token/redirect/byte behavior | `NOT_RUN` — one transient anonymous observation is recorded separately |
| Real Emby/Jellyfin scan/display | `NOT_RUN` |

Offline mocks and the transient public observation cannot imply these rows. Execution 0020 is limited to one frozen ordinary first-floor static-image slice.
