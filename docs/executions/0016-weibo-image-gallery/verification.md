**English** | [中文](verification.zh.md)

# Execution 0016 verification

- Status: Offline implementation and closeout gates pass; live qualification remains `NOT_RUN`
- Environment: Windows, local workspace, Python environment resolved by `uv`
- Evidence date: 2026-08-31
- Plan commit: `b7bb818`
- Implementation commit: `a77ca74`

## Starting baseline

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Existing ingestion, detail, refresh/runtime, downloader/network, Emby application/layout and Bilibili/Kuaishou/Douyin compositions | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py tests/integration/test_emby_application.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_kuaishou_playable_pipeline.py tests/integration/test_douyin_playable_pipeline.py` | `0` | `PASS` — `272 passed in 46.92s` |

The baseline proved predecessor platform-neutral image primitives and the three existing video-platform compositions. It did not prove Weibo media capture, Asset discovery, detail refresh, transfer or Emby image publication.

## Implementation evidence

| Scope | Status | Evidence |
| --- | --- | --- |
| Creator child shim | `PASS` | A real isolated fake child imports a verified checkout, installs the shim, runs concurrent note tasks and proves task-local ordered capture plus fail-closed duplicate/retweet/page-info/drift behavior. |
| Detail child shim | `PASS` | `MediaCrawlerDetailProcessRunner` crosses the child boundary with `platform=wb`, exact plain numeric `WEIBO_SPECIFIED_ID_LIST`, JSONL/media-off/concurrency configuration, bounded framing, stable profile and successful attempt cleanup. |
| Closed source shape | `PASS` | Only canonical numeric original posts, no media `page_info`, unique ordered PIDs, `sinaimg.cn` or subdomain authority, and `jpg/jpeg/png/webp` extensions emit Assets. Foreign hosts, video/GIF/unknown extensions and malformed shapes fail closed. |
| IMAGE/GALLERY normalization | `PASS` | One image becomes `IMAGE`; multiple images become `GALLERY`; Asset kind, position, remote ID, MIME and source-hint order are deterministic. |
| SQLite identity/provenance | `PASS` | Two ordered IMAGE Assets persist stable adapter-refresh locators and exact current Account/Subscription-bound `AssetRefreshSource` observations; replay does not create duplicate identities. |
| Exact WB detail identity | `PASS` | Request construction, resolved reference and child load all require `detail_reference == content_remote_id` as the same canonical plain numeric ID. Refresh matches content, remote ID, kind, position and query-free source hint; reorder/duplicate drift fails closed. |
| Two-image transfer/archive | `PASS` | The composition E2E performs two detail refreshes, two public-DNS/default-profile HTTP requests, receives two distinct synthetic PNG payloads and publishes two independent SHA-256 archives. No Cookie, Authorization, Referer or Origin is sent. |
| Emby layout | `PASS` | First image is poster, second is backdrop, both appear as ordered gallery 001/002 files, NFO references poster/backdrop, and source metadata records both ordered IDs/checksums without raw locators or source URLs. |
| Private/transient boundary | `PASS` | The private field, two PID sentinels and a nested signed-URL sentinel are absent from normalized raw, SQLite and sidecars, runtime/work roots, both archives, export staging and library output. |
| Zero-work replay | `PASS` | Replay adds no detail runner, HTTP, DNS, probe, archive or export work and leaves archive/library trees byte-identical. |

## Independent review and repair

| Finding | Resolution |
| --- | --- |
| The proxy transformation accepted an arbitrary embedded source host. | Restricted both raw transformation and normalized proxy validation to `sinaimg.cn` and its subdomains; added foreign-host fail-closed regressions. |
| IMAGE accepted video, GIF or unknown suffixes. | Added a case-insensitive `jpg/jpeg/png/webp` allowlist; excluded animation and non-static formats. |
| Different canonical numeric WB detail IDs passed initial validation. | Required exact same plain numeric ID at request construction, resolved-reference and child-load boundaries; added mismatch regressions. |
| The first composition test used only one image while claiming Gallery output. | Replaced it with a two-image Gallery E2E proving two refreshes, transfers, archives and ordered Emby gallery files. |

## Quality gates

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Combined focused gate across 15 files | `uv run pytest -q tests/contract/test_mediacrawler_bridge.py tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py tests/integration/test_emby_application.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_kuaishou_playable_pipeline.py tests/integration/test_douyin_playable_pipeline.py tests/integration/test_weibo_image_pipeline.py` | `0` | `PASS` — `388 passed in 125.73s` |
| Complete test suite | `uv run pytest -q` | `0` | `PASS` — `1251 passed, 1 skipped in 359.38s`; skip: Windows-inapplicable POSIX mode-bit test / 跳过：Windows 不适用的 POSIX mode-bit 测试 |
| Ruff lint | `uv run ruff check .` | `0` | `PASS` |
| Ruff format | `uv run ruff format --check .` | `0` | `PASS` — 228 files already formatted |
| Strict typing | `uv run mypy src/media_sync` | `0` | `PASS` — success for 78 source files |
| Pinned upstream verification | `uv run python scripts/check_upstreams.py` | `0` | `PASS` — 2 upstream entries verified |
| Build | `uv build` | `0` | `PASS` — wheel and source distribution produced |
| Diff checks | `git diff --check` and `git diff --cached --check` | `0` | `PASS` |
| Documentation after final truth edits | `uv run python scripts/check_docs.py` | `0` | `PASS` — 80 Markdown files checked |

No coverage run is claimed. The focused and complete results above are implementation-commit evidence. Git push and final local/tracking/GitHub SHA reconciliation occur after this documentation commit exists, so their authoritative result is reported in the task handoff rather than self-referentially embedded here.

## Retained and Git inventory

The read-only closeout audit enumerated Git tracked and standard-untracked paths plus every real file below ignored `.media-sync` and `dist`. It allowed the tracked `.env.example` template but rejected runtime, upstream, build, browser-profile, real environment and SQLite paths. It byte-scanned retained `.media-sync` files for the split execution-private field/PID/signature markers without printing matched data and verified that the frozen execution 0007/0008 sentinel roots still exist.

| Audit | Exit | Result |
| --- | ---: | --- |
| Final tracked/untracked/runtime inventory and execution-0016 retained-marker scan | `0` | `tracked=246`; `untracked=0`; `tracked_forbidden=0`; `suspicious_untracked=0`; `runtime_and_build_files=914`; `runtime_execution0016_marker_hits=0`; `sentinel_roots_preserved=2/2` |

## Live qualification

| Item | Status |
| --- | --- |
| Real QR/Cookie/saved-session login | `NOT_RUN` |
| Real creator scan and incremental rerun | `NOT_RUN` |
| Real detail and image-proxy/CDN transfer | `NOT_RUN` |
| Real platform bytes through production probe dependencies | `NOT_RUN` |
| Real Emby/Jellyfin server scan and viewing | `NOT_RUN` |

These `NOT_RUN` rows are not failures and are not implied by offline mocks. They remain explicit operator-assisted qualification work, as do Weibo video/animation/long-image semantics, bounded creator pagination, a Sina-direct profile, same-ID replacement detection, cleanup-failure quarantine and the remaining cross-platform objective.
