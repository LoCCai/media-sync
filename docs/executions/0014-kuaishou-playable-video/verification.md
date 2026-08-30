# Execution 0014 verification / 执行 0014 验证

- Status / 状态：Baseline only; implementation gates not yet run / 仅完成基线；实现门禁尚未运行
- Environment / 环境：Windows, local workspace, Python environment resolved by `uv` / Windows、本地工作区、由 `uv` 解析 Python 环境
- Evidence date / 证据日期：2026-08-31

## Starting baseline / 起始基线

| Check / 检查 | Command / 命令 | Exit / 退出码 | Result / 结果 |
| --- | --- | ---: | --- |
| Existing ingestion, detail, refresh/runtime, downloader/network, Emby layout/application and generic offline pipeline / 既有导入、detail、refresh/runtime、下载器/网络、Emby layout/application 及通用离线 pipeline | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/unit/test_media_downloader.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py tests/integration/test_emby_application.py tests/integration/test_offline_media_pipeline.py` | `0` | `PASS` — `211 passed in 27.81s` |

This baseline proves the predecessor Kuaishou normalizer/unit refresh cases and platform-neutral media machinery. It does not prove the pinned Kuaishou detail configuration, exact runtime provenance, video+cover transfer, Emby primary-media layout or platform-level replay. / 该基线证明既有快手 normalizer/单元 refresh case 及平台无关媒体机制；不证明锁定的快手 detail 配置、精确 runtime 来源、视频+封面传输、Emby 主媒体目录或平台级重放。

## Planned focused gates / 计划中的专项门禁

| Scope / 范围 | Evidence required / 所需证据 | Status / 状态 |
| --- | --- | --- |
| Discovery identity and durable raw / 发现身份与持久 raw | Exact video/cover remote IDs, positions, MIME/source hints, adapter locators, query rotation/generation behavior, and known/unknown query sentinels absent from ORM/SQLite raw / 精确视频/封面 remote ID、position、MIME/source hint、adapter locator、query 轮换/generation 行为，以及 ORM/SQLite raw 中已知/未知 query 哨兵均不存在 | `NOT_RUN` |
| Pinned detail process / 锁定 detail 进程 | Raw-ID `KS_SPECIFIED_ID_LIST`, detail/JSONL/media-off switches, signed output, bounded frame, repr safety and normal-success cleanup / 纯 ID `KS_SPECIFIED_ID_LIST`、detail/JSONL/媒体关闭开关、签名输出、有界 frame、repr 安全及正常成功清理 | `NOT_RUN` |
| Exact refresh/runtime / 精确 refresh/runtime | Bound Subscription/Account, exact content/asset/source hint, missing/drift/duplicate outcomes and no persistent signed URL / 绑定 Subscription/Account、精确 content/asset/source hint、缺失/漂移/重复结果及无签名 URL 持久化 | `NOT_RUN` |
| Playable video+cover / 可播放视频+封面 | Deterministic MP4/PNG, default profile without Cookie/Auth, probe, SHA-256 archive, durable Asset/Job and Emby `.mp4`/poster/NFO/source / 确定性 MP4/PNG、无 Cookie/Auth 默认 profile、探测、SHA-256 归档、持久 Asset/Job 及 Emby `.mp4`/海报/NFO/source | `NOT_RUN` |
| Replay and closed sinks / 重放与封闭落点 | `already_verified`/`already_exported`, no repeated detail/network/probe, and signed-sentinel scans across SQLite/runtime/work/archive/library/repr/Git / `already_verified`/`already_exported`、无重复 detail/network/probe，以及 SQLite/runtime/work/archive/library/repr/Git 签名哨兵扫描 | `NOT_RUN` |

## Planned focused command / 计划专项命令

```powershell
uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_kuaishou_playable_pipeline.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py
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

Full pytest, Ruff lint/format, mypy, documentation links, pinned-upstream verification, package build, patch checks and final retained/Git signed-sentinel audits remain `NOT_RUN`. No coverage or live qualification claim is made by this planning record. / 完整 pytest、Ruff lint/格式、mypy、文档链接、锁定上游验证、包构建、补丁检查及最终 retained/Git 签名哨兵审计仍为 `NOT_RUN`。本计划记录不声明覆盖率或真人验收。
