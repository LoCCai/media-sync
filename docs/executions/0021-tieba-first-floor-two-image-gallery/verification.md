# Execution 0021 verification / 执行 0021 验证记录

- Status / 状态：Frozen offline scope passes all final gates; authenticated/live qualification `NOT_RUN` / 冻结离线范围通过全部最终门禁；登录/现网验收 `NOT_RUN`
- Date / 日期：2026-09-02
- Predecessor / 前置：`e5d871050cdf25da1a51e2f057ba317dea2cffb1`
- Plan commit / 计划提交：`5095ed6e803a8a2f0a3134e756dd3e101fef10bd`
- Implementation commit / 实现提交：`e0fb8d572c8f5535a5495c2dfbf5b9cdf78461e7`

## Baseline / 前置基线

| Check / 检查 | Result / 结果 |
| --- | --- |
| Execution 0020 focused regression / Execution 0020 专项回归 | `PASS — 368 passed in 41.18s` |
| Execution 0020 complete suite / Execution 0020 完整套件 | `PASS — 1650 passed, 1 skipped in 310.82s` |
| Quality/build/docs/upstreams/audit / 质量/构建/文档/上游/审计 | `PASS` |
| Real two-image response-shape observation / 真实双图响应形状观察 | `PASS as transient bounded evidence only / 仅作为瞬态有界证据通过` — no body or signed value retained / 未保留正文或签名值 |

## Implemented evidence / 已实现证据

| Scope / 范围 | Result / 结果 |
| --- | --- |
| Exact-two-image capture and single-image compatibility / 精确双图捕获与单图兼容 | `PASS` — separate v2 ordered list; v1 string unchanged; dual claims, duplicate durable identity and three-or-more images rejected / 独立 v2 有序列表；v1 字符串不变；双重声明、重复持久身份及三张以上拒绝 |
| Locked loss boundary and concurrency / 锁定丢失边界与并发 | `PASS` — pinned extractor still discards both locators; exact-object gather-child → parent-store carry and peer isolation proven / 锁定 extractor 仍丢失两个 locator；精确对象跨 gather-child → parent-store 携带及并发隔离已证明 |
| Ordered ARTICLE + two IMAGE normalization / 有序 ARTICLE + 两项 IMAGE 归一化 | `PASS` — exact `<note_id>:image:0/1`; both private fields recursively absent; only distinct query-free hints durable / 精确 `<note_id>:image:0/1`；两个私有字段递归移除；只保留互异无 query hint |
| Position 0/1 detail refresh and drift rejection / Position 0/1 详情刷新与漂移拒绝 | `PASS` — full persisted gallery is bound into refresh context; complete current order/hints required; missing, reorder, replacement and dual claim rejected / 完整持久 gallery 绑定到刷新上下文；要求当前完整顺序/hint；缺图、重排、替换及双重声明拒绝 |
| Credential-free transfer and static gates / 无凭据传输与静态门 | `PASS` — both URLs use DEFAULT profile without Cookie/Authorization/Referer/Origin; production Tieba static gate accepts tested JPEG/PNG / 两个 URL 均使用无 Cookie/Authorization/Referer/Origin 的 DEFAULT profile；生产贴吧静态门接受已测 JPEG/PNG |
| Two-image SQLite/archive/Emby composition / 双图 SQLite/归档/Emby 组合 | `PASS` — two exact downloads and SHA-256 archives; poster/backdrop/two gallery files/body/NFO/source; query-only replay adds zero detail/DNS/HTTP/archive/export work / 两次精确下载与 SHA-256 归档；poster/backdrop/两项 gallery/body/NFO/source；query 重放不新增 detail/DNS/HTTP/archive/export 工作 |
| Retained-state boundary / 保留状态边界 | `PASS` — SQLite/runtime/work/archive/export/library whole-tree assertions retain neither private field nor any `tbpicau` token/value / SQLite/runtime/work/archive/export/library 整树断言不保留私有字段或任何 `tbpicau` token/value |

## Test and quality gates / 测试与质量门禁

| Check / 检查 | Command / 命令 | Result / 结果 |
| --- | --- | --- |
| Focused implementation regression / 实现专项回归 | `uv run pytest -q tests/unit/test_tieba_media.py tests/contract/test_tieba_upstream_first_floor_media.py tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_tieba_first_floor_image_pipeline.py tests/integration/test_asset_download_orchestration.py` | `PASS — 413 passed in 44.50s` |
| Locked Tieba source contract / 锁定贴吧源码合约 | `uv run pytest -q tests/contract/test_tieba_upstream_first_floor_media.py` | `PASS — 6 passed in 3.42s` |
| Two-image SQLite→Emby composition / 双图 SQLite→Emby 组合 | `uv run pytest -q tests/integration/test_tieba_first_floor_image_pipeline.py` | `PASS — 2 passed in 1.94s` |
| Complete suite / 完整套件 | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run pytest -q -p no:cacheprovider` | `PASS — 1668 passed, 1 skipped in 314.72s`; skip is the Windows-inapplicable POSIX mode-bit boundary / 跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff and format / Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 262 files formatted / 全部通过；262 个文件格式正确` |
| Strict mypy / 严格 mypy | `uv run mypy --strict src` | `PASS — no issues in 82 source files / 82 个源码文件无问题` |
| Compileall and build / 字节编译与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — wheel and source distribution built / wheel 与源码包构建成功` |
| Documentation and upstream locks / 文档与上游锁 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 100 Markdown files; 2 locked checkouts / 100 份 Markdown；2 个锁定 checkout` |
| Git/upstream audit / Git/上游审计 | explicit status, tracked/untracked/runtime/upstream and diff checks / 显式状态、跟踪/未跟踪/runtime/upstream 与 diff 检查 | `PASS — tracked 280; untracked 0; tracked runtime/upstream 0; both upstream dirty counts 0 / 跟踪 280；未跟踪 0；跟踪 runtime/upstream 0；两个上游 dirty 数均为 0` |

No coverage run is claimed. / 不宣称运行过 coverage。

## Git reconciliation / Git 核对

Implementation `e0fb8d572c8f5535a5495c2dfbf5b9cdf78461e7` is reconciled across local `main`, `origin/main` and GitHub. The commit containing this record is the bilingual documentation closeout; its self-referential SHA is intentionally left to Git history. / 实现 `e0fb8d572c8f5535a5495c2dfbf5b9cdf78461e7` 已在本地 `main`、`origin/main` 与 GitHub 间核对一致。包含本记录的提交即双语文档收尾；其自引用 SHA 有意只保留在 Git 历史中。

## Live qualification / 登录与现网验收

| Row / 验收行 | Result / 结果 |
| --- | --- |
| Real Tieba QR/Cookie login / 真人贴吧 QR/Cookie 登录 | `NOT_RUN` |
| Authenticated creator/detail gallery / 登录态作者/详情 gallery | `NOT_RUN` |
| Future real CDN byte/redirect behavior / 未来真实 CDN 字节/重定向行为 | `NOT_RUN` |
| Real Emby/Jellyfin scan/display / 真实 Emby/Jellyfin 扫描/展示 | `NOT_RUN` |

Offline evidence cannot imply these rows. Three-or-more images and complete Tieba gallery/media support also remain outside this execution. / 离线证据不能代表上述真人行通过；三张及以上图片与完整贴吧 gallery/媒体支持也不在本执行范围内。
