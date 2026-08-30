# Execution 0007 verification / 执行 0007 验证

- Verification state / 验证状态：`PARTIAL` — AC6 and AC13 remain incomplete / `PARTIAL` — AC6 与 AC13 尚未完整
- Verification date / 验证日期：2026-08-30
- Network/account policy / 网络与账户策略：offline fixtures and repository-owned local helper processes only; no browser, real credential, platform/CDN endpoint or Emby/Jellyfin server / 仅离线夹具与仓库自有本地辅助进程；不使用浏览器、真实凭据、平台/CDN 端点或 Emby/Jellyfin 服务器
- Implementation state / 实现状态：IMPLEMENTED for the documented offline scope / 已实现本文记录的离线范围

Execution 0007 has executable offline evidence; it is no longer a planning-only record. The evidence qualifies the local scheduler/bridge/child/artifact/database protocol, not live platform behavior. The late repeated-cancellation race was repaired and its root/full gates were rerun successfully. AC6 deterministic cancellation-barrier coverage and AC13's complete failure/secret-sink cross-product nevertheless remain explicitly `PARTIAL` at the narrower boundaries recorded below.

执行 0007 现已有可执行离线证据，不再只是计划记录。这些证据验收本地 scheduler/bridge/child/产物/数据库协议，不验收真人平台行为。后期发现的重复取消竞态已修复，并成功重跑根门禁与全量门禁；AC6 的确定性取消 barrier 覆盖与 AC13 的完整失败/密钥落点交叉矩阵仍在下方所列更窄边界明确标为 `PARTIAL`。

## Recorded focused gate / 已记录专项门禁

The following exact command covers the policy, bridge, process supervision, guarded ingestion, scheduled handler, scheduler repository/worker and CLI surfaces. It supersedes the earlier narrow 10-test selector record.

下列准确命令覆盖策略、bridge、进程监督、受保护导入、定时 handler、scheduler repository/worker 与 CLI 表面；它取代此前较窄的 10 项 selector 记录。

```powershell
uv run pytest tests\unit\test_mediacrawler_subscription_policy.py tests\contract\test_mediacrawler_bridge.py tests\contract\test_mediacrawler_supervision.py tests\integration\test_mediacrawler_db_ingestion.py tests\integration\test_mediacrawler_scheduler_handler.py tests\integration\test_scheduler_repository.py tests\integration\test_scheduler_worker.py tests\unit\test_cli.py -q
```

Final result / 最终结果：`PASS` — exit `0`; `320 passed, 1 skipped in 128.64s`.

The single skip is the POSIX mode-bit assertion on Windows. POSIX `.quarantine` mode tightening is covered where supported; on Windows, an equivalent restrictive ACL remains an operator-controlled-root deployment boundary and is not falsely claimed by this run. The standard `uv run pytest` first exposed package-import collection failures for the new contract helpers; adding `tests/__init__.py` and `tests/contract/__init__.py` fixed collection before the passing run above.

唯一 skip 是 Windows 上不适用的 POSIX mode-bit 断言。支持 POSIX 的系统会覆盖 `.quarantine` mode 收紧；在 Windows 上，等效受限 ACL 仍是操作员控制根目录的部署边界，本次运行不会虚假宣称已证明该 ACL。标准 `uv run pytest` 最初暴露新 contract helper 的包导入 collection 失败；新增 `tests/__init__.py` 与 `tests/contract/__init__.py` 后修复 collection，随后上方命令通过。

Additional pre-final checks already recorded on the same implementation tree were `uv run ruff check .` (`PASS`), `uv run ruff format --check .` (`PASS`) and `git diff --check` (`PASS`, no output). They will be represented by the final root rerun in the closeout table rather than promoted into unknown full-suite totals.

同一实现树上还记录了 `uv run ruff check .`（`PASS`）、`uv run ruff format --check .`（`PASS`）及 `git diff --check`（`PASS`、无输出）。收口表将以最终根任务重跑为准，不把这些结果冒充未知的全量套件总数。

## Behavior evidence / 行为证据

| Scope / 范围 | Evidence / 证据 | Status / 状态 |
| --- | --- | --- |
| Closed policy v1 / 封闭策略 v1 | Strict schema with `schema_version`, optional `creator_input.secret_ref`, explicit `allow_full_history`, positive delay ≤ 300 and `headless`; license authorization separate/default-off / 严格 schema 包含 `schema_version`、可选 `creator_input.secret_ref`、显式 `allow_full_history`、正数且 ≤ 300 的延迟与 `headless`；许可证授权独立且默认关闭 | `PASS` |
| Manifest v3/receipt v2 / Manifest v3/回执 v2 | New strict writers bind scheduler Job plus attempt UUID/root and reject unknown/mismatched identities / 新严格 writer 绑定 scheduler Job 与 attempt UUID/根，并拒绝未知/不匹配身份 | `PASS` |
| Legacy manifest v2/receipt v1 / Legacy manifest v2/回执 v1 | Shared normalization/manual ingest round-trips exact bytes read-only and never reseals/rewrites; scheduled restart recovery trusts v3 only / 共享归一化/手工导入只读逐字节往返，绝不重新密封/改写；定时重启恢复只信任 v3 | `PASS` |
| Pinned upstream shape / 锁定上游形状 | Faithful `parse_cmd()` fixture preserves dummy Cookie, binds `CRAWLER_MAX_SLEEP_SEC`, sets `MAX_CONCURRENCY_NUM=1` and keeps download disabled / 忠实 `parse_cmd()` 夹具保留虚拟 Cookie、绑定 `CRAWLER_MAX_SLEEP_SEC`、设置 `MAX_CONCURRENCY_NUM=1` 并保持下载关闭 | `PASS` — configuration only; no per-request spacing claim / 只证明配置；不宣称逐请求间隔 |
| Attempt isolation and restart / Attempt 隔离与重启 | Same durable Job UUID retries through unique attempt UUID/roots; stale attempts cannot ingest/checkpoint/delete successors / 同一持久 Job UUID 通过唯一 attempt UUID/根重试；旧 attempt 不能导入/checkpoint/删除后继 | `PASS` |
| Heartbeat and short transactions / Heartbeat 与短事务 | A real long local child runs while parent heartbeat and an independent SQLite writer continue; process wait holds no SQLite transaction / 真实长运行本地 child 期间父进程 heartbeat 与独立 SQLite writer 持续；进程等待不持有 SQLite 事务 | `PASS` |
| Cooperative cancellation / 协作取消 | Pre-spawn/running cancel, lease fencing, repeated runner cancellation and a real between-batch ownership-guard barrier pass; runner/ingestion both join before unwind, and the second batch is fenced / spawn 前/运行中取消、lease fencing、重复 runner 取消及真实批次间 ownership-guard barrier 均通过；runner/ingestion 都先 join 再 unwind，第二批被 fencing | `PARTIAL` — deterministic post-child/pre-seal and post-seal/pre-ingest barriers remain missing / 仍缺少确定性 child 后/seal 前及 seal 后/导入前 barrier |
| Parent hard death and profile lock / 父进程硬死亡与 profile 锁 | Repository-owned helper hard-kill exercises parent liveness/control, child/grandchild exit and bounded account/profile recovery; Windows attach/start handshake is implemented / 仓库自有 helper 硬杀验证父进程 liveness/control、子/孙进程退出及有界账户/profile 恢复；已实现 Windows attach/start handshake | `PASS` |
| Ownership, ABA and ingestion / Ownership、ABA 与导入 | Exact owner/token/unexpired guard precedes every SyncRun mutation and each ingestion/checkpoint transaction / 每个 SyncRun 变更及每个导入/checkpoint 事务前执行精确 owner/token/未过期 guard | `PASS` |
| Waiting/failure mapping / Waiting/失败映射 | `ACCOUNT_BUSY → account_busy`, `TIMED_OUT → upstream_timeout`, `START_FAILED → upstream_unavailable`, `CONFIGURATION_FAILED → configuration_invalid`, `UPSTREAM_FAILED → temporary_upstream`, output/tree/receipt rejection → `output_security_failed`; `waiting_user`/`waiting_auth` do not spawn and require explicit resume / 采用左列固定映射；`waiting_user`/`waiting_auth` 不 spawn 且必须显式 resume | `PASS`; cancellation/lease loss propagates fencing and stale handlers do not finalize / 取消/lease 丢失传播 fencing，旧 handler 不收尾 |
| Seven-platform real offline protocol / 七平台真实离线协议 | `xhs`, `dy`, `ks`, `bili`, `wb`, `tieba`, `zhihu`: subscribe → tick → v3 write/load → real local fake child writes versioned JSONL → v2 receipt write/read → guarded ingest → retry/restart → idempotent replay / 七个平台：订阅 → tick → v3 写入/读取 → 真实本地 fake child 写版本化 JSONL → v2 回执写入/读取 → 受保护导入 → 重试/重启 → 幂等重放 | `PASS` — offline only / 仅离线通过 |
| Four-state cleanup / 四状态清理 | `ABSENT`, `REMOVED`, `QUARANTINED`, `UNRESOLVED`; unresolved cleanup creates fixed/redacted account block and fences future execution / `ABSENT`、`REMOVED`、`QUARANTINED`、`UNRESOLVED`；unresolved 清理创建固定/脱敏账户 block 并 fence 后续执行 | `PASS` for implemented state machine / 已实现状态机通过 |
| Complete failure secret-sink matrix / 完整失败密钥落点矩阵 | Existing cleanup/redaction/sentinel tests cover substantial cases / 现有清理/脱敏/哨兵测试覆盖大量场景 | `PARTIAL` — the full known-secret/nonzero/timeout/every-output-limit/receipt/cancel/lease-loss × retained-filesystem/SQLite/operator-sink cross-product is incomplete / 完整“失败类型 × 保留文件系统/SQLite/运维落点”交叉矩阵尚不完整 |
| Explicit CLI enablement / 显式 CLI 启用 | Default run leaves MediaCrawler Jobs untouched; `--enable-mediacrawler` and `--accept-mediacrawler-license` are separate, redaction-safe controls / 默认运行不处理 MediaCrawler Job；两个开关独立且输出脱敏 | `PASS` |

## Cancellation and secret-sink acceptance gaps / 取消与密钥落点验收缺口

AC6 remains `PARTIAL`. Pre-spawn cancellation, running cancellation, lease fencing, repeated cancellation during runner wait and deterministic cancellation at the second ingestion-batch guard are covered. The unified join helper now records the first cancellation, signals cancellable work once and shields through any later cancellation until runner/ingestion reaches a definite verdict. The between-batch test preserves the first committed batch and fences the second. Deterministic tests are still missing only at child exit/before seal and after seal/before ingest.

AC6 继续为 `PARTIAL`。已覆盖 spawn 前取消、运行中取消、lease fencing、runner 等待期间重复取消，以及第二个导入批次 guard 处的确定性取消。统一 join helper 现在会记录首次取消、只通知一次可取消工作，并在后续取消下继续 shield，直到 runner/ingestion 得出确定 verdict；批次间测试会保留已提交首批并 fence 第二批。现在只缺少 child 退出后/seal 前及 seal 后/导入前的确定性测试。

AC13 remains `PARTIAL`. Cleanup/redaction/sentinel evidence is substantial, but it does not yet exercise the complete cross-product of known-secret output, nonzero exit, timeout, every output limit, receipt rejection, cancel and lease loss against every retained filesystem, SQLite and operator sink.

AC13 继续为 `PARTIAL`。清理/脱敏/哨兵证据已较充分，但尚未针对所有保留文件系统、SQLite 与运维落点，完成已知密钥输出、非零退出、timeout、每种输出超限、回执拒绝、取消及 lease 丢失的完整交叉组合。

## Credential-bearing retained boundaries / 可能携带凭据的保留边界

- Ordinary active attempt roots must end as `ABSENT` or `REMOVED`. / 普通 active attempt 根必须以 `ABSENT` 或 `REMOVED` 收尾。
- If atomic isolation succeeds but no-follow scrubbing fails, exact unsafe evidence may remain only below ignored `.quarantine`. That directory is operator-controlled, tightened to `0700` on POSIX, expects an equivalent restrictive ACL elsewhere, and is explicitly excluded from zero-secret claims. / 若原子隔离成功但 no-follow 清理失败，精确不安全证据只能保留在已忽略的 `.quarantine` 下。该目录由操作员控制，POSIX 上收紧为 `0700`，其他系统预期使用等效受限 ACL，并明确排除在零密钥声明外。
- If neither removal nor isolation can be proven, `UNRESOLVED` creates only a fixed/redacted durable account/incident block outside the attempt root and hard-fences future secret resolution, run attachment, preparation and spawn. Raw cleanup errors and retained paths never enter operator output. / 若既不能证明删除也不能证明隔离，`UNRESOLVED` 只会在 attempt 根外创建固定/脱敏的持久账户/事件 block，并硬 fence 后续密钥解析、run attach、准备与 spawn。原始清理错误与保留路径不得进入运维输出。
- Persistent account browser profiles are also credential-bearing boundaries and are excluded from whole-tree zero-secret claims. / 持久账户 browser profile 同样属于可能携带凭据的边界，并排除在整树零密钥声明外。
- Repository ignore rules cover `.quarantine/`, `.cleanup-security-v1/` and account profile paths, including custom repository-local runtime roots. They prevent accidental Git tracking but are not a substitute for dedicated operator-controlled roots, ancestors and restrictive permissions/ACLs. / 仓库 ignore 规则覆盖 `.quarantine/`、`.cleanup-security-v1/` 与账户 profile 路径，包括仓库内的自定义 runtime 根；它们用于防止意外 Git 跟踪，但不能替代专用、由操作员控制的根目录/祖先及受限权限/ACL。

## Final root quality gates / 最终根质量门禁

The first full gate was deliberately interrupted after the late cancellation race was reproduced. It is not counted below. Every command in the table was rerun on the repaired tree; the retained-artifact gate is recorded separately in the next section.

后期重复取消竞态复现后，第一次全量门禁被主动中止且不计入下表。表中每条命令都已在修复后的代码树上重跑；保留产物门禁在下一节单独记录。

| Check / 检查 | Exact final command / 最终准确命令 | Status and evidence / 状态与证据 |
| --- | --- | --- |
| Locked dependencies / 锁定依赖 | `uv sync --all-groups --locked` | `PASS` — 58 packages resolved, 43 audited / 解析 58、审计 43 |
| Lint / 代码规范 | `uv run ruff check .` | `PASS` — `All checks passed!` |
| Format / 格式 | `uv run ruff format --check .` | `PASS` — 156 files / 156 个文件 |
| Strict types / 严格类型 | `uv run mypy src\media_sync` | `PASS` — 65 source files / 65 个源码文件 |
| Full tests and coverage / 全量测试与覆盖率 | `uv run pytest --cov=media_sync --cov-report=term` | `PASS` — 819 passed, 1 skipped in 212.99s; 79% branch-aware total / 819 项通过、1 项跳过、212.99 秒；分支感知总覆盖率 79% |
| Focused execution 0007 gate / 执行 0007 专项 | Exact eight-module command recorded above / 上方准确八模块命令 | `PASS` — 320 passed, 1 skipped in 128.64s / 320 项通过、1 项跳过、128.64 秒 |
| Build / 构建 | `uv build` | `PASS` — sdist and wheel / 源码包与 wheel |
| Packaged resources/database compatibility / 随包资源与数据库兼容 | `uv run pytest tests\integration\test_packaged_migrations.py -q` | `PASS` — 6 passed in 7.47s / 6 项通过、7.47 秒 |
| Documentation links / 文档链接 | `uv run python scripts\check_docs.py` | `PASS` — 44 Markdown files / 44 个 Markdown 文件 |
| Pinned upstreams / 锁定上游 | `uv run python scripts\check_upstreams.py` | `PASS` — 2 locked checkouts / 2 个锁定 checkout |
| Custom runtime ignore boundary / 自定义运行根 ignore 边界 | `git check-ignore -v --no-index -- custom-runtime/.quarantine/evidence.json custom-runtime/.cleanup-security-v1/account-blocks/xhs/account.json custom-runtime/accounts/xhs/00000000-0000-0000-0000-000000000000/profile/cookies.json .media-sync/verification/0007-closeout-sentinel-root` | `PASS` — all four paths matched the intended rules / 四个路径均匹配预期规则 |
| Patch whitespace / 补丁空白 | `git diff --check` | `PASS` — no output / 无输出 |
| Runtime artifacts untracked / 运行产物未跟踪 | `git ls-files -- archive exports jobs .media-sync dist` and `git status --short -- archive exports jobs .media-sync dist` | `PASS` — both emitted no lines / 均无输出 |
| Retained safe-artifact sentinel / 安全留存产物哨兵 | Exact 29-case allowlist and scans below / 下方精确 29-case allowlist 与扫描 | `PASS` — 29 passed; eight zero-match scans; 21 logical SQLite authority checks / 29 项通过；8 次零匹配；21 个 SQLite 逻辑权限检查 |

## Final retained safe-artifact sentinel / 最终安全留存产物哨兵

The authoritative retained root is `.media-sync/verification/0007-closeout-sentinel-root`. It was required not to exist before the run and was never deleted or replaced. The allowlist below expands to exactly 29 cases. It retains successful scheduled-handler roots, manifest/receipt evidence, temporary SQLite databases, captured pytest/operator output and local helper-process evidence without selecting deliberate quarantine/unresolved-retention negatives.

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

Observed pytest result: `29 passed in 40.90s`. Pytest created 19 Windows `current` directory symlinks. The first generic “reject every reparse point” postcondition therefore stopped before scanning. Each alias was then checked to be a single directory symlink whose existing target is inside the sentinel root and has the same parent; every real target directory is independently present and scanned. No alias escaped the root. The retained tree was not rerun, deleted or rewritten; the scan resumed against that exact evidence.

实测 pytest 结果为 `29 passed in 40.90s`。Pytest 在 Windows 上创建了 19 个 `current` 目录符号链接，因此首次通用“拒绝全部 reparse point”后置条件在扫描前停止。随后逐个证明这些别名都是单目标目录符号链接，现存目标位于留存根内且与别名同父；每个真实目标目录也独立存在并参与扫描，没有任何别名逃逸。留存树没有被重跑、删除或改写；扫描在同一份精确证据上继续。

The resumed gate used `rg --hidden --no-ignore --text --fixed-strings` over every real file for eight generated values: the fixture Cookie, supervision Cookie, parse Cookie, scheduler-handler secret, SQLite sink secret, signed-query secret, signed-creator token and late-bridge attempt secret. All eight returned `rg` exit `1`, meaning a successful zero-match. A read-only SQLite query checked every database containing `jobs` and found no logical row with a non-null `lease_owner` or `lease_token` across 21 databases. Behavioral tests separately prove that scheduler authority never enters the child boundary. Scoped `git ls-files` and `git status` emitted no lines.

恢复后的门禁使用 `rg --hidden --no-ignore --text --fixed-strings` 对全部真实文件扫描 8 个生成值：夹具 Cookie、监督 Cookie、parse Cookie、scheduler-handler 密钥、SQLite 落点密钥、签名 query 密钥、签名作者 token 与 bridge 后期失败的 attempt 密钥。8 次均返回 `rg` 退出码 `1`，即扫描成功且零匹配。只读 SQLite 查询检查了所有含 `jobs` 表的数据库，在 21 个数据库中均未发现逻辑上 `lease_owner` 或 `lease_token` 非空的行；行为测试另行证明 scheduler 权限绝不进入 child 边界。限定范围的 `git ls-files` 与 `git status` 均无输出。

Final retained result / 最终留存结果：

```text
CLOSEOUT_PASS cases=29 pytest_seconds=40.90 scans=8 sqlite_authority=PASS aliases=19
files=279 directories=364 bytes=5958937
```

The exact retained-negative functions excluded from this safe-artifact allowlist were:

本安全产物 allowlist 明确排除的留存负向函数为：

- Supervision / 进程监督：`test_runner_hard_stops_and_records_redacted_block_when_attempt_cleanup_is_unresolved`, `test_cleanup_is_unresolved_when_atomic_quarantine_and_direct_removal_both_fail`, `test_cleanup_quarantines_when_post_move_scrub_is_denied`, `test_existing_quarantine_directory_mode_is_tightened_before_isolation`, `test_quarantined_cleanup_returns_only_fixed_operator_status`.
- Scheduled handler / 定时 handler：`test_unresolved_cleanup_fences_current_and_recovery_without_successor_or_spawn`, `test_cleanup_incident_persistence_failure_still_fences_without_terminal_write`, `test_lease_loss_cancels_and_joins_runner_before_worker_returns`, `test_task_cancellation_signals_and_joins_runner`, `test_repeated_task_cancellation_still_joins_runner_before_unwind`, `test_repeated_cancellation_between_ingestion_batches_joins_before_unwind`, `test_repeated_cancellation_during_unresolved_cleanup_records_block_before_unwind`, `test_repeated_cancellation_during_untrusted_recovery_records_block`.
- CLI projection fixture / CLI 投影夹具：`test_scheduler_controls_are_bounded_and_redact_every_output_sink` intentionally stores raw redaction fixtures in temporary SQLite and is covered by the full suite, not by a whole-tree zero-match claim. / 会故意把原始脱敏夹具写入临时 SQLite，由全量套件覆盖，不用于整树零匹配声明。

The zero-match claim applies only to the eight exact generated values in this 29-case safe-artifact tree. It does not claim that arbitrary unknown secrets cannot exist in a real browser profile or deliberate quarantine/unresolved evidence. / 零匹配声明只适用于本 29-case 安全产物树中的 8 个精确生成值；不宣称真实 browser profile 或故意 quarantine/unresolved 证据中不可能存在任意未知密钥。

## Live qualification / 真人资格验证

| Platform / 平台 | QR login / 二维码登录 | Cookie login / Cookie 登录 | Saved session / 保存会话 | Live creator traffic / 真人作者流量 | Live CDN retrieval / 真人 CDN 获取 | Real Emby/Jellyfin scan/playback / 真实 Emby/Jellyfin 扫描/播放 |
| --- | --- | --- | --- | --- | --- | --- |
| `xhs` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `dy` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `ks` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `bili` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `wb` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `tieba` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `zhihu` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

## Deferred implementation / 延期实现

Scheduled backfill, signed-locator refresh, real CDN/media retrieval, automatic sync → download → export planning, per-request HTTP spacing, QR/challenge presentation UX, REST, resident production supervision, Docker, distributed HA/PostgreSQL and live Emby/Jellyfin operations are outside execution 0007. The pinned-shape evidence proves only `CRAWLER_MAX_SLEEP_SEC` configuration with `MAX_CONCURRENCY_NUM=1`, not spacing for every request.

定时 backfill、签名 locator refresh、真实 CDN/媒体获取、自动 sync → download → export 规划、逐 HTTP 请求间隔、二维码/challenge 展示 UX、REST、常驻生产守护、Docker、分布式 HA/PostgreSQL 及真人 Emby/Jellyfin 运维不属于执行 0007。锁定形状证据只证明 `CRAWLER_MAX_SLEEP_SEC` 与 `MAX_CONCURRENCY_NUM=1` 的配置，不证明每次请求都按间隔执行。
