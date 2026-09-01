# Execution 0017 verification / 执行 0017 验证记录

- Status / 状态：Offline and documentation gates pass; live qualification `NOT_RUN` / 离线与文档门禁通过；真人验收 `NOT_RUN`
- Date / 日期：2026-09-01
- Plan commit / 计划提交：`9d19e7e`
- Implementation commit / 实现提交：`2f8dbaa`

## Implementation evidence / 实现证据

| Scope / 范围 | Result / 结果 | Evidence / 证据 |
| --- | --- | --- |
| Authority XOR and schema v3 / 权限互斥与 schema v3 | `PASS` | Exact note/creator URL, identity and decoded xsec validation repeat at parent/request/child boundaries. / 精确 note/creator URL、身份及解码后 xsec 校验在父/request/child 边界重复执行。 |
| Exact fallback and override / 精确 fallback 与覆盖 | `PASS` | Exact Subscription creator secret and bounded `max_items`; explicit detail wins with no creator-secret resolution. / 精确 Subscription 作者 secret 与有界 `max_items`；显式 detail 优先且不解析作者 secret。 |
| Static target and composition / 静态目标与组合 | `PASS` | One ordinary IMAGE/GALLERY all-IMAGE target reaches DEFAULT HTTP, image validation, SHA-256 archives and idempotent Emby output; replay adds no work. / 唯一普通 IMAGE/GALLERY 全 IMAGE 目标贯穿 DEFAULT HTTP、图片校验、SHA-256 归档及幂等 Emby 输出；重放不新增工作。 |
| Preflight and taxonomy / 前置校验与分类 | `PASS` | Missing/damaged VERIFIED repair preflights before mutation; valid replay is zero-secret; fixed causes remain distinct; non-XHS option use is rejected. / VERIFIED 缺失/损坏修复在变更前 preflight；有效重放零 secret；固定 cause 保持区分；非小红书选项使用被拒绝。 |
| Durable raw and secret sinks / 持久 raw 与密钥落点 | `PASS` | Field-specific authority/query removal preserves accepted value shapes and retains no execution marker. / 按字段执行的权限/query 清理保持已接受值形状，且不保留执行 marker。 |

## Six review repairs / 六类审查修复

1. Unique ordinary-static creator result gate. / 唯一普通静态 creator 结果门。
2. Duplicate target rejection before Asset selection. / Asset 选择前拒绝重复目标。
3. VERIFIED archive repair preflight before quarantine/reset with valid replay zero-secret. / VERIFIED 归档修复在 quarantine/reset 前 preflight，有效重放零 secret。
4. Dedicated pipeline error taxonomy and scheduler vocabulary. / 专用 pipeline 错误分类与 scheduler 词汇表。
5. Durable raw shape preservation plus field-specific authority/query removal. / 持久 raw 形状保持及按字段执行的权限/query 清理。
6. Non-XHS CLI use of the XHS option rejected. / 拒绝非小红书 CLI 使用小红书选项。

## Test and quality gates / 测试与质量门禁

| Check / 检查 | Command / 命令 | Result / 结果 |
| --- | --- | --- |
| Focused nine-file pytest / 九文件专项 pytest | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_asset_download_orchestration.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_pipeline_runtime.py tests/integration/test_pipeline_worker.py tests/integration/test_xhs_creator_authority_pipeline.py tests/unit/test_cli.py tests/unit/test_mediacrawler_refresh.py` | `PASS` — `266 passed in 56.90s` |
| Post-format related / 格式后相关 | `uv run pytest -q tests/unit/test_cli.py tests/integration/test_pipeline_runtime.py` | `PASS` — `89 passed in 13.74s` |
| Complete suite / 完整套件 | `uv run pytest -q` | `PASS` — `1298 passed, 1 skipped in 365.73s`; only skip: Windows POSIX mode-bit / 唯一跳过：Windows POSIX mode-bit |
| Final pipeline/worker / 最终 pipeline/worker | `uv run pytest -q tests/integration/test_pipeline_runtime.py tests/integration/test_pipeline_worker.py` | `PASS` — `52 passed in 4.57s` |
| Ruff / Ruff | `uv run ruff check .` | `PASS` |
| Format / 格式 | `uv run ruff format --check .` | `PASS` — 234 files |
| Strict mypy / 严格 mypy | `uv run mypy src/media_sync` | `PASS` — 79 sources |
| Compileall / 字节编译 | `uv run python -m compileall -q src/media_sync` | `PASS` |
| Upstream locks / 上游锁 | `uv run python scripts/check_upstreams.py` | `PASS` — 2 entries |
| Build / 构建 | `uv build` | `PASS` — 2 artifacts |
| Diff checks / Diff 检查 | `git diff --check` and `git diff --cached --check` | `PASS` |
| Post-edit docs / 编辑后文档 | `uv run python scripts/check_docs.py` | `PASS` — 84 Markdown files checked / 检查 84 个 Markdown 文件 |

No coverage run is claimed. / 不宣称运行过 coverage。

## Retained/Git audit / 保留产物与 Git 审计

`tracked=252`; `untracked=0`; `tracked_forbidden=0`; `suspicious_untracked=0`; `runtime_and_build_files=914`; `runtime_execution0017_marker_hits=0`; `sentinel_roots_preserved=2/2`; MediaCrawler dirty paths `0`; bili-sync-up dirty paths `0`.

## Live qualification / 真人在线验收

| Row / 验收行 | Result / 结果 |
| --- | --- |
| Real XHS QR/Cookie login / 真人小红书 QR/Cookie 登录 | `NOT_RUN` |
| Real creator/feed/detail lookup / 真实 creator/feed/detail 查找 | `NOT_RUN` |
| Real XHS CDN image bytes / 真实小红书 CDN 图片字节 | `NOT_RUN` |
| Real Emby/Jellyfin scan/playback / 真实 Emby/Jellyfin 扫描/播放 | `NOT_RUN` |

Offline mocks do not imply these rows. Execution 0017 is complete, while automatic XHS video/mixed/dynamic/expiry recovery, remaining platform shapes and the broader user goal remain active work. / 离线 mock 不代表这些行通过。Execution 0017 已完成，但小红书自动视频/混合/动态/权限过期恢复、其余平台形状及更大的用户目标仍需继续推进。
