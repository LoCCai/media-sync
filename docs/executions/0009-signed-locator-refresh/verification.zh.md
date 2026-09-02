[English](verification.md) | **中文**

# 执行 0009 验证

- 验证状态：`FUNCTION-FIRST MVP / PASSING OFFLINE FOCUSED GATES`
- 计划日期：2026-08-30
- 网络与账户策略：仅离线 fake 锁定上游模块、仓库自有本地 helper 与 mock HTTP；不使用连接平台的浏览器、真实凭据、平台/CDN 端点或 Emby/Jellyfin 服务器
- 实现状态：来源、清理、detail 刷新、惰性运行时及 CLI 接线已完成离线验证

本文件同时保留历史暂停证据与当前结果；migration、导入、清理、功能 locator refresh 及 CLI 接线已实现；完整套件/构建、留存哨兵及真人行仍待完成。

本文件是执行 0009 的冻结验证契约，不是实现证据。计划基线文档检查单独记录；在记录准确命令与结果前，不提升任何 migration、刷新、清理、签名哨兵或真人行。

## 计划基线检查

下列各行只验收已提交的 goal/plan/progress/verification 基线，不执行行为。

| 检查 | 准确命令 | 结果 |
| --- | --- | --- |
| 文档链接 | `uv run python scripts/check_docs.py` | 通过 |
| 锁定上游 | `uv run python scripts/check_upstreams.py` | 通过 |
| 补丁空白 | `git diff --check` | 通过 — 退出码 `0`，无输出 |

## 已执行的暂停检查点验证

| 检查 | 准确命令 | 结果 |
| --- | --- | --- |
| 修改源码 lint | `uv run ruff check src/media_sync/infrastructure/db/__init__.py src/media_sync/infrastructure/db/models.py src/media_sync/infrastructure/db/repositories.py src/media_sync/infrastructure/db/migrations/versions/0005_asset_refresh_sources.py src/media_sync/scheduler/mediacrawler_handler.py` | PASS — `All checks passed!` |
| cleanup 事实专项 | `uv run pytest -q tests/integration/test_mediacrawler_scheduler_handler.py::test_empty_normalized_delta_is_a_successful_guarded_checkpoint tests/integration/test_mediacrawler_scheduler_handler.py::test_committed_sync_run_truth_wins_over_invalid_returned_summary` | PASS — `2 passed in 1.21s` |
| 严格类型 | `uv run mypy src/media_sync` | 失败，共 3 项 |
| migration 专项节点 | `uv run pytest -q tests/integration/test_database.py::test_alembic_upgrade_matches_metadata_and_downgrades tests/integration/test_packaged_migrations.py::test_programmatic_upgrade_uses_packaged_resources_and_handles_percent_path` | 失败，共 2 项 |
| handler 整文件 | `uv run pytest -q tests/integration/test_mediacrawler_scheduler_handler.py` | 旧契约尚未同步新清理语义 |
| 补丁空白 | `git diff --check` | 通过 |

暂停前有意未运行完整 pytest/coverage、构建、wheel smoke、签名哨兵及权威留存门禁；未创建 0009 留存根，也未触碰 0007/0008 留存根。

## 恢复批次验证

| 检查 | 准确命令 | 结果 |
| --- | --- | --- |
| 合并 lint | `uv run ruff check <12 changed migration/ingestion/cleanup source and test files>` | PASS — `All checks passed!` |
| 严格类型 | `uv run mypy src/media_sync` | PASS — `Success: no issues found in 65 source files` |
| migration、导入与清理回归 | `uv run pytest -q <4 migration nodes> tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_scheduler_handler.py tests/contract/test_mediacrawler_supervision.py` | 87 项通过、1 项 Windows 合理跳过 |
| 下载器重解析 | `uv run pytest -q tests/unit/test_media_downloader.py` and `uv run pytest -q tests/unit/test_download_application.py tests/integration/test_asset_download_orchestration.py` | 45 项加 39 项通过 |
| 补丁空白 | `git diff --check` | PASS |

这些检查只验收恢复后的来源/清理批次，不宣称 locator refresh、平台流量、CDN 下载或 Emby 扫描已可用。

## 功能优先刷新验证

| 检查 | 准确命令 | 结果 |
| --- | --- | --- |
| detail refresher 单元与 fake-child 契约 | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py` | PASS — `20 passed` |
| locator、normalizer 与下载回归 | `uv run pytest -q tests/unit/test_media_locator.py tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_asset_download_orchestration.py` | PASS — `111 passed` |
| 惰性精确来源运行时 | `uv run pytest -q tests/integration/test_mediacrawler_download_runtime.py` | 覆盖精确单来源、0/N、显式不匹配、Cookie/策略上下文及构造零工作 |
| CLI 资产下载接线 | `uv run pytest -q tests/unit/test_cli.py -k "asset_download"` | 覆盖默认关闭、许可证拦截、ffprobe 行为及显式惰性 refresher 构造 |
| 修改代码 lint | `uv run ruff check src/media_sync/application/mediacrawler_download.py src/media_sync/integrations/mediacrawler/detail_runner.py src/media_sync/integrations/mediacrawler/refresh.py src/media_sync/interfaces/cli.py src/media_sync/media/errors.py tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/unit/test_cli.py` | PASS — `All checks passed!` |
| 严格类型 | `uv run mypy src/media_sync` | PASS — `Success: no issues found in 70 source files` |

上述各行均为离线验证；fake child 只导入仓库测试创建的 fake checkout，未发生真人平台浏览器、真实凭据、CDN、Emby/Jellyfin 或 Git 网络操作。

## 计划行为证据

| 范围 | 必需证据 | 状态 |
| --- | --- | --- |
| Migration 与 backfill | head/往返/FK/索引、精确平台/作者/adapter/stable-key 唯一推断、歧义/畸形/损坏不绑定、保留恢复身份 | `PASS (focused)` |
| 导入 observation | 同事务、错误关系回滚、旧 run 重放不回退 last-run 全序/时间、多账户、两类替换推进 generation、归档 reset 资格 | `PASS (focused)` |
| 来源 selector | 两种来源模式；共用锁二次 block 检查在密钥/claim/attach/prepare/spawn 前拦截首次读取后的 writer；事务无 FS I/O | MVP 的 0/1/N 与显式选择通过；既有 Job 不可变绑定及完整 TOCTOU 强化后置 |
| 恢复顺序 | inspection 零变更、verified 无来源/profile/凭据、prepared 只做已绑定 CAS/收尾、两者无 child/HTTP/新 attempt | `NOT_RUN` |
| Job 来源与配置绑定 | 既有 natural key 与空 `run_id`、payload 不含 observation kind、audit kind 升级保留 retry Job、恢复来源不可变、事务复核配置 | `NOT_RUN` |
| 私有 child 协议 | 专用 pipe、严格帧/错误矩阵、共用账户锁覆盖 child tree/HTTP/收尾/cleanup、所有 block writer 共用 fence、父死亡/取消 | 有界 stdout frame、清理及进程监督通过；专用旁路 pipe 与完整锁矩阵后置 |
| 平台 selector | 要求精确 stored hint；XHS authority、数值边界及固定 disposition；其余形状与三个不 spawn 平台 | DY/KS/Bili 与显式 XHS 详情链接通过；XHS 自动 feed 查找后置 |
| 候选身份 | child 验证语义、完整 request fingerprint 绑定响应、无 query hint 精确选一、同 kind 歧义与仅 position 匹配 fail closed | `NOT_RUN` |
| 下载器 | 签名 URL 只到 mock HTTP、一次重解析、direct 不变、续传安全、metadata/header 不变 | 功能性 MediaCrawler resolver 已接通 |
| 终态清理 | 非空来源哨兵与精确重启；真实成功提交后注入 result/readback/四状态/取消/重启并断言 failure mutation/重复导入为零；确定性恢复身份与并发消失 | 完整留存哨兵后置 |
| 密钥落点 | 私有 pipe + mock request 观察，随后清理后多落点精确零匹配及命名负向排除 | `NOT_RUN` |

## 计划质量门禁

准确专项节点、case 数、耗时及留存哨兵统计只在实现后定稿；在记录最终调用与关键输出前，全部结果保持 `NOT_RUN`。

| 检查 | 计划命令或范围 | 状态 |
| --- | --- | --- |
| 锁定依赖 | `uv sync --all-groups --locked` | `NOT_RUN` |
| 代码规范 | `uv run ruff check .` | 0009 全部修改文件通过；整树仍未运行 |
| 格式 | `uv run ruff format --check .` | `NOT_RUN` |
| 严格类型 | `uv run mypy src/media_sync` | 70 个源码文件 |
| 完整分支感知套件 | `uv run pytest --cov=media_sync --cov-report=term` | `NOT_RUN` |
| Refresh/清理专项 | 精确 unit/contract/integration/migration 节点 | 来源、清理、刷新运行时及 CLI 接线通过 |
| 构建与 wheel smoke | 构建及干净 wheel 安装/import/CLI | `NOT_RUN` |
| 随包迁移/资源 | head 清单及往返测试 | `PASS (focused)` — `0005` head/resource/round-trip |
| 文档 | `uv run python scripts/check_docs.py` | 56 个 Markdown 文件 |
| 锁定上游 | `uv run python scripts/check_upstreams.py` | 2 个锁定检出 |
| 补丁空白 | `git diff --check` | PASS |
| 运行产物未跟踪 | 限定 ignore、`git ls-files` 与 `git status` | `NOT_RUN` |
| 全新留存哨兵 | 精确 allowlist/扫描 | `NOT_RUN` |

## 计划留存产物规则

- 0009 留存根在唯一权威运行前必须不存在，之后不得删除或重建；0007 与 0008 根保持不动的只读证据。
- 使用精确安全测试 allowlist，不依赖模块级 `-k` 减法；逐项命名从整树零匹配排除的 profile/quarantine/unresolved 或故意原始夹具 case。
- 证明生成签名哨兵进入专用私有 pipe 与 mock HTTP 请求；另证明 collection 后动态哨兵在非空 fresh/recovered JSONL 来源根清理前确实存在，并把 already-succeeded restart 绑定到相同精确来源身份。不得把值写入源码、pytest ID、断言、JUnit property 或运维字符串。
- 把每个 Windows pytest `current` alias 验证为根内同父现存目标，并独立枚举/扫描每个真实目标。
- 最终遍历、内容/路径扫描及 SQLite main/sidecar/逻辑扫描遇到不可读、锁定、非普通、reparse 或遍历异常时 fail closed。

## 真人资格验证

| 平台 | 二维码登录 | Cookie 登录 | 保存会话 | 作者/detail 刷新 | 真人 CDN | 真实 Emby/Jellyfin |
| --- | --- | --- | --- | --- | --- | --- |
| `xhs` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `dy` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `ks` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `bili` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `wb` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `tieba` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `zhihu` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

手机号登录仍不支持；离线 fake detail 证据绝不改变本表。

## 延期实现

持久自动 `sync → download → Emby` DAG 属于执行 0010。QR UX、可能携带凭据的 CDN header、Bilibili 可播放衍生物、微博/贴吧/知乎 Asset discovery、逐请求上游间隔、REST、常驻监督、Docker 及 HA/PostgreSQL 继续延期。持久 unresolved 清理 block 需要后续显式操作员修复/确认，绝不静默清除。
