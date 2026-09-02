[English](verification.md) | **中文**

# 执行 0038 验证

- 状态：冻结的离线小红书实况照片范围通过全部最终门禁；真人验收 `NOT_RUN`
- 日期：2026-09-03
- 前驱：执行 0037 收尾 `b9c88c4afab6ba2d9d2a43efea63f63cd6cd31ca`
- 计划提交：`650c256`

## 基线（任何 0038 变更之前）

| 检查 | 结果 |
| --- | --- |
| 0037 专项回归 | `PASS — 344 passed in 6.32s` |
| 0037 完整套件 | `PASS — 2020 passed, 1 skipped in 370.56s` |
| Ruff、格式、strict mypy、docs、upstream | `PASS`（记录于 0037 验证文档） |

## 实现证据

| 范围 | 结果 |
| --- | --- |
| Store 边界捕获 | `PASS` — 新 shim 在双子进程为恰一张图的 `type="normal"` note 精确捕获冻结的 `image_list[0].live_photo.stream.h264[0].master_url`；嵌套畸形、外域、超过一张图与错误类型不捕获 |
| 归一化分支 | `PASS` — MIXED 内容与一个 `{note_id}:image:0` IMAGE 加一个 `{note_id}:video:0` VIDEO 及空 `video_url` 标量；payload 与形状漂移隔离；私有字段递归移除 |
| 刷新绑定 | `PASS` — creator 回退的 `normal` 类型分支接受精确无歧义的一图加一视频形状并重校验实况 URL；路径漂移以 `locator_refresh_asset_mismatch` 关闭；普通 `normal`/`video` note 字节级兼容 |
| 下载与发布 | `PASS` — 双资产经 DEFAULT profile 下载（静态 PNG 门与 MP4 探测）、以不同 SHA-256 摘要归档并发布带 poster 的 Emby 集，零工作重放 |
| 不泄密 | `PASS` — 实况哨兵与签名 URL 不出现在任何留存的 runtime/work/archive/export/library 树或 SQLite 产物中 |
| Fixture 兼容 | `PASS` — 共享 fake-project 基座与 XHS fake checkout 补齐新 shim 所需的最小 store 模块；安全矩阵、saved-session 与监督套件保持绿色 |

## 测试与质量门

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 专项实现回归 | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_xhs_playable_video_pipeline.py tests/integration/test_xhs_creator_authority_pipeline.py` | `PASS — 355 passed in 6.92s` |
| Detail 刷新契约套件 | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py` | `PASS — 116 passed in 80.18s` |
| 实况收尾复跑 | `uv run pytest -q tests/integration/test_xhs_playable_video_pipeline.py::test_xhs_live_photo_reaches_emby_with_zero_work_replay` | `PASS — 1 passed in 2.14s` |
| 完整套件 | `uv run pytest -q` | `PASS — 2032 passed, 1 skipped in 371.84s`；跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 509 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 86 source files` |
| Compileall 与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — 编译通过；构建 wheel 与源码分发包` |
| 文档与上游锁定 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 336 Markdown 文件；2 个锁定干净 checkout` |
| Git/上游审计 | 显式 status 与跟踪路径扫描 | `PASS — 仅预期变更加一个新模块；跟踪 runtime/upstream/dist 0；两个上游 dirty 计数 0` |

## 不宣称

不宣称运行过覆盖率。未执行任何真实账户、登录、作者流、小红书 API、CDN 字节或 Emby/Jellyfin 服务器交互；全部真人行保持 `NOT_RUN`。冻结的 `live_photo` 形状是文档化的 store 输入契约而非实活验证。
