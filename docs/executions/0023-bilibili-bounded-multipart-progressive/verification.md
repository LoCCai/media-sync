# Execution 0023 verification / 执行 0023 验证记录

- Status / 状态：Frozen offline scope passes all final gates; authenticated/live qualification `NOT_RUN` / 冻结离线范围通过全部最终门禁；登录/现网验收 `NOT_RUN`
- Date / 日期：2026-09-02
- Predecessor / 前置：`27e45c89f20e8eb6bc871ab1505fe25167b70ae3`
- Plan commit / 计划提交：`bd45478b28cc61a7f35b6211faf3a0fc1eb94138`
- Implementation commit / 实现提交：`24fd41c600eb30fb2df22079e3cf52778589959e`

## Baseline / 前置基线

| Check / 检查 | Result / 结果 |
| --- | --- |
| Execution 0022 focused regression / Execution 0022 专项回归 | `PASS — 433 passed in 48.91s` |
| Execution 0022 complete suite / Execution 0022 完整套件 | `PASS — 1688 passed, 1 skipped in 321.22s` |
| Quality/build/docs/upstreams/audit / 质量/构建/文档/上游/审计 | `PASS` |
| Local/tracking/GitHub reconciliation / 本地/tracking/GitHub 核对 | `PASS — 27e45c89f20e8eb6bc871ab1505fe25167b70ae3` |

## Implemented evidence / 已实现证据

| Scope / 范围 | Result / 结果 |
| --- | --- |
| Page capture / 分 P 捕获 | `PASS` for 1, 2, 3 and 64 canonical ordered pages; reject 65, malformed, non-contiguous and duplicate-CID declarations / 1、2、3 与 64 个规范有序分 P 通过；拒绝 65、畸形、不连续与重复 CID 声明 |
| Stable normalization / 稳定归一化 | `PASS` for exact `<aid>:video:0` single-page compatibility and ordered `<aid>:video:cid:<cid>` locator-only Assets for 2–64 pages / 精确 `<aid>:video:0` 单 P 兼容与 2–64 分 P 有序 `<aid>:video:cid:<cid>`、仅 locator Asset 通过 |
| Exact refresh / 精确刷新 | `PASS` for protocol v4 target-CID calls and complete sibling binding; reject missing, added, reordered, replaced, duplicated and malformed tuples / 协议 v4 目标 CID 调用与完整兄弟绑定通过；拒绝缺失、新增、重排、替换、重复与畸形元组 |
| Archive/Emby composition / 归档/Emby 组合 | `PASS` for three distinct downloads and SHA-256 archives, deterministic primary/two-part/NFO/source output and query-only zero-work replay / 三份不同下载与 SHA-256 归档、确定性主媒体/两个 part/NFO/source 输出及 query-only 零工作重放通过 |
| Retained-state boundary / 保留状态边界 | `PASS` with no private page/play field or signed locator in retained SQLite/runtime/archive/export trees / 保留 SQLite/runtime/归档/导出树中无私有分 P/播放字段或签名 locator |

## Test and quality gates / 测试与质量门禁

| Check / 检查 | Command / 命令 | Result / 结果 |
| --- | --- | --- |
| Focused implementation regression / 实现专项回归 | `uv run pytest -q tests/unit/test_bilibili_media.py tests/contract/test_bilibili_upstream_pages.py tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_bilibili_multipart_progressive_pipeline.py tests/integration/test_asset_download_orchestration.py tests/integration/test_emby_application.py` | `PASS — 436 passed in 53.96s` |
| Three-page SQLite→Emby composition / 三分 P SQLite→Emby 组合 | `uv run pytest -q tests/integration/test_bilibili_multipart_progressive_pipeline.py` | `PASS — 1 passed in 1.49s`; distinct bytes, targeted detail/profile calls, three archives, primary/two-part output and zero-work replay / 不同字节、定向详情/profile 调用、三份归档、主媒体/两个 part 输出及零工作重放通过 |
| Complete suite / 完整套件 | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run pytest -q -p no:cacheprovider` | `PASS — 1739 passed, 1 skipped in 321.25s`; skip is the Windows-inapplicable POSIX mode-bit boundary / 跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff and format / Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 274 files already formatted / 全部通过；274 个文件格式正确` |
| Strict mypy / 严格 mypy | `uv run mypy --strict src` | `PASS — no issues in 83 source files / 83 个源码文件无问题` |
| Compileall and build / 字节编译与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — wheel and source distribution built / wheel 与源码包构建成功` |
| Documentation and upstream locks / 文档与上游锁 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 108 Markdown files; 2 locked checkouts / 108 份 Markdown；2 个锁定 checkout` |
| Git/upstream audit / Git/上游审计 | explicit status, tracked/runtime/upstream and diff checks / 显式状态、跟踪/runtime/upstream 与 diff 检查 | `PASS — tracked 292; untracked 0; tracked runtime/upstream 0; both upstream dirty counts 0 / 跟踪 292；未跟踪 0；跟踪 runtime/upstream 0；两个上游 dirty 数均为 0` |

No coverage run is claimed. / 不宣称运行过 coverage。

## Git reconciliation / Git 核对

Implementation `24fd41c600eb30fb2df22079e3cf52778589959e` is reconciled across local `main`, `origin/main` and GitHub. The commit containing this record is the bilingual documentation closeout; its self-referential SHA is intentionally left to Git history. / 实现 `24fd41c600eb30fb2df22079e3cf52778589959e` 已在本地 `main`、`origin/main` 与 GitHub 间核对一致。包含本记录的提交即双语文档收尾；其自引用 SHA 有意只保留在 Git 历史中。

## Live qualification / 登录与现网验收

| Row / 验收行 | Result / 结果 |
| --- | --- |
| Real Bilibili QR/Cookie login / 真人 Bilibili QR/Cookie 登录 | `NOT_RUN` |
| Authenticated multi-P detail/play APIs / 登录态多分 P 详情/播放 API | `NOT_RUN` |
| Real bilivideo CDN behavior / 真实 bilivideo CDN 行为 | `NOT_RUN` |
| Real Emby/Jellyfin scan/display / 真实 Emby/Jellyfin 扫描/展示 | `NOT_RUN` |

Offline evidence cannot imply these rows or complete Bilibili media support. / 离线证据不能代表上述真人行或完整 Bilibili 媒体支持通过。
