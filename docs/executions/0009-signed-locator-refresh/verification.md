# Execution 0009 verification / 执行 0009 验证

- Verification state / 验证状态：`FUNCTION-FIRST MVP / PASSING OFFLINE FOCUSED GATES`
- Planning date / 计划日期：2026-08-30
- Network/account policy / 网络与账户策略：offline fake pinned-upstream modules, repository-owned local helpers and mock HTTP only; no browser connected to a platform, real credential, platform/CDN endpoint or Emby/Jellyfin server / 仅离线 fake 锁定上游模块、仓库自有本地 helper 与 mock HTTP；不使用连接平台的浏览器、真实凭据、平台/CDN 端点或 Emby/Jellyfin 服务器
- Implementation state / 实现状态：`MVP IMPLEMENTED` — provenance, cleanup, detail refresh, lazy runtime and CLI wiring verified offline / 来源、清理、detail 刷新、惰性运行时及 CLI 接线已完成离线验证

This file preserves the historical pause evidence and current results. Migration, ingestion, cleanup, functional locator refresh and CLI wiring are implemented; full-suite/build, retained-sentinel and live rows remain open. / 本文件同时保留历史暂停证据与当前结果；migration、导入、清理、功能 locator refresh 及 CLI 接线已实现；完整套件/构建、留存哨兵及真人行仍待完成。

本文件是执行 0009 的冻结验证契约，不是实现证据。计划基线文档检查单独记录；在记录准确命令与结果前，不提升任何 migration、刷新、清理、签名哨兵或真人行。

## Planning-baseline checks / 计划基线检查

The following rows qualify only the committed goal/plan/progress/verification baseline. They do not execute behavior.

下列各行只验收已提交的 goal/plan/progress/verification 基线，不执行行为。

| Check / 检查 | Exact command / 准确命令 | Result / 结果 |
| --- | --- | --- |
| Documentation links / 文档链接 | `uv run python scripts/check_docs.py` | PASS — `Documentation links OK (52 Markdown files checked).` / 通过 |
| Locked upstreams / 锁定上游 | `uv run python scripts/check_upstreams.py` | PASS — `Upstreams OK (2 locked checkouts verified).` / 通过 |
| Patch whitespace / 补丁空白 | `git diff --check` | PASS — exit `0`, no output / 通过 — 退出码 `0`，无输出 |

## Executed pause-checkpoint checks / 已执行的暂停检查点验证

| Check / 检查 | Exact command / 准确命令 | Result / 结果 |
| --- | --- | --- |
| Modified-source lint / 修改源码 lint | `uv run ruff check src/media_sync/infrastructure/db/__init__.py src/media_sync/infrastructure/db/models.py src/media_sync/infrastructure/db/repositories.py src/media_sync/infrastructure/db/migrations/versions/0005_asset_refresh_sources.py src/media_sync/scheduler/mediacrawler_handler.py` | PASS — `All checks passed!` |
| Focused cleanup truth / cleanup 事实专项 | `uv run pytest -q tests/integration/test_mediacrawler_scheduler_handler.py::test_empty_normalized_delta_is_a_successful_guarded_checkpoint tests/integration/test_mediacrawler_scheduler_handler.py::test_committed_sync_run_truth_wins_over_invalid_returned_summary` | PASS — `2 passed in 1.21s` |
| Strict types / 严格类型 | `uv run mypy src/media_sync` | FAIL — 3 errors at handler lines 727/730/731: `SyncRun | None` assigned to `UUID | None`, then UUID accessed as `subscription_id` and `attempt` / 失败，共 3 项 |
| Migration focused nodes / migration 专项节点 | `uv run pytest -q tests/integration/test_database.py::test_alembic_upgrade_matches_metadata_and_downgrades tests/integration/test_packaged_migrations.py::test_programmatic_upgrade_uses_packaged_resources_and_handles_percent_path` | FAIL — `2 failed`; `DOMAIN_TABLES` omits `asset_refresh_sources`, and tests/CLI still hard-code head `0004_scheduler_control_plane` instead of `0005_asset_refresh_sources` / 失败，共 2 项 |
| Full handler file / handler 整文件 | `uv run pytest -q tests/integration/test_mediacrawler_scheduler_handler.py` | FAIL — `9 failed, 43 passed in 25.27s`; seven platform cases still expect successful attempt roots retained, heartbeat reads a now-cleaned snapshot, and valid recovery expects the receipt retained / 旧契约尚未同步新清理语义 |
| Patch whitespace / 补丁空白 | `git diff --check` | PASS — exit `0`, no output / 通过 |

The full pytest/coverage suite, build, wheel smoke, signed sentinel and authoritative retained gate were deliberately not run before pausing. The 0009 retained root was not created; the 0007/0008 retained roots were not touched. / 暂停前有意未运行完整 pytest/coverage、构建、wheel smoke、签名哨兵及权威留存门禁；未创建 0009 留存根，也未触碰 0007/0008 留存根。

## Resumed tranche checks / 恢复批次验证

| Check / 检查 | Exact command / 准确命令 | Result / 结果 |
| --- | --- | --- |
| Merged lint / 合并 lint | `uv run ruff check <12 changed migration/ingestion/cleanup source and test files>` | PASS — `All checks passed!` |
| Strict types / 严格类型 | `uv run mypy src/media_sync` | PASS — `Success: no issues found in 65 source files` |
| Migration/ingestion/cleanup regression / migration、导入与清理回归 | `uv run pytest -q <4 migration nodes> tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_scheduler_handler.py tests/contract/test_mediacrawler_supervision.py` | PASS — `87 passed, 1 skipped in 44.51s`; the skip is the documented Windows/POSIX mode-bit boundary / 87 项通过、1 项 Windows 合理跳过 |
| Downloader re-resolution / 下载器重解析 | `uv run pytest -q tests/unit/test_media_downloader.py` and `uv run pytest -q tests/unit/test_download_application.py tests/integration/test_asset_download_orchestration.py` | PASS — `45 passed` plus `39 passed`; adapter refresh re-resolves once after 401/403 and direct locators remain unchanged / 45 项加 39 项通过 |
| Patch whitespace / 补丁空白 | `git diff --check` | PASS |

These checks qualify only the resumed provenance/cleanup tranche. They do not claim a working locator refresh, platform traffic, CDN download or Emby scan. / 这些检查只验收恢复后的来源/清理批次，不宣称 locator refresh、平台流量、CDN 下载或 Emby 扫描已可用。

## Function-first refresh checks / 功能优先刷新验证

| Check / 检查 | Exact command / 准确命令 | Result / 结果 |
| --- | --- | --- |
| Detail refresher unit + fake-child contract / detail refresher 单元与 fake-child 契约 | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py` | PASS — `20 passed` |
| Locator/normalizer/download regression / locator、normalizer 与下载回归 | `uv run pytest -q tests/unit/test_media_locator.py tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_asset_download_orchestration.py` | PASS — `111 passed` |
| Lazy exact-source runtime / 惰性精确来源运行时 | `uv run pytest -q tests/integration/test_mediacrawler_download_runtime.py` | PASS — `6 passed`; covers exact 1, 0/N, explicit mismatch, Cookie/policy context and zero-work construction / 覆盖精确单来源、0/N、显式不匹配、Cookie/策略上下文及构造零工作 |
| CLI asset download wiring / CLI 资产下载接线 | `uv run pytest -q tests/unit/test_cli.py -k "asset_download"` | PASS — `5 passed`; default-off, license block, ffprobe behavior and explicit lazy-refresher construction / 覆盖默认关闭、许可证拦截、ffprobe 行为及显式惰性 refresher 构造 |
| Changed-code lint / 修改代码 lint | `uv run ruff check src/media_sync/application/mediacrawler_download.py src/media_sync/integrations/mediacrawler/detail_runner.py src/media_sync/integrations/mediacrawler/refresh.py src/media_sync/interfaces/cli.py src/media_sync/media/errors.py tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/unit/test_cli.py` | PASS — `All checks passed!` |
| Strict types / 严格类型 | `uv run mypy src/media_sync` | PASS — `Success: no issues found in 70 source files` |

All rows above are offline. The fake child imports a repository-owned fake checkout; no real platform browser, credential, CDN request, Emby/Jellyfin request or Git network operation occurred. / 上述各行均为离线验证；fake child 只导入仓库测试创建的 fake checkout，未发生真人平台浏览器、真实凭据、CDN、Emby/Jellyfin 或 Git 网络操作。

## Planned behavior evidence / 计划行为证据

| Scope / 范围 | Required evidence / 必需证据 | Status / 状态 |
| --- | --- | --- |
| Migration and backfill / Migration 与 backfill | Head/round-trip/FKs/indexes; exact platform/author/adapter/stable-key unique inference; ambiguous/malformed/corrupt cases unbound; existing recovery identities preserved / head/往返/FK/索引、精确平台/作者/adapter/stable-key 唯一推断、歧义/畸形/损坏不绑定、保留恢复身份 | `PASS (focused)` |
| Ingestion observation / 导入 observation | Same transaction as Asset/checkpoint; wrong-run/cross-relation rollback; older-run replay cannot regress `(created_at,id)` last-run order/timestamps; multi-account; both replacement kinds advance generation; archive-reset eligibility / 同事务、错误关系回滚、旧 run 重放不回退 last-run 全序/时间、多账户、两类替换推进 generation、归档 reset 资格 | `PASS (focused)` |
| Source selector / 来源 selector | No-Job 0/1/N; existing-Job authority; explicit mismatch; shared-lock second filesystem-block check catches post-first-read writer before SecretResolver/claim/attach/prepare/spawn; no FS I/O in transaction / 两种来源模式；共用锁二次 block 检查在密钥/claim/attach/prepare/spawn 前拦截首次读取后的 writer；事务无 FS I/O | `PASS (MVP 0/1/N + explicit)` — immutable existing-Job binding and full TOCTOU hardening deferred / MVP 的 0/1/N 与显式选择通过；既有 Job 不可变绑定及完整 TOCTOU 强化后置 |
| Recovery ordering / 恢复顺序 | Read-only inspection zero-mutation; valid verified result needs no source/profile/credential; prepared recovery only bound CAS/finalization; both zero child/HTTP/new attempt / inspection 零变更、verified 无来源/profile/凭据、prepared 只做已绑定 CAS/收尾、两者无 child/HTTP/新 attempt | `NOT_RUN` |
| Job source/config binding / Job 来源与配置绑定 | Existing natural key and `run_id = NULL`; closed ID/platform/fingerprint payload omits observation kind; legacy-to-ingested upgrade preserves retry Job; retry/running/prepared source immutable; transactional config identities exact after secret resolution / 既有 natural key 与空 `run_id`、payload 不含 observation kind、audit kind 升级保留 retry Job、恢复来源不可变、事务复核配置 | `NOT_RUN` |
| Private child protocol / 私有 child 协议 | Dedicated pipe/handle; strict frame/error matrix; shared account lock spans child-tree join, HTTP/finalization and cleanup; every cleanup-block writer uses same fence; parent death/cancel / 专用 pipe、严格帧/错误矩阵、共用账户锁覆盖 child tree/HTTP/收尾/cleanup、所有 block writer 共用 fence、父死亡/取消 | `PASS (MVP fake child)` — bounded stdout frame, cleanup and process supervision pass; dedicated side pipe/full lock matrix deferred / 有界 stdout frame、清理及进程监督通过；专用旁路 pipe 与完整锁矩阵后置 |
| Platform selectors / 平台 selector | Exact stored hint required; XHS creator secret/author/token/source, 4 x 30/120-second bound and fixed invalid/expired/not-found/schema/timeout dispositions; DY/KS/Bili shapes; WB/Tieba/Zhihu no spawn / 要求精确 stored hint；XHS authority、数值边界及固定 disposition；其余形状与三个不 spawn 平台 | `PASS (MVP shapes)` — DY/KS/Bili and explicit XHS detail URL; automatic XHS feed lookup deferred / DY/KS/Bili 与显式 XHS 详情链接通过；XHS 自动 feed 查找后置 |
| Candidate identity / 候选身份 | Child validates semantics; full-request fingerprint binds response; query-free hint selects exactly one; same-kind ambiguity and position-only matching fail closed / child 验证语义、完整 request fingerprint 绑定响应、无 query hint 精确选一、同 kind 歧义与仅 position 匹配 fail closed | `NOT_RUN` |
| Downloader / 下载器 | Signed URL reaches mock HTTP only; one 401/403 re-resolve; direct unchanged; resume safe; metadata/redirect headers unchanged / 签名 URL 只到 mock HTTP、一次重解析、direct 不变、续传安全、metadata/header 不变 | `PASS (offline focused)` — functional MediaCrawler resolver wired / 功能性 MediaCrawler resolver 已接通 |
| Terminal cleanup / 终态清理 | Non-empty fresh/recovered sentinels and exact restart source; after real success commit inject malformed result, readback error/mismatch, all four states, repeated cancel/lease loss/restart and assert zero failure mutation/reingest; deterministic recovery identity and concurrent disappearance / 非空来源哨兵与精确重启；真实成功提交后注入 result/readback/四状态/取消/重启并断言 failure mutation/重复导入为零；确定性恢复身份与并发消失 | `PASS (focused)` — exhaustive retained sentinel deferred / 完整留存哨兵后置 |
| Secret sinks / 密钥落点 | Private-pipe + mock-request observation, then exact post-cleanup filesystem/SQLite/operator/JUnit zero-match with named negative exclusions / 私有 pipe + mock request 观察，随后清理后多落点精确零匹配及命名负向排除 | `NOT_RUN` |

## Planned quality gates / 计划质量门禁

Exact focused nodes, case counts, timings and retained-sentinel statistics will be finalized only after implementation. Every result remains `NOT_RUN` until the final invocation and material output are recorded.

准确专项节点、case 数、耗时及留存哨兵统计只在实现后定稿；在记录最终调用与关键输出前，全部结果保持 `NOT_RUN`。

| Check / 检查 | Planned command or scope / 计划命令或范围 | Status / 状态 |
| --- | --- | --- |
| Locked dependencies / 锁定依赖 | `uv sync --all-groups --locked` | `NOT_RUN` |
| Lint / 代码规范 | `uv run ruff check .` | `PARTIAL` — all 0009 changed files PASS; whole tree still `NOT_RUN` / 0009 全部修改文件通过；整树仍未运行 |
| Format / 格式 | `uv run ruff format --check .` | `NOT_RUN` |
| Strict types / 严格类型 | `uv run mypy src/media_sync` | PASS — 70 source files / 70 个源码文件 |
| Full branch-aware suite / 完整分支感知套件 | `uv run pytest --cov=media_sync --cov-report=term` | `NOT_RUN` |
| Focused refresh/cleanup gate / Refresh/清理专项 | Exact unit/contract/integration/migration nodes / 精确 unit/contract/integration/migration 节点 | `PASS (function-first MVP)` — provenance, cleanup, refresh runtime and CLI wiring / 来源、清理、刷新运行时及 CLI 接线通过 |
| Build and wheel smoke / 构建与 wheel smoke | `uv build` plus clean wheel install/import/CLI checks / 构建及干净 wheel 安装/import/CLI | `NOT_RUN` |
| Packaged migrations/resources / 随包迁移/资源 | Head inventory and round-trip tests / head 清单及往返测试 | `PASS (focused)` — `0005` head/resource/round-trip |
| Documentation / 文档 | `uv run python scripts/check_docs.py` | PASS — 56 Markdown files / 56 个 Markdown 文件 |
| Pinned upstreams / 锁定上游 | `uv run python scripts/check_upstreams.py` | PASS — 2 locked checkouts / 2 个锁定检出 |
| Patch whitespace / 补丁空白 | `git diff --check` | PASS |
| Runtime artifacts untracked / 运行产物未跟踪 | Scoped ignore, `git ls-files` and `git status` checks / 限定 ignore、`git ls-files` 与 `git status` | `NOT_RUN` |
| Fresh retained sentinel / 全新留存哨兵 | `.media-sync/verification/0009-refresh-sentinel-root` exact allowlist/scans / 精确 allowlist/扫描 | `NOT_RUN` |

## Planned retained-artifact rules / 计划留存产物规则

- The 0009 retained root must not exist before its one authoritative run and must never be deleted or recreated afterward. The 0007 and 0008 roots remain untouched read-only evidence. / 0009 留存根在唯一权威运行前必须不存在，之后不得删除或重建；0007 与 0008 根保持不动的只读证据。
- Use an exact safe-test allowlist, never module-level `-k` subtraction. Name every profile/quarantine/unresolved or deliberate raw-fixture case excluded from whole-tree zero-match evidence. / 使用精确安全测试 allowlist，不依赖模块级 `-k` 减法；逐项命名从整树零匹配排除的 profile/quarantine/unresolved 或故意原始夹具 case。
- Prove a generated signed sentinel entered the dedicated private pipe and mock HTTP request. Separately prove post-collection dynamic sentinels existed in non-empty fresh/recovered JSONL source roots before exact cleanup, and bind already-succeeded restart to the same exact source identity. Do not put values in source, pytest IDs, assertions, JUnit properties or operator strings. / 证明生成签名哨兵进入专用私有 pipe 与 mock HTTP 请求；另证明 collection 后动态哨兵在非空 fresh/recovered JSONL 来源根清理前确实存在，并把 already-succeeded restart 绑定到相同精确来源身份。不得把值写入源码、pytest ID、断言、JUnit property 或运维字符串。
- Validate every Windows pytest `current` alias as an existing same-parent in-root target and independently enumerate/scan every real target. / 把每个 Windows pytest `current` alias 验证为根内同父现存目标，并独立枚举/扫描每个真实目标。
- Final traversal, content/path scan and SQLite main/sidecar/logical scan fail closed on any unreadable, locked, nonregular, reparse or traversal condition. / 最终遍历、内容/路径扫描及 SQLite main/sidecar/逻辑扫描遇到不可读、锁定、非普通、reparse 或遍历异常时 fail closed。

## Live qualification / 真人资格验证

| Platform / 平台 | QR login / 二维码登录 | Cookie login / Cookie 登录 | Saved session / 保存会话 | Creator/detail refresh / 作者/detail 刷新 | Live CDN / 真人 CDN | Real Emby/Jellyfin / 真实 Emby/Jellyfin |
| --- | --- | --- | --- | --- | --- | --- |
| `xhs` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `dy` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `ks` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `bili` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `wb` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `tieba` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `zhihu` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

Phone login remains unsupported. Offline fake-detail evidence never changes this table.

手机号登录仍不支持；离线 fake detail 证据绝不改变本表。

## Deferred implementation / 延期实现

The durable automatic `sync → download → Emby` DAG is execution 0010. QR UX, credential-bearing CDN headers, Bilibili playable derivatives, Weibo/Tieba/Zhihu Asset discovery, per-request upstream spacing, REST, resident supervision, Docker and HA/PostgreSQL remain deferred. Persistent unresolved cleanup blocks require later explicit operator repair/acknowledgement and are never silently cleared.

持久自动 `sync → download → Emby` DAG 属于执行 0010。QR UX、可能携带凭据的 CDN header、Bilibili 可播放衍生物、微博/贴吧/知乎 Asset discovery、逐请求上游间隔、REST、常驻监督、Docker 及 HA/PostgreSQL 继续延期。持久 unresolved 清理 block 需要后续显式操作员修复/确认，绝不静默清除。
