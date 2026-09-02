[English](verification.md) | **中文**

# 执行 0024 验证记录

- 状态：冻结离线范围通过全部最终门禁；登录/现网验收 `NOT_RUN`
- 日期：2026-09-02
- 前置：`d4c9941d2d5fb1206cd9b1a60ce2cc344a9e66e3`
- 计划提交：`a7d038e383c76f2c29825c6f42ac7ff29b967693`
- 实现提交：`12314b927dcaac97dc9ae184c03f98153f3ef687`

## 前置基线

| 检查 | 结果 |
| --- | --- |
| Execution 0023 专项回归 | `PASS — 436 passed in 53.96s` |
| Execution 0023 完整套件 | `PASS — 1739 passed, 1 skipped in 321.25s` |
| 质量/构建/文档/上游审计 | `PASS` |
| 本地/tracking/GitHub 核对 | `PASS — d4c9941d2d5fb1206cd9b1a60ce2cc344a9e66e3` |
| 本地 ffmpeg/ffprobe 探测 | 两个可执行文件均已发现` |

## 已实现证据

| 范围 | 结果 |
| --- | --- |
| 精确播放请求 | 协议 v5 以 WBI 签名及精确参数调用，完整当前分 P 元组继续绑定 |
| DASH 选择 | 最高受支持画质；同画质 AVC → HEV → AV1；锁定普通/杜比/Hi-Res 顺序；合法无声 target；畸形与超限形状关闭失败 |
| 瞬态边界 | 签名主/备用/组件 URL 为 repr-safe 且只存在于运行时，保留 SQLite、Job、runtime、归档与导出树中均不存在 |
| 组件生命周期 | 独立 generation-scoped 音视频 store、严格中断/Range 续传、组件结构探测、组合字节上限、固定有界 ffmpeg stream-copy 与成品探测通过 |
| 失败与恢复 | 合并失败不发布且保留已验证组件；已准备且发布的成品无需 detail/DNS/HTTP/ffmpeg 即可恢复；成功编排清理成品/组件状态 |
| 兼容性 | 带音频 DASH 产生一个合并 VIDEO，无声 DASH 产生一个 remux VIDEO，既有单 P/多分 P progressive 路径保持通过 |
| 生产进程组合 | 真实 H.264 与 AAC 组件贯穿完整链路；最终 MP4 同时含视频与音频流 |
| 能力预检 | doctor 报告 ffmpeg；独立与 pipeline 路径均在持久 child 工作前拒绝缺失的 Bilibili 合并能力 |

备用 URL 已在瞬态 target 中完成校验与表达，但本次有意不声明 CDN 故障切换。

## 测试与质量门禁

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 实现专项回归 | `uv run pytest tests/unit/test_media_locator.py tests/unit/test_mediacrawler_refresh.py tests/unit/test_media_mux.py tests/unit/test_media_dash_downloader.py tests/unit/test_media_downloader.py tests/unit/test_cli.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_asset_download_orchestration.py tests/integration/test_pipeline_runtime.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_bilibili_multipart_progressive_pipeline.py tests/integration/test_bilibili_dash_pipeline.py -q` | `PASS — 456 passed in 66.47s` |
| 生产 ffmpeg/ffprobe 组合 | `uv run pytest tests/integration/test_bilibili_dash_pipeline.py -q` | 最终归档与 Emby MP4 同时含视频和音频 |
| 完整套件 | `uv run pytest -q` | 跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | 全部通过；282 个文件格式正确` |
| 严格 mypy | `uv run mypy --strict src` | 84 个源码文件无问题` |
| 字节编译与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | wheel 与源码包构建成功` |
| 文档与上游锁 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | 112 份 Markdown；2 个锁定 checkout` |
| Git/上游/diff 审计 | 显式状态、跟踪/runtime/upstream 与 diff 检查 | 跟踪 300；未跟踪 0；跟踪 runtime/upstream 0；上游 diff 为 0；两个上游 dirty 数均为 0` |
| 文档收尾复验 | 上述文档、上游、diff 与审计检查 | 1 项通过，耗时 1.83 秒；112 份 Markdown；2 个锁定 checkout；跟踪 300；未跟踪 0；跟踪 runtime/upstream 0；两个上游 dirty 数均为 0` |

不宣称运行过 coverage。

## Git 核对

实现 `12314b927dcaac97dc9ae184c03f98153f3ef687` 已推送并在本地 `main` 与 `origin/main` 间核对一致。包含本记录的提交即双语文档收尾；其自引用 SHA 有意只保留在 Git 历史中。

## 登录与现网验收

| 验收行 | 结果 |
| --- | --- |
| 真人 Bilibili QR/Cookie 登录 | `NOT_RUN` |
| 登录态 DASH 详情/播放 API | `NOT_RUN` |
| 真实 bilivideo 组件/CDN 行为 | `NOT_RUN` |
| 真实 Emby/Jellyfin 扫描与播放 | `NOT_RUN` |

离线证据不能代表上述真人行或完整 Bilibili 支持通过。
