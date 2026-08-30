# Execution 0015 verification / 执行 0015 验证

- Status / 状态：Baseline only; implementation gates not yet run / 仅完成基线；实现门禁尚未运行
- Environment / 环境：Windows, local workspace, Python environment resolved by `uv` / Windows、本地工作区、由 `uv` 解析 Python 环境
- Evidence date / 证据日期：2026-08-31

## Starting baseline / 起始基线

| Check / 检查 | Command / 命令 | Exit / 退出码 | Result / 结果 |
| --- | --- | ---: | --- |
| Existing ingestion, detail, refresh/runtime, downloader/network, Emby application/layout and Bilibili/Kuaishou playable compositions / 既有导入、detail、refresh/runtime、下载器/网络、Emby application/layout 及 Bilibili/快手可播放组合 | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py tests/integration/test_emby_application.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_kuaishou_playable_pipeline.py` | `0` | `PASS` — `269 passed in 34.05s` |

This baseline proves predecessor Douyin unit refresh/process cases and both existing playable-platform pipelines. It does not prove Douyin durable raw closure, exact composed runtime, video+cover transfer, Emby primary-media layout or platform replay. / 该基线证明既有抖音单元 refresh/process case 与两个现有可播放平台 pipeline；不证明抖音持久 raw 封闭、精确组合 runtime、视频+封面传输、Emby 主媒体 layout 或平台重放。

## Planned focused gates / 计划中的专项门禁

| Scope / 范围 | Evidence required / 所需证据 | Status / 状态 |
| --- | --- | --- |
| Discovery identity and durable raw / 发现身份与持久 raw | Exact video/cover IDs, positions, MIME/source hints, comma-list semantics and dynamic query/userinfo/fragment/nested sentinels absent from ORM/SQLite raw / 精确视频/封面 ID、position、MIME/source hint、逗号列表语义，以及动态 query/userinfo/fragment/嵌套哨兵不进入 ORM/SQLite raw | `NOT_RUN` |
| Pinned pure-ID detail / 锁定纯 ID detail | Numeric `DY_SPECIFIED_ID_LIST`, detail/JSONL/media-off switches, bounded frame, repr safety and normal-success cleanup / numeric `DY_SPECIFIED_ID_LIST`、detail/JSONL/媒体关闭开关、有界 frame、repr 安全及正常成功清理 | `NOT_RUN` |
| Exact runtime and playable publication / 精确 runtime 与可播放发布 | Exact Account/Subscription provenance, default profile without Cookie/Auth/Referer/Origin, MP4 probe, PNG, SHA-256 archive and Emby `.mp4`/poster/NFO/source / 精确 Account/Subscription 来源、无 Cookie/Auth/Referer/Origin 默认 profile、MP4 probe、PNG、SHA-256 归档及 Emby `.mp4`/海报/NFO/source | `NOT_RUN` |
| Replay and closed sinks / 重放与封闭落点 | Query rotation keeps generation; live counters prove no repeated detail/network/probe; marker scans cover SQLite/runtime/work/archive/library/repr/Git/build / query 轮换保留 generation；实时计数证明无重复 detail/network/probe；marker 扫描覆盖 SQLite/runtime/work/archive/library/repr/Git/build | `NOT_RUN` |

## Planned focused command / 计划专项命令

```powershell
uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_douyin_playable_pipeline.py tests/integration/test_kuaishou_playable_pipeline.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py
```

## Live qualification / 真人验收

| Item / 项目 | Status / 状态 |
| --- | --- |
| Real QR/Cookie/saved-session login / 真人 QR/Cookie/saved-session 登录 | `NOT_RUN` |
| Real creator scan and incremental rerun / 真人作者扫描与增量重跑 | `NOT_RUN` |
| Real detail and signed CDN transfer / 真人 detail 与签名 CDN 传输 | `NOT_RUN` |
| Real platform bytes through FFmpeg/ffprobe / 真实平台字节经 FFmpeg/ffprobe | `NOT_RUN` |
| Real Emby/Jellyfin scan and playback / 真人 Emby/Jellyfin 重扫与播放 | `NOT_RUN` |

## Complete closeout gates / 完整收尾门禁

Full pytest, Ruff lint/format, mypy, documentation links, pinned-upstream verification, package build, patch checks and final retained/Git/build marker audits remain `NOT_RUN`. No coverage or live qualification claim is made by this planning record. / 完整 pytest、Ruff lint/格式、mypy、文档链接、锁定上游验证、包构建、补丁检查及最终 retained/Git/build marker 审计仍为 `NOT_RUN`。本计划记录不声明覆盖率或真人验收。
