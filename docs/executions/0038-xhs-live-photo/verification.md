**English** | [中文](verification.zh.md)

# Execution 0038 verification

- Status: Frozen offline XHS live-photo scope passes all final gates; live qualification `NOT_RUN`
- Date: 2026-09-03
- Predecessor: Execution 0037 closeout `b9c88c4afab6ba2d9d2a43efea63f63cd6cd31ca`
- Plan commit: `650c256`

## Baseline (before any 0038 change)

| Check | Result |
| --- | --- |
| 0037 focused regression | `PASS — 344 passed in 6.32s` |
| 0037 complete suite | `PASS — 2020 passed, 1 skipped in 370.56s` |
| Ruff, format, strict mypy, docs, upstreams | `PASS` (recorded in the 0037 verification) |

## Implemented evidence

| Scope | Result |
| --- | --- |
| Store-boundary capture | `PASS` — the new shim captures exactly the frozen `image_list[0].live_photo.stream.h264[0].master_url` for a one-image `type="normal"` note in both children; malformed nesting, foreign hosts, above-one images and wrong types capture nothing |
| Normalizer branch | `PASS` — MIXED content with one `{note_id}:image:0` IMAGE plus one `{note_id}:video:0` VIDEO and an empty `video_url` scalar; payload and shape drift quarantine; the private field is recursively stripped |
| Refresh binding | `PASS` — the creator-fallback `normal`-type branch accepts the exact unambiguous one-image-plus-one-video shape and revalidates the live URL; path drift closes as `locator_refresh_asset_mismatch`; ordinary `normal`/`video` notes stay byte-compatible |
| Download and publication | `PASS` — both assets download through the DEFAULT profile (static PNG gate and MP4 probe), archive under distinct SHA-256 digests and publish the Emby episode with poster, zero-work replay |
| Non-retention | `PASS` — the live sentinel and signed URL appear nowhere in retained runtime/work/archive/export/library trees or SQLite artifacts |
| Fixture compat | `PASS` — the shared fake-project base and the XHS fake checkout gained the minimal store modules the new shim requires; the security matrix, saved-session and supervision suites stay green |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Focused implementation regression | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_xhs_playable_video_pipeline.py tests/integration/test_xhs_creator_authority_pipeline.py` | `PASS — 355 passed in 6.92s` |
| Detail-refresh contract suite | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py` | `PASS — 116 passed in 80.18s` |
| Live closeout rerun | `uv run pytest -q tests/integration/test_xhs_playable_video_pipeline.py::test_xhs_live_photo_reaches_emby_with_zero_work_replay` | `PASS — 1 passed in 2.14s` |
| Complete suite | `uv run pytest -q` | `PASS — 2032 passed, 1 skipped in 371.84s`; the skip is the Windows-inapplicable POSIX mode-bit boundary |
| Ruff and format | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 509 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 86 source files` |
| Compileall and build | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — compiled; wheel and source distribution built` |
| Documentation and upstream locks | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 336 Markdown files; 2 locked clean checkouts` |
| Git/upstream audit | explicit status and tracked-path scans | `PASS — intended changes plus one new module; tracked runtime/upstream/dist 0; both upstream dirty counts 0` |

## Not claimed

No coverage run is claimed. No real account, login, creator feed, XHS API, CDN byte or Emby/Jellyfin server interaction was performed; every live row stays `NOT_RUN`. The frozen `live_photo` shape is a documented store-input contract, not a live-verified one.
