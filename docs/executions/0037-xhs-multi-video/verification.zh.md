[English](verification.md) | **中文**

# 执行 0037 验证

- 状态：冻结的离线小红书多视频范围通过全部最终门禁；真人验收 `NOT_RUN`
- 日期：2026-09-03
- 前驱：执行 0036 收尾 `145176f8624f5c1518b6cd28cea3f9aa3d938454`
- 计划提交：`d858147`

## 基线（任何 0037 变更之前）

| 检查 | 结果 |
| --- | --- |
| 0036 专项回归 | `PASS — 341 passed in 4.29s` |
| 0036 完整套件 | `PASS — 2016 passed, 1 skipped in 370.47s` |
| Ruff、格式、strict mypy、docs、upstream | `PASS`（记录于 0036 验证文档） |

## 实现证据

| 范围 | 结果 |
| --- | --- |
| 有界物化 | `PASS` — 1–16 个逗号拼接候选物化有序 `{note_id}:video:0..N-1` VIDEO 资产；17 候选记录以 `INVALID_RECORD` 隔离；其余保持既有宽容解析不变 |
| 刷新标量放宽 | `PASS` — `_validated_xhs_media_scalar` 接受有界 1–16 有序互异元组，每个候选重校验为合法 `xhscdn.com` URL；重复、内嵌漂移与超界标量关闭 |
| Creator 目标绑定 | `PASS` — fresh detail 资产必须精确复现视频元组（数量、position 0..N-1、URL 顺序）；替换路径以 `locator_refresh_asset_mismatch` 关闭，17 候选标量以 `locator_refresh_schema_changed` 关闭 |
| 下载与发布 | `PASS` — 两个 position 经 DEFAULT profile 与 MP4 探测下载、以不同 SHA-256 摘要归档并发布两个 Emby 集，零工作重放 |
| 不泄密 | `PASS` — 多视频哨兵与两个签名 URL 不出现在任何留存的 runtime/work/archive/export/library 树或 SQLite 产物中 |

## 测试与质量门

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 专项实现回归 | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_xhs_playable_video_pipeline.py tests/integration/test_xhs_creator_authority_pipeline.py tests/integration/test_scheduled_offline_pipeline.py` | `PASS — 344 passed in 6.32s` |
| 多视频收尾复跑 | `uv run pytest -q tests/integration/test_xhs_playable_video_pipeline.py::test_xhs_multi_video_reaches_emby_with_zero_work_replay` | `PASS — 1 passed in 2.18s` |
| 完整套件 | `uv run pytest -q` | `PASS — 2020 passed, 1 skipped in 370.56s`；跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 498 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 85 source files` |
| Compileall 与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — 编译通过；构建 wheel 与源码分发包` |
| 文档与上游锁定 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 328 Markdown 文件；2 个锁定干净 checkout` |
| Git/上游审计 | 显式 status 与跟踪路径扫描 | `PASS — 仅预期变更；跟踪 runtime/upstream/dist 0；两个上游 dirty 计数 0` |

## 不宣称

不宣称运行过覆盖率。未执行任何真实账户、登录、作者流、小红书 API、CDN 字节或 Emby/Jellyfin 服务器交互；全部真人行保持 `NOT_RUN`。
