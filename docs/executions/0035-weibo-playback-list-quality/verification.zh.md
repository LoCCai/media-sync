[English](verification.md) | **中文**

# 执行 0035 验证

- 状态：冻结的离线 `playback_list` 画质选择范围通过全部最终门禁；真人验收 `NOT_RUN`
- 日期：2026-09-03
- 前驱：执行 0034 收尾 `3cdd0fc`
- 计划提交：`ecc08da`

## 基线（任何 0035 变更之前）

| 检查 | 结果 |
| --- | --- |
| 0034 专项回归 | `PASS — 445 passed` |
| 0034 detail 契约 | `PASS — 106 passed in 69.98s` |
| 0034 完整套件 | `PASS — 2002 passed, 1 skipped in 352.79s` |
| Ruff、格式、strict mypy、docs、upstream | `PASS`（记录于 0034 验证文档） |

## 实现证据

| 范围 | 结果 |
| --- | --- |
| 封闭画质选择 | `PASS` — 1–8 项 `playback_list` 在封闭偏好 `1080p > 720p > 540p > 480p > 360p` 下选择最高的合法项，每个候选 URL 都经 0031 封闭校验器重校验 |
| 标量优先 | `PASS` — `stream_url` 路径保持第一且字节级兼容；仅当标量缺失或无效时才查询 `playback_list` |
| 关闭 | `PASS` — 未知或缺失画质标签、无效 URL、九项列表与错误形状不捕获，帖回退到非视频结局 |
| 契约组合 | `PASS` — 真实子进程在双项列表中解析出最高封闭画质并以 `locator_refresh_asset_mismatch` 关闭不可用形状；两个列表 URL 均不在留存 runtime 树中 |
| 集成 | `PASS` — playback 来源帖归一化为 VIDEO 与无 query 提示、经 DEFAULT profile 下载、归档、发布 Emby `.mp4` 并零工作重放且不保留哨兵 |

## 测试与质量门

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 专项实现回归 | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_weibo_image_pipeline.py tests/integration/test_weibo_playable_video_pipeline.py` | `PASS — 451 passed in 74.84s`（集成前快照；最终集成为下方补充） |
| 微博管线套件 | `uv run pytest -q tests/integration/test_weibo_playable_video_pipeline.py` | `PASS — 4 passed in 2.70s` |
| Playback 收尾复跑 | `uv run pytest -q tests/integration/test_weibo_playable_video_pipeline.py::test_weibo_playback_list_sourced_video_reaches_emby_with_zero_work_replay` | `PASS — 1 passed in 1.57s` |
| 完整套件 | `uv run pytest -q` | `PASS — 2010 passed, 1 skipped in 360.55s`；跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 481 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 85 source files` |
| Compileall 与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — 编译通过；构建 wheel 与源码分发包` |
| 文档与上游锁定 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 312 Markdown 文件；2 个锁定干净 checkout` |
| Git/上游审计 | 显式 status 与跟踪路径扫描 | `PASS — 仅预期变更；跟踪 runtime/upstream/dist 0；两个上游 dirty 计数 0` |

## 不宣称

不宣称运行过覆盖率。未执行任何真实账户、登录、作者流、微博 API、CDN 字节或 Emby/Jellyfin 服务器交互；全部真人行保持 `NOT_RUN`。冻结的 `playback_list` 形状与画质标签是文档化的 m.weibo.cn 契约而非实活验证。
