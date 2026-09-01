# Execution 0018 verification / 执行 0018 验证记录

- Status / 状态：Baseline PASS; implementation not run yet / 基线通过；实现尚未运行
- Date / 日期：2026-09-01
- Starting commit / 起始提交：`00add11`

## Selection evidence / 选型证据

| Candidate / 候选 | Locked evidence / 锁定证据 | Decision / 决策 |
| --- | --- | --- |
| XHS video / 小红书视频 | `store/xhs/__init__.py` emits origin-key or H.264 `video_url`; media-sync already normalizes VIDEO, refreshes XHS and probes/archives/publishes video. / `store/xhs/__init__.py` 输出 origin-key 或 H.264 `video_url`；media-sync 已能归一化 VIDEO、刷新小红书并探测/归档/发布视频。 | Execution 0018 / 本轮实现 |
| Tieba static images / 贴吧静态图片 | `TiebaNote` has no media field; first-floor API/HTML media is discarded before JSONL and anti-hotlink fields require a frozen redacted fixture. / `TiebaNote` 无媒体字段；首楼 API/HTML 媒体在 JSONL 前被丢弃，且防盗链字段需要冻结的脱敏夹具。 | Future integration shim / 后续集成 shim |
| Zhihu static/video / 知乎静态图/视频 | `ZhihuContent` retains text/landing URL only; HTML image attributes and nested playable-video structures are discarded before JSONL. / `ZhihuContent` 只保留文本/落地页 URL；HTML 图片属性及嵌套可播放视频结构在 JSONL 前被丢弃。 | Future integration shim / 后续集成 shim |

## Pre-edit baseline / 编辑前基线

| Check / 检查 | Command / 命令 | Result / 结果 |
| --- | --- | --- |
| Seven-file related pytest / 七文件相关 pytest | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_asset_download_orchestration.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_pipeline_runtime.py tests/integration/test_xhs_creator_authority_pipeline.py tests/unit/test_mediacrawler_refresh.py` | `PASS` — `167 passed in 46.50s` |
| Git baseline / Git 基线 | `git status --short --branch`; local/tracking/remote SHA reconciliation / 本地、跟踪、远端 SHA 核对 | `PASS` — clean `00add11` / 干净 `00add11` |

## Planned implementation gates / 计划实现门禁

| Gate / 门禁 | Planned evidence / 计划证据 | Current / 当前 |
| --- | --- | --- |
| XHS video URL contract / 小红书视频 URL 合约 | HTTP/HTTPS XHS CDN host/path, exact-one variant, malformed/foreign rejection / HTTP/HTTPS 小红书 CDN host/path、唯一变体、畸形/外部拒绝 | `NOT_RUN` |
| Creator/detail process contract / 作者/detail 进程合约 | Real isolated fake checkout, bounded creator lookup, cleanup and DEFAULT profile / 真实隔离 fake checkout、有界作者查找、清理及 DEFAULT profile | `NOT_RUN` |
| Download/archive/Emby composition / 下载/归档/Emby 组合 | Synthetic MP4/PNG, mock DNS/HTTP, controlled probe, SHA-256 and replay / 合成 MP4/PNG、mock DNS/HTTP、受控探测、SHA-256 及重放 | `NOT_RUN` |
| Complete quality gates / 完整质量门禁 | Focused/full pytest, Ruff, mypy, compileall, upstream locks, build, docs and artifact audit / 专项/完整 pytest、Ruff、mypy、compileall、上游锁、构建、文档及产物审计 | `NOT_RUN` |

## Live qualification / 真人在线验收

| Row / 验收行 | Result / 结果 |
| --- | --- |
| Real XHS QR/Cookie login / 真人小红书 QR/Cookie 登录 | `NOT_RUN` |
| Real creator/feed/detail lookup / 真实 creator/feed/detail 查找 | `NOT_RUN` |
| Real XHS CDN video/artwork bytes / 真实小红书 CDN 视频/封面字节 | `NOT_RUN` |
| Real Emby/Jellyfin scan/playback / 真实 Emby/Jellyfin 扫描/播放 | `NOT_RUN` |

Offline mocks will not change these rows. / 离线 mock 不会改变这些验收行。
