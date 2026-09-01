# Execution 0026 verification / 执行 0026 验证记录

- Status / 状态：Frozen offline scope passes all final gates; authenticated/live qualification `NOT_RUN` / 冻结离线范围通过全部最终门禁；登录/现网验收 `NOT_RUN`
- Date / 日期：2026-09-02
- Predecessor / 前置：`7cb84fc6c93b832492b95513d9cb6a9708ee6cc9`
- Plan commit / 计划提交：`0694934bc9230151a85c040a061d6e704dffc4fc`
- Implementation commit / 实现提交：`190488f77d1704492cc148b890d6f9ae16d84f84`

## Baseline / 前置基线

| Check / 检查 | Result / 结果 |
| --- | --- |
| Execution 0025 focused regression / Execution 0025 专项回归 | `PASS — 466 passed in 66.96s` |
| Execution 0025 complete suite / Execution 0025 完整套件 | `PASS — 1790 passed, 1 skipped in 331.33s` |
| Production backup-path closeout rerun / 生产备用路径收尾复验 | `PASS — 1 passed in 1.74s` |
| Documentation and upstream locks / 文档与上游锁 | `PASS — 116 Markdown files; 2 locked clean checkouts / 116 份 Markdown；2 个锁定且干净的 checkout` |
| Repository audit / 仓库审计 | `PASS — tracked 304; untracked 0; tracked runtime/upstream 0 / 跟踪 304；未跟踪 0；跟踪 runtime/upstream 0` |
| Local/tracking/GitHub reconciliation / 本地/tracking/GitHub 核对 | `PASS — 7cb84fc6c93b832492b95513d9cb6a9708ee6cc9` |

## Implemented evidence / 已实现证据

| Scope / 范围 | Result / 结果 |
| --- | --- |
| Strict protocol-v6 parsing / 严格 v6 协议解析 | `PASS` — exactly one progressive `durl` accepts one primary plus equivalent `backup_url`/`backupUrl` aliases and at most eight validated distinct backups; malformed, conflicting, duplicate, primary-equal and over-bound candidates fail closed / 精确一个 progressive `durl` 接受一个主地址、等价 `backup_url`/`backupUrl` 别名及最多八个已校验互异备用地址；畸形、冲突、重复、与主地址相同及超限候选均关闭失败 |
| Private bridge compatibility / 私有桥接兼容 | `PASS` — the single-page private backup field and optional multipart `backup_urls` reach runtime `ResolvedLocator`; historical primary-only payloads remain accepted / 单 P 私有备用字段与多分 P 可选 `backup_urls` 可到达运行时 `ResolvedLocator`；历史仅主地址 payload 继续接受 |
| Shared candidate order / 共享候选顺序 | `PASS` — ordinary progressive and DASH locators share one primary-first pass under the existing asset lock, deadline, byte caps and restart budget; primary success touches no backup DNS/HTTP / 普通 progressive 与 DASH locator 共用既有 Asset 锁、截止时间、字节上限及 restart 预算下的主地址优先轮次；主地址成功时备用 DNS/HTTP 为零 |
| Eligible and immediate failures / 可切换与立即失败 | `PASS` — DNS, timeout, transport, interruption, HTTP and Range incompatibility may advance; network-policy, redirect/header/encoding, chunk/size, filesystem, probe, mux, archive and publication failures remain immediate / DNS、timeout、传输、中断、HTTP 与 Range 不兼容可推进；网络策略、重定向/header/encoding、chunk/size、文件系统、探测、合并、归档及发布失败继续立即关闭 |
| Strict partial continuity / 严格 partial 连续性 | `PASS` — cross-candidate append requires exact offset, total length, validator type and value; mixed failures preserve valid partials, and bounded discard/restart occurs only after the complete candidate pass rejects the partial / 跨候选追加要求 offset、总长度、validator 类型和值完全一致；混合失败保留合法 partial，只有完整候选轮次拒绝 partial 后才有界丢弃/restart |
| Adapter refresh semantics / Adapter 刷新语义 | `PASS` — one adapter pass containing only `401`/`403` re-resolves detail once; a second all-auth pass returns `locator_refresh_auth_expired`; mixed/non-auth exhaustion and direct locators do not refresh / adapter 一轮仅含 `401`/`403` 时重解析详情一次；第二轮仍全鉴权失败返回 `locator_refresh_auth_expired`；混合/非鉴权穷尽与 direct locator 不刷新 |
| Ephemeral boundary / 瞬态边界 | `PASS` — primary/backup signed values and all private fields are recursively absent from retained SQLite, Job, runtime, work, archive, export and operator evidence / 主/备用签名值与全部私有字段递归地不存在于保留 SQLite、Job、runtime、work、归档、导出及运维证据中 |
| Single-page composition / 单 P 组合 | `PASS` — SQLite → exact-CID detail → primary `503` → backup bytes → controlled probe → SHA-256 archive → Emby MP4/NFO/source succeeds; replay performs zero new detail/DNS/HTTP/probe/archive/export work / SQLite → 精确 CID 详情 → 主地址 `503` → 备用字节 → 受控探测 → SHA-256 归档 → Emby MP4/NFO/source 成功；重放不新增 detail/DNS/HTTP/probe/archive/export 工作 |
| Multipart composition / 多分 P 组合 | `PASS` — all three page primaries return `503`, ordered backups supply distinct bytes, primary/part publication succeeds and replay is zero-work / 三个分 P 的主地址均返回 `503`，有序备用地址提供互异字节，主媒体/part 发布成功且重放零工作 |
| Compatibility / 兼容 | `PASS` — no-backup progressive, DASH backup failover, static media, recovery and the twelve frozen media-shape count remain green / 无备用 progressive、DASH 备用故障切换、静态媒体、恢复路径与十二个冻结媒体形状计数保持通过 |

## Test and quality gates / 测试与质量门禁

| Check / 检查 | Command / 命令 | Result / 结果 |
| --- | --- | --- |
| Focused implementation regression / 实现专项回归 | `uv run pytest tests/unit/test_media_locator.py tests/unit/test_mediacrawler_refresh.py tests/unit/test_media_mux.py tests/unit/test_media_dash_downloader.py tests/unit/test_media_downloader.py tests/unit/test_cli.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_asset_download_orchestration.py tests/integration/test_pipeline_runtime.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_bilibili_multipart_progressive_pipeline.py tests/integration/test_bilibili_dash_pipeline.py -q` | `PASS — 490 passed in 73.31s` |
| Single-page progressive backup → Emby / 单 P progressive 备用 → Emby | `uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py` | `PASS — 1 passed in 1.45s` on the documentation-closeout rerun (`1.64s` on the implementation run) / 文档收尾复验 `1 passed in 1.45s`（实现运行 `1.64s`） |
| Multipart progressive backup → Emby / 多分 P progressive 备用 → Emby | `uv run pytest -q tests/integration/test_bilibili_multipart_progressive_pipeline.py` | `PASS — 1 passed in 1.70s` on the documentation-closeout rerun (`1.95s` on the implementation run) / 文档收尾复验 `1 passed in 1.70s`（实现运行 `1.95s`） |
| DASH failover compatibility / DASH 故障切换兼容 | `uv run pytest -q tests/integration/test_bilibili_dash_pipeline.py` | `PASS — 1 passed in 1.87s` on the documentation-closeout rerun (`2.11s` on the implementation run) / 文档收尾复验 `1 passed in 1.87s`（实现运行 `2.11s`） |
| Complete suite / 完整套件 | `uv run pytest -q` | `PASS — 1814 passed, 1 skipped in 342.33s`; skip is the Windows-inapplicable POSIX mode-bit boundary / 跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff and format / Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 290 files already formatted / 全部通过；290 个文件格式正确` |
| Strict mypy / 严格 mypy | `uv run mypy --strict src` | `PASS — no issues in 84 source files / 84 个源码文件无问题` |
| Compileall and build / 字节编译与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — wheel and source distribution built / wheel 与源码包构建成功` |
| Documentation and upstream locks / 文档与上游锁 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 120 Markdown files; 2 locked checkouts / 120 份 Markdown；2 个锁定 checkout` |
| Git/upstream/diff audit / Git/上游/diff 审计 | explicit status, tracked/runtime/upstream and diff checks / 显式状态、跟踪/runtime/upstream 与 diff 检查 | `PASS — tracked 308; untracked 0; tracked runtime/upstream/dist 0; upstream diff 0; both upstream dirty counts 0 / 跟踪 308；未跟踪 0；跟踪 runtime/upstream/dist 0；上游 diff 为 0；两个上游 dirty 数均为 0` |

No coverage run is claimed. / 不宣称运行过 coverage。

## Git reconciliation / Git 核对

Plan `0694934bc9230151a85c040a061d6e704dffc4fc` and implementation `190488f77d1704492cc148b890d6f9ae16d84f84` are pushed and reconciled across local `main` and `origin/main`. The commit containing this record is the bilingual documentation closeout; its self-referential SHA is intentionally left to Git history. / 计划 `0694934bc9230151a85c040a061d6e704dffc4fc` 与实现 `190488f77d1704492cc148b890d6f9ae16d84f84` 已推送并在本地 `main` 与 `origin/main` 间核对一致。包含本记录的提交即双语文档收尾；其自引用 SHA 有意只保留在 Git 历史中。

## Live qualification / 登录与现网验收

| Row / 验收行 | Result / 结果 |
| --- | --- |
| Real Bilibili QR/Cookie login / 真人 Bilibili QR/Cookie 登录 | `NOT_RUN` |
| Authenticated progressive detail/play API / 登录态 progressive 详情/播放 API | `NOT_RUN` |
| Real primary/backup bilivideo CDN behavior / 真实主/备用 bilivideo CDN 行为 | `NOT_RUN` |
| Real progressive bytes with production ffprobe / 真实 progressive 字节与生产 ffprobe | `NOT_RUN` |
| Real Emby/Jellyfin scan and playback / 真实 Emby/Jellyfin 扫描与播放 | `NOT_RUN` |

Offline evidence cannot imply these rows, segmented `durl`, FLV, CDN ranking/racing/cache or complete Bilibili support. / 离线证据不能代表上述真人行、分段 `durl`、FLV、CDN 排序/竞速/缓存或完整 Bilibili 支持通过。
