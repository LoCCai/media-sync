# Execution 0022 verification / 执行 0022 验证记录

- Status / 状态：Frozen offline scope passes all final gates; authenticated/live qualification `NOT_RUN` / 冻结离线范围通过全部最终门禁；登录/现网验收 `NOT_RUN`
- Date / 日期：2026-09-02
- Predecessor / 前置：`817875bdd1902f54c72397fa7da46359fbe33207`
- Plan commit / 计划提交：`fbcb7cf5c642fc9da210faa5d92b6886b350a9b8`
- Implementation commit / 实现提交：`b6d03aa1c6705e52c2e47c63086a5b7200c208e7`

## Baseline / 前置基线

| Check / 检查 | Result / 结果 |
| --- | --- |
| Execution 0021 focused regression / Execution 0021 专项回归 | `PASS — 413 passed in 44.50s` |
| Execution 0021 complete suite / Execution 0021 完整套件 | `PASS — 1668 passed, 1 skipped in 314.72s` |
| Quality/build/docs/upstreams/audit / 质量/构建/文档/上游/审计 | `PASS` |
| Local/tracking/GitHub reconciliation / 本地/tracking/GitHub 核对 | `PASS — 817875bdd1902f54c72397fa7da46359fbe33207` |

## Implemented evidence / 已实现证据

| Scope / 范围 | Result / 结果 |
| --- | --- |
| v3 capture and compatibility / v3 捕获与兼容 | `PASS` for 3 and 64 ordered images; reject 65, duplicates, malformed items and multi-version claims; retain exact v1/v2 behavior / 3 与 64 张有序图片通过；拒绝 65 张、重复、畸形项与多版本声明；保留精确 v1/v2 行为 |
| Ordered normalization and storage / 有序归一化与存储 | `PASS` for N stable remote IDs/positions, query-free durable hints and recursive private-field removal / N 项稳定 remote ID/position、无 query 持久 hint 与递归私有字段移除通过 |
| Complete-gallery refresh / 完整 gallery 刷新 | `PASS` for every valid position; reject missing, added, reordered, replaced and duplicated galleries / 每个有效 position 通过；拒绝缺失、新增、重排、替换与重复 gallery |
| Three-image archive/Emby composition / 三图归档/Emby 组合 | `PASS` for distinct static bytes, SHA-256 archives, poster/backdrop/three gallery files/body/NFO/source and query-only zero-work replay / 不同静态字节、SHA-256 归档、poster/backdrop/三项 gallery/body/NFO/source 与 query-only 零工作重放通过 |
| Retained-state boundary / 保留状态边界 | `PASS` with no private v1/v2/v3 field or signed-query token/value in retained trees / 保留树中不存在 v1/v2/v3 私有字段或签名 query token/value |

## Test and quality gates / 测试与质量门禁

| Check / 检查 | Command / 命令 | Result / 结果 |
| --- | --- | --- |
| Focused implementation regression / 实现专项回归 | `uv run pytest -q tests/unit/test_tieba_media.py tests/contract/test_tieba_upstream_first_floor_media.py tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_tieba_first_floor_image_pipeline.py tests/integration/test_asset_download_orchestration.py` | `PASS — 433 passed in 48.91s` |
| Bounded Tieba SQLite→Emby compositions / 有界贴吧 SQLite→Emby 组合 | `uv run pytest -q tests/integration/test_tieba_first_floor_image_pipeline.py` | `PASS — 3 passed in 2.88s` |
| Complete suite / 完整套件 | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run pytest -q -p no:cacheprovider` | `PASS — 1688 passed, 1 skipped in 321.22s`; skip is the Windows-inapplicable POSIX mode-bit boundary / 跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff and format / Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 266 files formatted / 全部通过；266 个文件格式正确` |
| Strict mypy / 严格 mypy | `uv run mypy --strict src` | `PASS — no issues in 82 source files / 82 个源码文件无问题` |
| Compileall and build / 字节编译与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — wheel and source distribution built / wheel 与源码包构建成功` |
| Documentation and upstream locks / 文档与上游锁 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 104 Markdown files; 2 locked checkouts / 104 份 Markdown；2 个锁定 checkout` |
| Git/upstream audit / Git/上游审计 | explicit status, tracked/runtime/upstream and diff checks / 显式状态、跟踪/runtime/upstream 与 diff 检查 | `PASS — tracked 284; untracked 0; tracked runtime/upstream 0; both upstream dirty counts 0 / 跟踪 284；未跟踪 0；跟踪 runtime/upstream 0；两个上游 dirty 数均为 0` |

No coverage run is claimed. / 不宣称运行过 coverage。

## Git reconciliation / Git 核对

Implementation `b6d03aa1c6705e52c2e47c63086a5b7200c208e7` is reconciled across local `main`, `origin/main` and GitHub. The commit containing this record is the bilingual documentation closeout; its self-referential SHA is intentionally left to Git history. / 实现 `b6d03aa1c6705e52c2e47c63086a5b7200c208e7` 已在本地 `main`、`origin/main` 与 GitHub 间核对一致。包含本记录的提交即双语文档收尾；其自引用 SHA 有意只保留在 Git 历史中。

## Live qualification / 登录与现网验收

| Row / 验收行 | Result / 结果 |
| --- | --- |
| Real Tieba QR/Cookie login / 真人贴吧 QR/Cookie 登录 | `NOT_RUN` |
| Authenticated creator/detail gallery / 登录态作者/详情 gallery | `NOT_RUN` |
| Real CDN byte/redirect behavior / 真实 CDN 字节/重定向行为 | `NOT_RUN` |
| Real Emby/Jellyfin scan/display / 真实 Emby/Jellyfin 扫描/展示 | `NOT_RUN` |

Offline evidence cannot imply these rows or complete Tieba media support. / 离线证据不能代表上述真人行或完整贴吧媒体支持通过。
