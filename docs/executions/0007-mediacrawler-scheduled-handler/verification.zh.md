[English](verification.md) | **中文**

# 执行 0007 验证

- 验证状态：`PARTIAL` — AC6 与 AC13 尚未完整
- 验证日期：2026-08-30
- 网络与账户策略：仅离线夹具与仓库自有本地辅助进程；不使用浏览器、真实凭据、平台/CDN 端点或 Emby/Jellyfin 服务器
- 实现状态：已实现本文记录的离线范围

执行 0007 现已有可执行离线证据，不再只是计划记录。这些证据验收本地 scheduler/bridge/child/产物/数据库协议，不验收真人平台行为。后期发现的重复取消竞态已修复，并成功重跑根门禁与全量门禁；AC6 的确定性取消 barrier 覆盖与 AC13 的完整失败/密钥落点交叉矩阵仍在下方所列更窄边界明确标为 `PARTIAL`。

## 已记录专项门禁

下列准确命令覆盖策略、bridge、进程监督、受保护导入、定时 handler、scheduler repository/worker 与 CLI 表面；它取代此前较窄的 10 项 selector 记录。

```powershell
uv run pytest tests\unit\test_mediacrawler_subscription_policy.py tests\contract\test_mediacrawler_bridge.py tests\contract\test_mediacrawler_supervision.py tests\integration\test_mediacrawler_db_ingestion.py tests\integration\test_mediacrawler_scheduler_handler.py tests\integration\test_scheduler_repository.py tests\integration\test_scheduler_worker.py tests\unit\test_cli.py -q
```

最终结果：`PASS` — exit `0`; `320 passed, 1 skipped in 128.64s`.

唯一 skip 是 Windows 上不适用的 POSIX mode-bit 断言。支持 POSIX 的系统会覆盖 `.quarantine` mode 收紧；在 Windows 上，等效受限 ACL 仍是操作员控制根目录的部署边界，本次运行不会虚假宣称已证明该 ACL。标准 `uv run pytest` 最初暴露新 contract helper 的包导入 collection 失败；新增 `tests/__init__.py` 与 `tests/contract/__init__.py` 后修复 collection，随后上方命令通过。

同一实现树上还记录了 `uv run ruff check .`（`PASS`）、`uv run ruff format --check .`（`PASS`）及 `git diff --check`（`PASS`、无输出）。收口表将以最终根任务重跑为准，不把这些结果冒充未知的全量套件总数。

## 行为证据

| 范围 | 证据 | 状态 |
| --- | --- | --- |
| 封闭策略 v1 | 严格 schema 包含 `schema_version`、可选 `creator_input.secret_ref`、显式 `allow_full_history`、正数且 ≤ 300 的延迟与 `headless`；许可证授权独立且默认关闭 | `PASS` |
| Manifest v3/回执 v2 | 新严格 writer 绑定 scheduler Job 与 attempt UUID/根，并拒绝未知/不匹配身份 | `PASS` |
| Legacy manifest v2/回执 v1 | 共享归一化/手工导入只读逐字节往返，绝不重新密封/改写；定时重启恢复只信任 v3 | `PASS` |
| 锁定上游形状 | 忠实 `parse_cmd()` 夹具保留虚拟 Cookie、绑定 `CRAWLER_MAX_SLEEP_SEC`、设置 `MAX_CONCURRENCY_NUM=1` 并保持下载关闭 | 只证明配置；不宣称逐请求间隔 |
| Attempt 隔离与重启 | 同一持久 Job UUID 通过唯一 attempt UUID/根重试；旧 attempt 不能导入/checkpoint/删除后继 | `PASS` |
| Heartbeat 与短事务 | 真实长运行本地 child 期间父进程 heartbeat 与独立 SQLite writer 持续；进程等待不持有 SQLite 事务 | `PASS` |
| 协作取消 | spawn 前/运行中取消、lease fencing、重复 runner 取消及真实批次间 ownership-guard barrier 均通过；runner/ingestion 都先 join 再 unwind，第二批被 fencing | 仍缺少确定性 child 后/seal 前及 seal 后/导入前 barrier |
| 父进程硬死亡与 profile 锁 | 仓库自有 helper 硬杀验证父进程 liveness/control、子/孙进程退出及有界账户/profile 恢复；已实现 Windows attach/start handshake | `PASS` |
| Ownership、ABA 与导入 | 每个 SyncRun 变更及每个导入/checkpoint 事务前执行精确 owner/token/未过期 guard | `PASS` |
| Waiting/失败映射 | 采用左列固定映射；`waiting_user`/`waiting_auth` 不 spawn 且必须显式 resume | 取消/lease 丢失传播 fencing，旧 handler 不收尾 |
| 七平台真实离线协议 | 七个平台：订阅 → tick → v3 写入/读取 → 真实本地 fake child 写版本化 JSONL → v2 回执写入/读取 → 受保护导入 → 重试/重启 → 幂等重放 | 仅离线通过 |
| 四状态清理 | `ABSENT`、`REMOVED`、`QUARANTINED`、`UNRESOLVED`；unresolved 清理创建固定/脱敏账户 block 并 fence 后续执行 | 已实现状态机通过 |
| 完整失败密钥落点矩阵 | 现有清理/脱敏/哨兵测试覆盖大量场景 | 完整“失败类型 × 保留文件系统/SQLite/运维落点”交叉矩阵尚不完整 |
| 显式 CLI 启用 | 默认运行不处理 MediaCrawler Job；两个开关独立且输出脱敏 | `PASS` |

## 取消与密钥落点验收缺口

AC6 继续为 `PARTIAL`。已覆盖 spawn 前取消、运行中取消、lease fencing、runner 等待期间重复取消，以及第二个导入批次 guard 处的确定性取消。统一 join helper 现在会记录首次取消、只通知一次可取消工作，并在后续取消下继续 shield，直到 runner/ingestion 得出确定 verdict；批次间测试会保留已提交首批并 fence 第二批。现在只缺少 child 退出后/seal 前及 seal 后/导入前的确定性测试。

AC13 继续为 `PARTIAL`。清理/脱敏/哨兵证据已较充分，但尚未针对所有保留文件系统、SQLite 与运维落点，完成已知密钥输出、非零退出、timeout、每种输出超限、回执拒绝、取消及 lease 丢失的完整交叉组合。

## 可能携带凭据的保留边界

- 普通 active attempt 根必须以 `ABSENT` 或 `REMOVED` 收尾。
- 若原子隔离成功但 no-follow 清理失败，精确不安全证据只能保留在已忽略的 `.quarantine` 下。该目录由操作员控制，POSIX 上收紧为 `0700`，其他系统预期使用等效受限 ACL，并明确排除在零密钥声明外。
- 若既不能证明删除也不能证明隔离，`UNRESOLVED` 只会在 attempt 根外创建固定/脱敏的持久账户/事件 block，并硬 fence 后续密钥解析、run attach、准备与 spawn。原始清理错误与保留路径不得进入运维输出。
- 持久账户 browser profile 同样属于可能携带凭据的边界，并排除在整树零密钥声明外。
- 仓库 ignore 规则覆盖 `.quarantine/`、`.cleanup-security-v1/` 与账户 profile 路径，包括仓库内的自定义 runtime 根；它们用于防止意外 Git 跟踪，但不能替代专用、由操作员控制的根目录/祖先及受限权限/ACL。

## 最终根质量门禁

后期重复取消竞态复现后，第一次全量门禁被主动中止且不计入下表。表中每条命令都已在修复后的代码树上重跑；保留产物门禁在下一节单独记录。

| 检查 | 最终准确命令 | 状态与证据 |
| --- | --- | --- |
| 锁定依赖 | `uv sync --all-groups --locked` | 解析 58、审计 43 |
| 代码规范 | `uv run ruff check .` | `PASS` — `All checks passed!` |
| 格式 | `uv run ruff format --check .` | 156 个文件 |
| 严格类型 | `uv run mypy src\media_sync` | 65 个源码文件 |
| 全量测试与覆盖率 | `uv run pytest --cov=media_sync --cov-report=term` | 819 项通过、1 项跳过、212.99 秒；分支感知总覆盖率 79% |
| 执行 0007 专项 | 上方准确八模块命令 | 320 项通过、1 项跳过、128.64 秒 |
| 构建 | `uv build` | 源码包与 wheel |
| 随包资源与数据库兼容 | `uv run pytest tests\integration\test_packaged_migrations.py -q` | 6 项通过、7.47 秒 |
| 文档链接 | `uv run python scripts\check_docs.py` | 44 个 Markdown 文件 |
| 锁定上游 | `uv run python scripts\check_upstreams.py` | 2 个锁定 checkout |
| 自定义运行根 ignore 边界 | `git check-ignore -v --no-index -- custom-runtime/.quarantine/evidence.json custom-runtime/.cleanup-security-v1/account-blocks/xhs/account.json custom-runtime/accounts/xhs/00000000-0000-0000-0000-000000000000/profile/cookies.json .media-sync/verification/0007-closeout-sentinel-root` | 四个路径均匹配预期规则 |
| 补丁空白 | `git diff --check` | 无输出 |
| 运行产物未跟踪 | `git ls-files -- archive exports jobs .media-sync dist` and `git status --short -- archive exports jobs .media-sync dist` | 均无输出 |
| 安全留存产物哨兵 | 下方精确 29-case allowlist 与扫描 | 29 项通过；8 次零匹配；21 个 SQLite 逻辑权限检查 |

## 最终安全留存产物哨兵

权威留存根为 `.media-sync/verification/0007-closeout-sentinel-root`。运行前要求该路径不存在，之后从未删除或替换。下方 allowlist 精确展开为 29 个 case；它会保留成功定时 handler 根、manifest/receipt 证据、临时 SQLite、捕获的 pytest/运维输出及本地 helper-process 证据，同时不选择故意保留 quarantine/unresolved 的负向测试。

```powershell
$relativeRoot = '.media-sync/verification/0007-closeout-sentinel-root'
$sentinelRoot = [IO.Path]::GetFullPath((Join-Path (Resolve-Path -LiteralPath '.').Path $relativeRoot))
if (Test-Path -LiteralPath $sentinelRoot) { throw 'Closeout sentinel root already exists' }
git check-ignore -q -- "$relativeRoot/probe"
if ($LASTEXITCODE -ne 0) { throw 'Sentinel root is not ignored' }
New-Item -ItemType Directory -Path $sentinelRoot | Out-Null

$nodes = @(
  'tests/integration/test_mediacrawler_scheduler_handler.py::test_all_platform_fixtures_prepare_v3_and_ingest_forward_off_loop'
  'tests/integration/test_mediacrawler_scheduler_handler.py::test_all_platforms_cross_real_v3_v2_process_protocol_retry_and_idempotent_restart'
  'tests/integration/test_mediacrawler_scheduler_handler.py::test_real_handler_process_wait_keeps_heartbeat_and_independent_sqlite_writer_live'
  'tests/integration/test_mediacrawler_scheduler_handler.py::test_bridge_late_failure_removes_the_exact_attempt_root'
  'tests/contract/test_mediacrawler_bridge.py::test_manifest_v3_binds_scheduler_and_attempt_identity'
  'tests/contract/test_mediacrawler_bridge.py::test_sealed_v2_v1_artifacts_round_trip_byte_exact_and_read_only'
  'tests/contract/test_mediacrawler_supervision.py::test_start_token_is_sent_only_after_tree_attachment'
  'tests/contract/test_mediacrawler_supervision.py::test_running_cancel_joins_child_and_grandchild_before_cleanup'
  'tests/contract/test_mediacrawler_supervision.py::test_receipt_failure_removes_secret_bytes_but_preserves_profile'
  'tests/contract/test_mediacrawler_supervision.py::test_hard_parent_death_stops_real_child_tree_and_allows_safe_recovery'
  'tests/contract/test_mediacrawler_supervision.py::test_pinned_shape_parse_cmd_preserves_cookie_delay_and_single_concurrency'
  'tests/integration/test_scheduler_worker.py::test_worker_heartbeats_blocking_handler_then_cancel_returns_durable_terminal_state'
  'tests/integration/test_scheduler_secret_sinks.py::test_raw_handler_secret_stays_out_of_scheduler_and_retained_artifacts'
  'tests/integration/test_secret_sinks.py::test_all_json_error_and_url_sinks_redact_before_sqlite'
  'tests/integration/test_scheduled_offline_pipeline.py::test_scheduled_offline_pipeline_survives_restart_without_duplicate_identities'
  'tests/unit/test_cli.py::test_mediacrawler_dry_run_rejects_signed_creator_url_without_echoing_token'
  'tests/unit/test_cli.py::test_scheduler_mediacrawler_enablement_and_license_are_explicit'
)
uv run pytest -vv --tb=short -p no:cacheprovider `
  --basetemp (Join-Path $sentinelRoot 'pytest') `
  --junitxml (Join-Path $sentinelRoot 'pytest-junit.xml') @nodes 2>&1 |
  Tee-Object -FilePath (Join-Path $sentinelRoot 'pytest-output.txt')
```

实测 pytest 结果为 `29 passed in 40.90s`。Pytest 在 Windows 上创建了 19 个 `current` 目录符号链接，因此首次通用“拒绝全部 reparse point”后置条件在扫描前停止。随后逐个证明这些别名都是单目标目录符号链接，现存目标位于留存根内且与别名同父；每个真实目标目录也独立存在并参与扫描，没有任何别名逃逸。留存树没有被重跑、删除或改写；扫描在同一份精确证据上继续。

恢复后的门禁使用 `rg --hidden --no-ignore --text --fixed-strings` 对全部真实文件扫描 8 个生成值：夹具 Cookie、监督 Cookie、parse Cookie、scheduler-handler 密钥、SQLite 落点密钥、签名 query 密钥、签名作者 token 与 bridge 后期失败的 attempt 密钥。8 次均返回 `rg` 退出码 `1`，即扫描成功且零匹配。只读 SQLite 查询检查了所有含 `jobs` 表的数据库，在 21 个数据库中均未发现逻辑上 `lease_owner` 或 `lease_token` 非空的行；行为测试另行证明 scheduler 权限绝不进入 child 边界。限定范围的 `git ls-files` 与 `git status` 均无输出。

最终留存结果：

```text
CLOSEOUT_PASS cases=29 pytest_seconds=40.90 scans=8 sqlite_authority=PASS aliases=19
files=279 directories=364 bytes=5958937
```

本安全产物 allowlist 明确排除的留存负向函数为：

- 进程监督：`test_runner_hard_stops_and_records_redacted_block_when_attempt_cleanup_is_unresolved`, `test_cleanup_is_unresolved_when_atomic_quarantine_and_direct_removal_both_fail`, `test_cleanup_quarantines_when_post_move_scrub_is_denied`, `test_existing_quarantine_directory_mode_is_tightened_before_isolation`, `test_quarantined_cleanup_returns_only_fixed_operator_status`.
- 定时 handler：`test_unresolved_cleanup_fences_current_and_recovery_without_successor_or_spawn`, `test_cleanup_incident_persistence_failure_still_fences_without_terminal_write`, `test_lease_loss_cancels_and_joins_runner_before_worker_returns`, `test_task_cancellation_signals_and_joins_runner`, `test_repeated_task_cancellation_still_joins_runner_before_unwind`, `test_repeated_cancellation_between_ingestion_batches_joins_before_unwind`, `test_repeated_cancellation_during_unresolved_cleanup_records_block_before_unwind`, `test_repeated_cancellation_during_untrusted_recovery_records_block`.
- CLI 投影夹具：会故意把原始脱敏夹具写入临时 SQLite，由全量套件覆盖，不用于整树零匹配声明。

零匹配声明只适用于本 29-case 安全产物树中的 8 个精确生成值；不宣称真实 browser profile 或故意 quarantine/unresolved 证据中不可能存在任意未知密钥。

## 真人资格验证

| 平台 | 二维码登录 | Cookie 登录 | 保存会话 | 真人作者流量 | 真人 CDN 获取 | 真实 Emby/Jellyfin 扫描/播放 |
| --- | --- | --- | --- | --- | --- | --- |
| `xhs` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `dy` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `ks` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `bili` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `wb` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `tieba` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `zhihu` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

## 延期实现

定时 backfill、签名 locator refresh、真实 CDN/媒体获取、自动 sync → download → export 规划、逐 HTTP 请求间隔、二维码/challenge 展示 UX、REST、常驻生产守护、Docker、分布式 HA/PostgreSQL 及真人 Emby/Jellyfin 运维不属于执行 0007。锁定形状证据只证明 `CRAWLER_MAX_SLEEP_SEC` 与 `MAX_CONCURRENCY_NUM=1` 的配置，不证明每次请求都按间隔执行。
