[English](verification.md) | **中文**

# 执行 0025 验证记录

- 状态：冻结离线范围通过全部最终门禁；登录/现网验收 `NOT_RUN`
- 日期：2026-09-02
- 前置：`46905a50bbba19b7c4b74a0f7a274d5efdb013d6`
- 计划提交：`8e9467d2ecbedfd8f87e8d1d2ffb5a66d6d15591`
- 实现提交：`fe45abcb7262c3d70437aff82a05609e43902af4`

## 前置基线

| 检查 | 结果 |
| --- | --- |
| Execution 0024 专项回归 | `PASS — 456 passed in 66.47s` |
| Execution 0024 完整套件 | `PASS — 1780 passed, 1 skipped in 333.43s` |
| 生产 ffmpeg/ffprobe 收尾复验 | `PASS — 1 passed in 1.83s` |
| 文档/上游/仓库审计 | 112 份 Markdown；2 个锁定且干净的 checkout；跟踪 300；未跟踪 0；跟踪 runtime/upstream 0` |
| 本地/tracking/GitHub 核对 | `PASS — 46905a50bbba19b7c4b74a0f7a274d5efdb013d6` |

## 已实现证据

| 范围 | 结果 |
| --- | --- |
| 候选顺序与边界 | 每个 DASH 组件按来源顺序使用已校验的“主地址 + 0..8 个备用地址”；主地址成功时备用地址 DNS/HTTP 为零 |
| 可切换失败 | DNS、timeout、传输、中断、HTTP 与 partial Range 不兼容在同一截止时间下推进候选 |
| 关闭失败类别 | 禁用/混合网络策略、重定向/header/encoding、chunk/size、文件系统、探测与合并失败不会触碰后续候选 |
| 严格 partial 连续性 | 备用追加要求 offset、总长度与 validator 完全一致；中断可跨候选续传；混合无效候选保留字节；完整轮次 `200`/错误 `206` 拒绝后才有界丢弃/restart |
| 穷尽语义 | 全部 `401`/`403` 返回 `locator_refresh_auth_expired`；混合穷尽返回最后一个固定错误且不披露 URL/host |
| 独立组件 | 视频主地址 `503` 与音频主地址 `403` 各自到达备用地址，完成探测、组合字节约束及一次合并 |
| 生产进程组合 | 备用 H.264/AAC 组件贯穿完整链路；最终 MP4 同时含视频与音频流 |
| 瞬态边界 | 签名主/备用值、私有字段与胜出序号不存在于保留 SQLite、Job、runtime、work、归档、导出树及错误中 |
| 兼容与恢复 | 无备用地址、无声 DASH、单 P/多分 P progressive、合并失败、已发布成品恢复、清理与零工作重放保持通过 |

## 测试与质量门禁

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 实现专项回归 | `uv run pytest tests/unit/test_media_locator.py tests/unit/test_mediacrawler_refresh.py tests/unit/test_media_mux.py tests/unit/test_media_dash_downloader.py tests/unit/test_media_downloader.py tests/unit/test_cli.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_asset_download_orchestration.py tests/integration/test_pipeline_runtime.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_bilibili_multipart_progressive_pipeline.py tests/integration/test_bilibili_dash_pipeline.py -q` | `PASS — 466 passed in 66.96s` |
| DASH 候选单元边界 | `uv run pytest -q tests/unit/test_media_dash_downloader.py` | `PASS — 17 passed in 1.43s` |
| 生产备用路径 ffmpeg/ffprobe 组合 | `uv run pytest -q tests/integration/test_bilibili_dash_pipeline.py` | 文档收尾复验 `1 passed in 1.74s`（实现运行 `1.78s`）；最终归档与 Emby MP4 同时含视频与音频 |
| 完整套件 | `uv run pytest -q` | 跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | 全部通过；286 个文件格式正确` |
| 严格 mypy | `uv run mypy --strict src` | 84 个源码文件无问题` |
| 字节编译与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | wheel 与源码包构建成功` |
| 文档与上游锁 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | 116 份 Markdown；2 个锁定 checkout` |
| Git/上游/diff 审计 | 显式状态、跟踪/runtime/upstream 与 diff 检查 | 跟踪 304；未跟踪 0；跟踪 runtime/upstream 0；上游 diff 为 0；两个上游 dirty 数均为 0` |

不宣称运行过 coverage。

## Git 核对

实现 `fe45abcb7262c3d70437aff82a05609e43902af4` 已推送并在本地 `main` 与 `origin/main` 间核对一致。包含本记录的提交即双语文档收尾；其自引用 SHA 有意只保留在 Git 历史中。

## 登录与现网验收

| 验收行 | 结果 |
| --- | --- |
| 真人 Bilibili QR/Cookie 登录 | `NOT_RUN` |
| 登录态 DASH 详情/播放 API | `NOT_RUN` |
| 真实主/备用 bilivideo CDN 行为 | `NOT_RUN` |
| 真实 Emby/Jellyfin 扫描与播放 | `NOT_RUN` |

离线证据不能代表上述真人行、progressive 备用故障切换或完整 Bilibili 支持通过。
