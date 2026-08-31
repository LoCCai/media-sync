# Execution 0015 verification / 执行 0015 验证

- Status / 状态：Offline implementation and closeout gates pass; live qualification remains `NOT_RUN` / 离线实现与收尾门禁通过；真人验收仍为 `NOT_RUN`
- Environment / 环境：Windows, local workspace, Python environment resolved by `uv` / Windows、本地工作区、由 `uv` 解析 Python 环境
- Evidence date / 证据日期：2026-08-31
- Plan commit / 计划提交：`76b1973`
- Implementation commit / 实现提交：`95d314d`

## Starting baseline / 起始基线

| Check / 检查 | Command / 命令 | Exit / 退出码 | Result / 结果 |
| --- | --- | ---: | --- |
| Existing ingestion, detail, refresh/runtime, downloader/network, Emby application/layout and Bilibili/Kuaishou playable compositions / 既有导入、detail、refresh/runtime、下载器/网络、Emby application/layout 及 Bilibili/快手可播放组合 | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py tests/integration/test_emby_application.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_kuaishou_playable_pipeline.py` | `0` | `PASS` — `269 passed in 34.05s` |

This baseline proves predecessor Douyin unit refresh/process cases and both existing playable-platform pipelines. It does not prove Douyin durable raw closure, exact composed runtime, video+cover transfer, Emby primary-media layout or platform replay. / 该基线证明既有抖音单元 refresh/process case 与两个现有可播放平台 pipeline；不证明抖音持久 raw 封闭、精确组合 runtime、视频+封面传输、Emby 主媒体 layout 或平台重放。

## Focused implementation evidence / 实现专项证据

| Scope / 范围 | Command / 命令 | Exit / 退出码 | Result / 结果 |
| --- | --- | ---: | --- |
| Douyin discovery/raw, pinned detail process, exact Account/Subscription refresh, video+cover download/probe/archive, Emby publication, replay and Kuaishou regression / 抖音发现/raw、锁定 detail 进程、精确 Account/Subscription 刷新、视频+封面下载/探测/归档、Emby 发布、重放及快手回归 | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_douyin_playable_pipeline.py tests/integration/test_kuaishou_playable_pipeline.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py` | `0` | `PASS` — `231 passed in 41.79s` |

The focused gate proves exact video/cover remote IDs, positions, MIME/source hints and provenance; query/userinfo/fragment/nested sentinels absent from normalized raw, ORM and disposed SQLite/sidecars across all four Douyin media fields; comma-list normalization into an ordered flat sequence; and accepted transient Asset URLs preserved in memory. A real fake checkout goes through `MediaCrawlerDetailProcessRunner` for the pure-ID process contract. The composed E2E separately uses a fake detail runner, mock public DNS/HTTP, synthetic MP4/PNG bytes and a controlled video probe; it does not use a real account, Douyin endpoint, CDN, FFmpeg process or media server. / 专项门禁证明精确视频/封面 remote ID、position、MIME/source hint 与来源；四个抖音媒体字段中的 query/userinfo/fragment/嵌套哨兵不会进入归一化 raw、ORM 及 dispose 后 SQLite/sidecar；逗号列表会归一化成有序平面序列；被接受的瞬态 Asset URL 在内存中保留。纯 ID 进程契约的真实 fake checkout 会经过 `MediaCrawlerDetailProcessRunner`；组合 E2E 则另行使用 fake detail runner、mock 公网 DNS/HTTP、合成 MP4/PNG 字节与受控视频 probe，不使用真人账户、抖音端点、CDN、FFmpeg 进程或媒体服务器。

Exact lazy runtime binding covers Account, Subscription and `AssetRefreshSource`; existing negative cases close missing, drifted, duplicate and wrong-source selections before transfer. Media HTTP uses `MediaRequestProfile.DEFAULT` without Cookie, Authorization, Referer, Origin or caller-controlled headers. Video receives mandatory controlled probing; video and cover receive SHA-256 archive identities and local Emby `.mp4`/poster/NFO/source output. Query-only replay preserves generation and re-reads live counters to prove no second fake detail runner, detail call, HTTP request, DNS resolution or probe. / 精确惰性 runtime 绑定覆盖 Account、Subscription 与 `AssetRefreshSource`；既有负例会在传输前关闭缺失、漂移、重复及错误来源选择。媒体 HTTP 使用 `MediaRequestProfile.DEFAULT`，不含 Cookie、Authorization、Referer、Origin 或调用方自定义 header。视频执行强制受控 probe；视频与封面均获得 SHA-256 归档身份及本地 Emby `.mp4`/海报/NFO/source 输出。仅 query 变化的重放会保留 generation，并重新读取实时计数，证明不会再次调用 fake detail runner、detail、HTTP、DNS 或 probe。

## Complete root closeout gates / 根任务完整收尾门禁

| Check / 检查 | Command / 命令 | Exit / 退出码 | Result / 结果 |
| --- | --- | ---: | --- |
| First complete offline suite / 首轮完整离线套件 | `uv run pytest -q` | `1` | `FAIL` — `1208 passed, 1 skipped, 1 failed in 365.17s`; exposed the account-lock readiness race described below / `1208` 项通过、`1` 项跳过、`1` 项失败，耗时 `365.17s`；暴露下述账户锁 readiness 竞态 |
| Final complete offline suite / 最终完整离线套件 | `uv run pytest -q` | `0` | `PASS` — `1209 passed, 1 skipped in 438.39s` |
| Lint / 静态检查 | `uv run ruff check .` | `0` | `PASS` — `All checks passed!` |
| Format / 格式 | `uv run ruff format --check .` | `0` | `PASS` — `222 files already formatted` |
| Strict typing / 严格类型 | `uv run mypy src/media_sync` | `0` | `PASS` — `Success: no issues found in 77 source files` |
| Documentation links / 文档链接 | `uv run python scripts/check_docs.py` | `0` | `PASS` — `Documentation links OK (76 Markdown files checked)` |
| Pinned upstreams / 锁定上游 | `uv run python scripts/check_upstreams.py` | `0` | `PASS` — `Upstreams OK (2 locked checkouts verified)` |
| Source distribution and wheel / 源码包与 wheel | `uv build` | `0` | `PASS` — built `dist\media_sync-0.1.0.tar.gz` and `dist\media_sync-0.1.0-py3-none-any.whl` |
| Patch whitespace / 补丁空白 | `git diff --check` and `git diff --cached --check` / `git diff --check` 与 `git diff --cached --check` | `0` | `PASS` — no output / 无输出 |

### First-run failure and repair / 首轮失败与修复

The first full run failed `tests/contract/test_mediacrawler_bridge.py::test_account_profile_lock_serializes_same_account`. Its former readiness signal polled for generated JSONL, which did not establish that the first runner had already acquired the per-account lock on a cold Windows start. The contract now monkeypatches the same runner and waits on a `threading.Event` reached inside the lock-owned `_run_locked` path before starting the competing call. This makes lock ownership, not file timing, the readiness authority. / 首轮完整套件失败于 `tests/contract/test_mediacrawler_bridge.py::test_account_profile_lock_serializes_same_account`。原 readiness 信号通过轮询已生成 JSONL 判断，在 Windows 冷启动下不能证明第一个 runner 已经取得逐账户锁。契约现在 monkeypatch 同一个 runner，并在启动竞争调用前等待持锁 `_run_locked` 路径内部触发的 `threading.Event`；readiness 权威因此变成锁所有权，而不是文件时序。

Windows cold process startup and real-time scanning could also consume the former four-second wall-clock budget before a byte/item/file/line/tree watchdog became authoritative. Non-timeout watchdog cases now use ten seconds; the dedicated timeout case retains its explicit 0.8-second limit. The final full run passed, so the repair does not weaken the timeout contract. / Windows 冷进程启动与实时扫描还可能在 byte/item/file/line/tree watchdog 成为权威前耗尽原 4 秒墙钟预算。非 timeout watchdog case 现改用 10 秒；专用 timeout case 保持显式 0.8 秒限制。最终全量通过，因此该修复没有弱化 timeout 契约。

The single skip is `tests/contract/test_mediacrawler_supervision.py:556`: POSIX mode bits are not the Windows ACL boundary. It is environment-inapplicable, not a failed feature. No coverage command ran, so execution 0015 makes no coverage claim. / 唯一跳过项为 `tests/contract/test_mediacrawler_supervision.py:556`：POSIX mode bit 不是 Windows ACL 边界；它在当前环境不适用，不是功能失败。本执行未运行 coverage 命令，因此不声明覆盖率。

## Retained and ephemeral-data audit / 保留产物与瞬态数据审计

The read-only audit enumerates tracked and standard-untracked files plus every real file below ignored `.media-sync` and `dist`. It rejects tracked/untracked runtime or credential paths, constructs the three execution markers from split non-secret literals, byte-scans Git-visible/runtime/build files without printing matched data, and verifies that the frozen `0007`/`0008` sentinel roots still exist. / 只读审计枚举 tracked、标准 untracked 文件，以及忽略目录 `.media-sync` 与 `dist` 下的每个真实文件；它拒绝被跟踪/未跟踪的运行或凭据路径，从拆分的非密钥字面量构造三个执行 marker，在不打印命中数据的情况下扫描 Git 可见/runtime/build 字节，并确认冻结的 `0007`/`0008` sentinel 根仍存在。

| Audit / 审计 | Exit / 退出码 | Counts / 计数 |
| --- | ---: | --- |
| Pre-closeout Git/runtime/build inventory and exact marker scan / 收尾前 Git、runtime、build 清单及精确 marker 扫描 | `0` | `tracked=239`; `untracked=1`; `runtime_and_build_files=914`; `ephemeral_marker_hits=0`; `sentinel_roots_preserved=1` |
| Final closeout inventory and exact marker scan / 最终收尾清单及精确 marker 扫描 | `0` | `tracked=240`; `untracked=0`; `tracked_forbidden=0`; `suspicious_untracked=0`; `runtime_and_build_files=914`; `git_ephemeral_marker_hits=0`; `runtime_ephemeral_marker_hits=0`; `sentinel_roots_preserved=1` |

The end-to-end tests separately scan Author/Content/Asset raw and locators, Job/SyncRun payloads, disposed SQLite and sidecars, detail runtime, download/export work roots, archive, Emby library, source metadata and object representations. Dynamic query, fragment, userinfo, nested-shape and comma-drift sentinels are absent from those durable sinks. / 端到端测试还分别扫描 Author/Content/Asset raw 与 locator、Job/SyncRun payload、dispose 后 SQLite 及 sidecar、detail runtime、下载/导出工作根、归档、Emby 媒体库、source 元数据与对象表示；动态 query、fragment、userinfo、嵌套形状及逗号漂移哨兵不会进入这些持久落点。

## Live qualification / 真人验收

| Item / 项目 | Status / 状态 |
| --- | --- |
| Real QR/Cookie/saved-session login / 真人 QR/Cookie/saved-session 登录 | `NOT_RUN` |
| Real creator scan and incremental rerun / 真人作者扫描与增量重跑 | `NOT_RUN` |
| Real detail and signed CDN transfer / 真人 detail 与签名 CDN 传输 | `NOT_RUN` |
| Real platform bytes through FFmpeg/ffprobe / 真实平台字节经 FFmpeg/ffprobe | `NOT_RUN` |
| Real Emby/Jellyfin scan and playback / 真人 Emby/Jellyfin 重扫与播放 | `NOT_RUN` |

Offline fake checkout, fake detail runner, mock DNS/HTTP, synthetic bytes and controlled probing do not promote any live row. Same-ID/same-origin/path byte replacement, trusted-Subscription author ownership and injected detail-cleanup failure remain the explicit limitations recorded in `goal.md` and `progress.md`. / 离线 fake checkout、fake detail runner、mock DNS/HTTP、合成字节与受控 probe 不会提升任何真人行。同 ID/同 origin/path 字节替换、受信 Subscription 作者归属及注入 detail 清理失败继续作为 `goal.md` 与 `progress.md` 中的明确限制。
