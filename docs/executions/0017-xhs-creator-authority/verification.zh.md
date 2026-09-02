[English](verification.md) | **中文**

# 执行 0017 验证记录

- 状态：离线与文档门禁通过；真人验收 `NOT_RUN`
- 日期：2026-09-01
- 计划提交：`9d19e7e`
- 实现提交：`2f8dbaa`

## 实现证据

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 权限互斥与 schema v3 | `PASS` | 精确 note/creator URL、身份及解码后 xsec 校验在父/request/child 边界重复执行。 |
| 精确 fallback 与覆盖 | `PASS` | 精确 Subscription 作者 secret 与有界 `max_items`；显式 detail 优先且不解析作者 secret。 |
| 静态目标与组合 | `PASS` | 唯一普通 IMAGE/GALLERY 全 IMAGE 目标贯穿 DEFAULT HTTP、图片校验、SHA-256 归档及幂等 Emby 输出；重放不新增工作。 |
| 前置校验与分类 | `PASS` | VERIFIED 缺失/损坏修复在变更前 preflight；有效重放零 secret；固定 cause 保持区分；非小红书选项使用被拒绝。 |
| 持久 raw 与密钥落点 | `PASS` | 按字段执行的权限/query 清理保持已接受值形状，且不保留执行 marker。 |

## 六类审查修复

1. 唯一普通静态 creator 结果门。
2. Asset 选择前拒绝重复目标。
3. VERIFIED 归档修复在 quarantine/reset 前 preflight，有效重放零 secret。
4. 专用 pipeline 错误分类与 scheduler 词汇表。
5. 持久 raw 形状保持及按字段执行的权限/query 清理。
6. 拒绝非小红书 CLI 使用小红书选项。

## 测试与质量门禁

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 九文件专项 pytest | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_asset_download_orchestration.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_pipeline_runtime.py tests/integration/test_pipeline_worker.py tests/integration/test_xhs_creator_authority_pipeline.py tests/unit/test_cli.py tests/unit/test_mediacrawler_refresh.py` | `PASS` — `266 passed in 56.90s` |
| 格式后相关 | `uv run pytest -q tests/unit/test_cli.py tests/integration/test_pipeline_runtime.py` | `PASS` — `89 passed in 13.74s` |
| 完整套件 | `uv run pytest -q` | 唯一跳过：Windows POSIX mode-bit |
| 最终 pipeline/worker | `uv run pytest -q tests/integration/test_pipeline_runtime.py tests/integration/test_pipeline_worker.py` | `PASS` — `52 passed in 4.57s` |
| Ruff | `uv run ruff check .` | `PASS` |
| 格式 | `uv run ruff format --check .` | `PASS` — 234 files |
| 严格 mypy | `uv run mypy src/media_sync` | `PASS` — 79 sources |
| 字节编译 | `uv run python -m compileall -q src/media_sync` | `PASS` |
| 上游锁 | `uv run python scripts/check_upstreams.py` | `PASS` — 2 entries |
| 构建 | `uv build` | `PASS` — 2 artifacts |
| Diff 检查 | `git diff --check` and `git diff --cached --check` | `PASS` |
| 编辑后文档 | `uv run python scripts/check_docs.py` | 检查 84 个 Markdown 文件 |

不宣称运行过 coverage。

## 保留产物与 Git 审计

`tracked=252`; `untracked=0`; `tracked_forbidden=0`; `suspicious_untracked=0`; `runtime_and_build_files=914`; `runtime_execution0017_marker_hits=0`; `sentinel_roots_preserved=2/2`; MediaCrawler dirty paths `0`; bili-sync-up dirty paths `0`.

## 真人在线验收

| 验收行 | 结果 |
| --- | --- |
| 真人小红书 QR/Cookie 登录 | `NOT_RUN` |
| 真实 creator/feed/detail 查找 | `NOT_RUN` |
| 真实小红书 CDN 图片字节 | `NOT_RUN` |
| 真实 Emby/Jellyfin 扫描/播放 | `NOT_RUN` |

离线 mock 不代表这些行通过。Execution 0017 已完成，但小红书自动视频/混合/动态/权限过期恢复、其余平台形状及更大的用户目标仍需继续推进。
