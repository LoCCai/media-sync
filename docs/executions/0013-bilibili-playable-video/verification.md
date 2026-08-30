# Execution 0013 verification / 执行 0013 验证

- Status / 状态：Offline implementation and closeout gates pass; live qualification remains `NOT_RUN` / 离线实现与收尾门禁通过；真人验收仍为 `NOT_RUN`
- Environment / 环境：Windows, local workspace, Python environment resolved by `uv` / Windows、本地工作区、由 `uv` 解析 Python 环境
- Evidence date / 证据日期：2026-08-31
- Plan commit / 计划提交：`46323bd`
- Implementation commit / 实现提交：`dd6cfec`

## Starting baseline / 起始基线

| Check / 检查 | Command / 命令 | Exit / 退出码 | Result / 结果 |
| --- | --- | ---: | --- |
| Existing ingestion, detail refresh, locator/network/downloader, Emby layout and offline pipeline / 既有导入、detail refresh、locator/网络/下载、Emby layout 与离线 pipeline | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_media_downloader.py tests/unit/test_emby_layout.py tests/integration/test_offline_media_pipeline.py tests/integration/test_scheduled_offline_pipeline.py` | `0` | `PASS` — `158 passed in 6.47s` |

This was predecessor-only evidence: it proved the prior Bilibili cover path and platform-neutral media pipeline, not the new video slice. Every delivered claim below comes from post-implementation evidence. / 该基线只是前置证据：它证明既有 Bilibili 封面路径与平台无关媒体流水线，不证明新视频切片；下方交付声明全部来自实现后证据。

## Focused implementation evidence / 实现专项证据

| Scope / 范围 | Command / 命令 | Exit / 退出码 | Result / 结果 |
| --- | --- | ---: | --- |
| Discovery, exact aid/CID and single-`durl` child contract, nullable-slot application/runtime boundary, private normalization bridge, Bilibili network profile, downloader/re-resolution and offline playable-to-Emby pipeline / 发现、精确 aid/CID 与单 `durl` child 契约、可空槽应用/运行时边界、私有归一化桥、Bilibili 网络 profile、下载器/重解析及离线可播放到 Emby 流水线 | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_bilibili_playable_pipeline.py tests/unit/test_domain.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_mediacrawler_refresh.py` | `0` | `PASS` — `223 passed in 19.85s` |

The focused gate proves a stable `NULL`-source `<aid>:video:0` slot, exact Subscription-bound selection, aid/first-CID validation, exactly one valid progressive `durl`, fixed temporary/unsupported/invalid outcomes, memory-only URL bridging, raw stripping, cover compatibility, fixed UA/Referer/Origin without Cookie or Authorization, redirect/resume and one 401/403 re-resolution, synthetic bytes through controlled probing/archive/Emby `.mp4`, and idempotent replay. Near-miss nullable slots and non-null Bilibili video hints fail before secret lookup or child construction. / 专项门禁证明：稳定的 `NULL` source `<aid>:video:0` 槽、绑定精确 Subscription 的选择、aid/首 CID 校验、精确一个合法 progressive `durl`、固定的瞬时/不支持/非法结果、纯内存 URL 桥、raw 剥离、封面兼容、无 Cookie/Authorization 的固定 UA/Referer/Origin、重定向/续传与一次 401/403 重解析、合成字节经受控探测/归档/Emby `.mp4`，以及幂等重放。近似可空槽和非空 Bilibili 视频 hint 都会在密钥读取或 child 构造前失败。

## Complete root closeout gates / 根任务完整收尾门禁

| Check / 检查 | Command / 命令 | Exit / 退出码 | Result / 结果 |
| --- | --- | ---: | --- |
| Complete offline suite / 完整离线套件 | `uv run pytest -q` | `0` | `PASS` — `1199 passed, 1 skipped in 263.14s` |
| Lint / 静态检查 | `uv run ruff check .` | `0` | `PASS` — `All checks passed!` |
| Format / 格式 | `uv run ruff format --check .` | `0` | `PASS` — `212 files already formatted` |
| Strict typing / 严格类型 | `uv run mypy src/media_sync` | `0` | `PASS` — `Success: no issues found in 77 source files` |
| Documentation links / 文档链接 | `uv run python scripts/check_docs.py` | `0` | `PASS` — `Documentation links OK (68 Markdown files checked)` |
| Pinned upstreams / 锁定上游 | `uv run python scripts/check_upstreams.py` | `0` | `PASS` — `Upstreams OK (2 locked checkouts verified)` |
| Source distribution and wheel / 源码包与 wheel | `uv build` | `0` | `PASS` — built `dist\media_sync-0.1.0.tar.gz` and `dist\media_sync-0.1.0-py3-none-any.whl` |
| Patch whitespace / 补丁空白 | `git diff --check` and `git diff --cached --check` / `git diff --check` 与 `git diff --cached --check` | `0` | `PASS` — no output / 无输出 |

The single skip is `tests/contract/test_mediacrawler_supervision.py:556`: POSIX mode bits are not the Windows ACL boundary. It is environment-inapplicable, not a failed feature. No coverage command ran, so execution 0013 makes no coverage claim. / 唯一跳过项为 `tests/contract/test_mediacrawler_supervision.py:556`：POSIX mode bit 不是 Windows ACL 边界；它在当前环境不适用，不是功能失败。本执行未运行 coverage 命令，因此不声明覆盖率。

## Retained and ephemeral-data audit / 保留产物与瞬态数据审计

The final read-only PowerShell audit enumerated `git ls-files`, standard untracked files, and every real file below ignored `.media-sync` and `dist`. It rejected tracked/untracked runtime or credential filenames, constructed the execution sentinel from two non-secret literals, and byte-scanned Git-visible plus runtime/build files without printing matched values or paths. The frozen `.media-sync/verification/0007-closeout-sentinel-root` and `0008-closeout-sentinel-root` were retained and never removed or rewritten. / 最终只读 PowerShell 审计枚举了 `git ls-files`、标准未跟踪文件，以及忽略目录 `.media-sync` 与 `dist` 下的全部真实文件；它拒绝被跟踪/未跟踪的运行时或凭据文件名，从两段非密钥字面量构造执行哨兵，并在不打印命中值或路径的前提下扫描 Git 可见文件与 runtime/build 字节。冻结的 `.media-sync/verification/0007-closeout-sentinel-root` 与 `0008-closeout-sentinel-root` 被完整保留，从未删除或改写。

| Audit / 审计 | Exit / 退出码 | Final counts / 最终计数 |
| --- | ---: | --- |
| Git/runtime/build inventory and exact ephemeral-marker scan / Git、runtime、build 清单及精确瞬态标记扫描 | `0` | `tracked=230`; `untracked=0`; `tracked_forbidden=0`; `suspicious_untracked=0`; `runtime_and_build_files=914`; `git_ephemeral_marker_hits=0`; `runtime_ephemeral_marker_hits=0` |

The offline end-to-end test separately scans its disposed SQLite database and sidecars, MediaCrawler runtime, download work tree, archive and Emby library for the signed URL and private bridge value. It also verifies durable JSON, object `repr`, retained attempt data and emitted metadata contain none of them. / 离线端到端测试还会分别扫描已 dispose 的 SQLite 数据库及 sidecar、MediaCrawler runtime、下载工作树、归档与 Emby library，确认不存在签名 URL 与私有桥值；同时验证持久 JSON、对象 `repr`、保留 attempt 数据及导出元数据均不包含这些值。

## Live qualification matrix / 真人验收矩阵

No real browser, QR scan, account credential, creator endpoint, WBI play-url request, CDN transfer, FFmpeg probe against platform bytes, or Emby/Jellyfin server was used. / 未使用真人浏览器、二维码扫码、账户凭据、作者端点、WBI 播放地址请求、CDN 传输、针对平台字节的 FFmpeg 探测或 Emby/Jellyfin 服务器。

| Platform / 平台 | Real login/session / 真人登录/会话 | Real creator sync / 真人作者同步 | Real signed CDN media / 真人签名 CDN 媒体 | Real Emby/Jellyfin scan/playback / 真人 Emby/Jellyfin 重扫/播放 |
| --- | --- | --- | --- | --- |
| XHS / 小红书 `xhs` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Douyin / 抖音 `dy` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Kuaishou / 快手 `ks` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Bilibili / 哔哩哔哩 `bili` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Weibo / 微博 `wb` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Tieba / 百度贴吧 `tieba` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Zhihu / 知乎 `zhihu` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

## Known limitation and exclusions / 已知限制与排除项

Forward JSONL has no CID, so the durable identity remains the logical `<aid>:video:0` slot. Each unresolved lookup validates the current first CID, but a later same-aid first-CID replacement cannot automatically bump the Asset generation or invalidate already-verified bytes. CID-aware discovery and replacement belong with multi-page identity. / forward JSONL 不含 CID，因此持久身份仍是逻辑 `<aid>:video:0` 槽。每次未解析查询会校验当前首 CID，但后续同 aid 首 CID 替换无法自动提升 Asset generation 或使已验证字节失效；CID-aware 发现与替换应和多 P 身份一并实现。

DASH audio/video selection and muxing, FLV remux, multi-segment concatenation, multiple pages, subtitles, danmaku, backup-URL failover, bangumi/paid/live media, broader seven-platform downloadable media, REST and deployment/HA work remain deferred. These are unsupported or unimplemented scope, not successful qualification claims. / DASH 音视频选择与合并、FLV remux、多段拼接、多 P、字幕、弹幕、备用 URL 故障切换、番剧/付费/直播媒体、更广的七平台可下载媒体、REST 及部署/HA 工作继续后置。这些属于不支持或未实现范围，不是已通过验收的声明。
