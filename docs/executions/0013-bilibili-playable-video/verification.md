# Execution 0013 verification / 执行 0013 验证

- Status / 状态：Baseline only; implementation gates not yet run / 仅完成基线；实现门禁尚未运行
- Environment / 环境：Windows, local workspace, Python environment resolved by `uv` / Windows、本地工作区、由 `uv` 解析 Python 环境
- Evidence date / 证据日期：2026-08-31

## Starting baseline / 起始基线

| Check / 检查 | Command / 命令 | Exit / 退出码 | Result / 结果 |
| --- | --- | ---: | --- |
| Existing ingestion, detail refresh, locator/network/downloader, Emby layout and offline pipeline / 既有导入、detail refresh、locator/网络/下载、Emby layout 与离线 pipeline | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_media_downloader.py tests/unit/test_emby_layout.py tests/integration/test_offline_media_pipeline.py tests/integration/test_scheduled_offline_pipeline.py` | `0` | `PASS` — `158 passed in 6.47s` |

This predecessor baseline proves the existing cover-only Bilibili normalization/refresh path and the platform-neutral download/Emby machinery. It does not prove a Bilibili video Asset, play-url resolution, Bilibili request headers or an end-to-end playable Bilibili output. / 该前置基线证明既有 Bilibili 仅封面归一化/刷新路径，以及平台无关下载/Emby 机制；不证明 Bilibili 视频 Asset、播放地址解析、Bilibili 请求 header 或端到端可播放 Bilibili 输出。

## Planned focused gates / 计划中的专项门禁

| Scope / 范围 | Evidence required / 所需证据 | Status / 状态 |
| --- | --- | --- |
| Discovery identity / 发现身份 | Cover plus locator-only `NULL`-source video shape, dynamic exclusion, replay/generation stability, provenance and no signed persistence / 封面加 locator-only `NULL` source 视频形状、动态排除、重放/generation 稳定、来源追踪及无签名持久化 | `NOT_RUN` |
| First-page detail child / 首 P detail child | Exact aid and first CID, single `durl`, unsupported DASH/multi-segment, malformed/temporary outcomes, memory-only bridge and cleanup / 精确 aid 与首 CID、单 `durl`、不支持 DASH/多段、非法/瞬时结果、纯内存桥接及清理 | `NOT_RUN` |
| Exact refresh / 精确刷新 | Bound Asset/Subscription selection, exact `NULL`-hint exception, ephemeral signed URL, private-field stripping and one 401/403 re-resolution / 绑定 Asset/Subscription 选择、精确 `NULL` hint 例外、瞬态签名 URL、私有字段移除及一次 401/403 重解析 | `NOT_RUN` |
| Bilibili HTTP profile / Bilibili HTTP 配置 | Fixed UA/Referer/Origin, no Cookie/Authorization/arbitrary headers, redirect/resume compatibility / 固定 UA/Referer/Origin、无 Cookie/Authorization/任意 header、重定向/续传兼容 | `NOT_RUN` |
| Playable pipeline / 可播放 pipeline | Synthetic metadata → refresh → bytes → probe → archive → durable Asset/Job → Emby primary `.mp4`, metadata and replay / 合成元数据 → 刷新 → 字节 → 探测 → 归档 → 持久 Asset/Job → Emby 主 `.mp4`、元数据与重放 | `NOT_RUN` |
| Closed sinks / 封闭落点 | SQLite/runtime/log/docs/Git scans for signed URL, Cookie, profile and forbidden header values / SQLite/runtime/log/docs/Git 中签名 URL、Cookie、profile 与禁止 header 值扫描 | `NOT_RUN` |

## Live qualification / 真人验收

No real Bilibili account, creator endpoint, WBI play-url request, CDN media transfer or Emby/Jellyfin server is used by this planning record. Real login, creator sync, first-page CDN retrieval and server scan/playback all remain `NOT_RUN`. DASH, multi-page, subtitle, danmaku and other excluded shapes are unsupported scope, not `NOT_RUN` qualification outcomes. / 本计划记录不使用真人 Bilibili 账户、作者端点、WBI 播放地址请求、CDN 媒体传输或 Emby/Jellyfin 服务器。真人登录、作者同步、首 P CDN 获取及服务器重扫/播放全部保持 `NOT_RUN`。DASH、多 P、字幕、弹幕等排除形状属于不支持范围，不是 `NOT_RUN` 验收结果。

## Complete closeout gates / 完整收尾门禁

Full pytest, Ruff lint and format, mypy, documentation links, pinned-upstream verification, package build, `git diff --check` and final retained-artifact/high-confidence-secret audits remain `NOT_RUN`. No implementation completion or live qualification is claimed by this planning record. / 完整 pytest、Ruff lint 与格式、mypy、文档链接、锁定上游验证、包构建、`git diff --check` 及最终保留产物/高置信密钥审计仍为 `NOT_RUN`。本计划记录不宣称实现完成或真人验收通过。
