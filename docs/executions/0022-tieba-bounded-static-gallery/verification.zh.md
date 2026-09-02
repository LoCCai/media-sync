[English](verification.md) | **中文**

# 执行 0022 验证记录

- 状态：冻结离线范围通过全部最终门禁；登录/现网验收 `NOT_RUN`
- 日期：2026-09-02
- 前置：`817875bdd1902f54c72397fa7da46359fbe33207`
- 计划提交：`fbcb7cf5c642fc9da210faa5d92b6886b350a9b8`
- 实现提交：`b6d03aa1c6705e52c2e47c63086a5b7200c208e7`

## 前置基线

| 检查 | 结果 |
| --- | --- |
| Execution 0021 专项回归 | `PASS — 413 passed in 44.50s` |
| Execution 0021 完整套件 | `PASS — 1668 passed, 1 skipped in 314.72s` |
| 质量/构建/文档/上游/审计 | `PASS` |
| 本地/tracking/GitHub 核对 | `PASS — 817875bdd1902f54c72397fa7da46359fbe33207` |

## 已实现证据

| 范围 | 结果 |
| --- | --- |
| v3 捕获与兼容 | 3 与 64 张有序图片通过；拒绝 65 张、重复、畸形项与多版本声明；保留精确 v1/v2 行为 |
| 有序归一化与存储 | N 项稳定 remote ID/position、无 query 持久 hint 与递归私有字段移除通过 |
| 完整 gallery 刷新 | 每个有效 position 通过；拒绝缺失、新增、重排、替换与重复 gallery |
| 三图归档/Emby 组合 | 不同静态字节、SHA-256 归档、poster/backdrop/三项 gallery/body/NFO/source 与 query-only 零工作重放通过 |
| 保留状态边界 | 保留树中不存在 v1/v2/v3 私有字段或签名 query token/value |

## 测试与质量门禁

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 实现专项回归 | `uv run pytest -q tests/unit/test_tieba_media.py tests/contract/test_tieba_upstream_first_floor_media.py tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_tieba_first_floor_image_pipeline.py tests/integration/test_asset_download_orchestration.py` | `PASS — 433 passed in 48.91s` |
| 有界贴吧 SQLite→Emby 组合 | `uv run pytest -q tests/integration/test_tieba_first_floor_image_pipeline.py` | `PASS — 3 passed in 2.88s` |
| 完整套件 | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run pytest -q -p no:cacheprovider` | 跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | 全部通过；266 个文件格式正确` |
| 严格 mypy | `uv run mypy --strict src` | 82 个源码文件无问题` |
| 字节编译与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | wheel 与源码包构建成功` |
| 文档与上游锁 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | 104 份 Markdown；2 个锁定 checkout` |
| Git/上游审计 | 显式状态、跟踪/runtime/upstream 与 diff 检查 | 跟踪 284；未跟踪 0；跟踪 runtime/upstream 0；两个上游 dirty 数均为 0` |

不宣称运行过 coverage。

## Git 核对

实现 `b6d03aa1c6705e52c2e47c63086a5b7200c208e7` 已在本地 `main`、`origin/main` 与 GitHub 间核对一致。包含本记录的提交即双语文档收尾；其自引用 SHA 有意只保留在 Git 历史中。

## 登录与现网验收

| 验收行 | 结果 |
| --- | --- |
| 真人贴吧 QR/Cookie 登录 | `NOT_RUN` |
| 登录态作者/详情 gallery | `NOT_RUN` |
| 真实 CDN 字节/重定向行为 | `NOT_RUN` |
| 真实 Emby/Jellyfin 扫描/展示 | `NOT_RUN` |

离线证据不能代表上述真人行或完整贴吧媒体支持通过。
