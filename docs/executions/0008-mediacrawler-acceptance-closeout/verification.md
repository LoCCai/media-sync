# Execution 0008 verification / 执行 0008 验证

- Verification state / 验证状态：`PASS` for the offline acceptance scope / 离线验收范围 `PASS`
- Verification date / 验证日期：2026-08-30
- Plan commit / 计划提交：`f0c6015`
- Implementation commit / 实现提交：this commit / 本次提交
- Network/account policy / 网络与账户策略：offline fixtures and repository-owned helper processes only; no browser, real credential, platform/CDN endpoint or Emby/Jellyfin server / 仅离线夹具与仓库自有 helper process；不使用浏览器、真实凭据、平台/CDN 端点或 Emby/Jellyfin 服务器

## Verdict / 验证结论

Execution 0008 passes its offline successor closeout for execution 0007 AC6 and AC13. Both missing cancellation windows are now deterministic, and the exact eleven-failure × three-sink matrix proves 33 cells. The full branch-aware suite, focused and negative-boundary gates, build, repository checks and the one-shot retained-artifact gate all pass.

执行 0008 通过针对执行 0007 AC6 与 AC13 的离线继任收口。两个缺失取消窗口现均有确定性证明，精确“11 种失败 × 3 类落点”矩阵证明 33 个 cell。完整分支感知套件、专项及负向边界门禁、构建、仓库检查与一次性留存产物门禁均通过。

This verdict does not alter execution 0007's historical `PARTIAL` records and does not qualify any live platform, CDN or media-server behavior.

本结论不改写执行 0007 历史记录中的 `PARTIAL`，也不验收任何真人平台、CDN 或媒体服务器行为。

## Behavior evidence / 行为证据

| Scope / 范围 | Evidence and result / 证据与结果 | Status / 状态 |
| --- | --- | --- |
| Child-exit/pre-seal cancellation / Child 退出后、密封前取消 | Real helper returns `0` and its full tree joins; the test requests cancellation while the final-inspection barrier is held, then releases inspection; the runner observes cancellation before receipt publication; receipt writer, normalization and ingestion remain unentered; attempt cleanup and lock reacquisition pass / 真实 helper 返回 `0` 且完整进程树 join；测试在最终检查 barrier 阻塞时请求取消，再释放检查；runner 在发布回执前观察取消；回执 writer、归一化与导入均未进入；attempt 清理与锁重获通过 | `PASS` |
| Post-seal/pre-ingest cancellation / 密封后、导入前取消 | A valid receipt is visible; both single and repeated cancellation join the protected normalizer before unwind; Content/Asset/checkpoint/success writes remain zero / 有效回执可见；单次与重复取消均在 unwind 前 join 受保护 normalizer；Content/Asset/checkpoint/成功写入保持为零 | `PASS` |
| Closed failure rows / 封闭失败行 | Exact set equality for `known_secret_echo`, `nonzero_exit`, `timeout`, `output_bytes`, `output_items`, `output_files`, `output_line_bytes`, `output_tree`, `receipt_rejected`, `cancellation`, `lease_loss` / 对上述 11 个精确失败值执行集合等式检查 | `PASS` |
| Sentinel injection / 哨兵注入 | Cleanup observers prove every row's generated sentinel exists in attempt-private output before cleanup; no row can pass by omitting its injection / 清理观察器证明每行生成哨兵在清理前存在于 attempt 私有输出；任何行都不能因未注入而空通过 | `PASS` |
| Filesystem sink / 文件系统落点 | Ordinary roots end `ABSENT`/`REMOVED`; final traversal scans contents and path names, rejects traversal errors and scans hidden/ignored real files without exclusions / 普通根终态为 `ABSENT`/`REMOVED`；最终遍历扫描内容与路径名、拒绝遍历错误，并无排除地扫描隐藏/忽略真实文件 | `PASS` |
| SQLite sink / SQLite 落点 | Logical text/JSON plus every retained database and sidecar are scanned fail-closed; Job/SyncRun/checkpoint/Content/Asset and platform/account authority match each row's fixed disposition / 逻辑文本/JSON 及全部保留数据库和 sidecar 均 fail-closed 扫描；Job/SyncRun/checkpoint/Content/Asset 与平台/账户权限符合各行固定 disposition | `PASS` |
| Operator sink / 运维落点 | Serialized results, Job/worker/lane CLI projections, captured output and exception/result `str`/`repr` contain no sentinel, lease authority, runtime root or raw cleanup error / 序列化结果、Job/worker/lane CLI 投影、捕获输出及异常/结果 `str`/`repr` 不含哨兵、lease 权限、运行根或原始清理错误 | `PASS` |
| Matrix completeness / 矩阵完整性 | Exact Cartesian product: 11 failure rows × 3 named sinks = 33 cells / 精确笛卡尔积：11 个失败行 × 3 个命名落点 = 33 cell | `PASS` |
| Negative boundaries / 负向边界 | Selected saved-profile, quarantine and unresolved-cleanup tests preserve their credential-bearing classification and prove fixed markers/unconditional fencing; raw cleanup-error evidence comes from this gate / 选定的保存 profile、quarantine 与 unresolved 清理测试保留其可能携带凭据分类，并证明固定 marker/无条件 fencing；原始 cleanup error 证据来自本门禁 | `PASS` |
| Protocol compatibility / 协议兼容 | Seven-platform v3/v2 forward protocol, retry/restart, parent supervision and byte-exact immutable manual v2/v1 compatibility remain green / 七平台 v3/v2 forward 协议、重试/重启、父进程监督及逐字节精确不可变的手工 v2/v1 兼容保持通过 | `PASS` |

## Exact focused gates / 准确专项门禁

### Cancellation and matrix core / 取消与矩阵核心

The exact gate selected one runner pre-seal contract, one handler pre-seal contract, the two parameterized post-seal cases, matrix completeness and all eleven matrix rows:

准确门禁选择 1 个 runner 密封前契约、1 个 handler 密封前契约、2 个参数化 seal 后 case、矩阵完整性及全部 11 个矩阵行：

```powershell
uv run pytest `
  tests/contract/test_mediacrawler_supervision.py::test_cancel_after_successful_tree_join_never_starts_receipt_seal `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_child_exit_pre_seal_cancellation_never_enters_normalization_or_ingestion `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_post_seal_pre_ingest_cancellation_joins_before_unwind `
  tests/integration/test_mediacrawler_security_matrix.py::test_mediacrawler_security_matrix_declares_exactly_thirty_three_cells `
  tests/integration/test_mediacrawler_security_matrix.py::test_mediacrawler_failure_matrix_checks_every_sink
```

Result / 结果：`PASS` — exit `0`; `16 passed in 29.08s`.

### Scanner contracts and related modules / 扫描器契约与相关模块

| Scope / 范围 | Exact command / 准确命令 | Result / 结果 |
| --- | --- | --- |
| Complete matrix module / 完整矩阵模块 | `uv run pytest tests/integration/test_mediacrawler_security_matrix.py` | `PASS` — exit `0`; `14 passed in 24.29s` |
| Related MediaCrawler modules / 相关 MediaCrawler 模块 | `uv run pytest tests/contract/test_mediacrawler_bridge.py tests/contract/test_mediacrawler_supervision.py tests/integration/test_mediacrawler_scheduler_handler.py tests/integration/test_mediacrawler_security_matrix.py` | `PASS` — exit `0`; `151 passed, 1 skipped` |

The matrix module count is one completeness case, two fail-closed scanner contracts and eleven failure rows.

矩阵模块数量由 1 个完整性 case、2 个 fail-closed 扫描器契约及 11 个失败行组成。

### Credential-bearing negative boundary / 可能携带凭据负向边界

The exact 13-function gate below contains the saved-session/profile contract; five quarantine/unresolved supervision functions; and seven handler authority/cancellation functions. The final recovery function expands to two cases, so the command collects 14 cases. It deliberately remains outside ordinary safe-tree zero-match evidence.

下方精确 13 函数门禁包含保存会话/profile 契约、5 个 quarantine/unresolved supervision 函数，以及 7 个 handler 权限/取消函数。最后一个恢复函数展开为 2 个 case，因此命令共收集 14 个 case。它有意不纳入普通安全树零匹配证明。

```powershell
uv run pytest `
  tests/contract/test_mediacrawler_bridge.py::test_saved_session_and_profile_path_isolation `
  tests/contract/test_mediacrawler_supervision.py::test_runner_hard_stops_and_records_redacted_block_when_attempt_cleanup_is_unresolved `
  tests/contract/test_mediacrawler_supervision.py::test_cleanup_is_unresolved_when_atomic_quarantine_and_direct_removal_both_fail `
  tests/contract/test_mediacrawler_supervision.py::test_cleanup_quarantines_when_post_move_scrub_is_denied `
  tests/contract/test_mediacrawler_supervision.py::test_existing_quarantine_directory_mode_is_tightened_before_isolation `
  tests/contract/test_mediacrawler_supervision.py::test_quarantined_cleanup_returns_only_fixed_operator_status `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_unresolved_cleanup_fences_current_and_recovery_without_successor_or_spawn `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_cleanup_incident_persistence_failure_still_fences_without_terminal_write `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_lease_loss_cancels_and_joins_runner_before_worker_returns `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_task_cancellation_signals_and_joins_runner `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_repeated_task_cancellation_still_joins_runner_before_unwind `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_repeated_cancellation_during_unresolved_cleanup_records_block_before_unwind `
  tests/integration/test_mediacrawler_scheduler_handler.py::test_repeated_cancellation_during_untrusted_recovery_records_block
```

Result / 结果：`PASS` — exit `0`; `13 passed, 1 skipped in 7.31s`. The skip is the Windows-inapplicable POSIX mode-bit boundary / skip 为 Windows 不适用的 POSIX mode-bit 边界。

## Full quality gates / 完整质量门禁

| Check / 检查 | Exact command / 准确命令 | Result / 结果 |
| --- | --- | --- |
| Locked dependencies / 锁定依赖 | `uv sync --all-groups --locked` | `PASS` — exit `0`; `Resolved 58 packages`; `Audited 43 packages` |
| Lint / 代码规范 | `uv run ruff check .` | `PASS` — exit `0` |
| Format / 格式 | `uv run ruff format --check .` | `PASS` — exit `0`; `162 files already formatted` |
| Strict types / 严格类型 | `uv run mypy src/media_sync` | `PASS` — exit `0`; `Success: no issues found in 65 source files` |
| Full branch-aware suite / 完整分支感知套件 | `uv run pytest --cov=media_sync --cov-report=term` | `PASS` — exit `0`; `838 collected`; `837 passed, 1 skipped in 248.20s`; total branch-aware coverage `79%` |
| Build / 构建 | `uv build` | `PASS` — exit `0`; wheel and source distribution built / 已构建 wheel 与源码分发包 |
| Packaged migrations/resources / 随包迁移/资源 | Covered by the full suite and built wheel/sdist; no Alembic revision was added / 由完整套件及 wheel/sdist 构建覆盖；未新增 Alembic revision | `PASS` |
| Documentation links / 文档链接 | `uv run python scripts/check_docs.py` | `PASS` — exit `0`; `Documentation links OK (48 Markdown files checked).` |
| Locked upstreams / 锁定上游 | `uv run python scripts/check_upstreams.py` | `PASS` — exit `0`; `Upstreams OK (2 locked checkouts verified).` |
| Patch whitespace / 补丁空白 | `git diff --check` | `PASS` — exit `0`; no output / 无输出 |

The single full-suite skip is the POSIX mode-bit boundary that is not applicable on Windows. No browser, network, real platform account, CDN or media server is used by these gates.

完整套件唯一 skip 是 Windows 不适用的 POSIX mode-bit 边界。上述门禁未使用浏览器、网络、真人平台账户、CDN 或媒体服务器。

## Authoritative retained-artifact gate / 权威留存产物门禁

The complete one-shot recipe is frozen in [`closeout-gate.ps1`](closeout-gate.ps1). Its canonical LF repository bytes are Git blob `6f5e8119de66a36f0f93f75a5f5e27ef1bf2ec18`, SHA-256 `d56f9108c2f5d2ddc01d8d9da26657ef5f95a25024017d52c6c169db7016c853`; the checkout may render PowerShell files with CRLF according to `.gitattributes`. It preserves the exact 22 function nodes, pytest invocation, twelve value/prefix scans, fail-closed path/content traversal, Windows alias validation, SQLite logical/sidecar and eleven-row authority checks, exact retained-tree statistics, scoped Git checks and receipt write. The authoritative run created the previously absent ignored root `.media-sync/verification/0008-closeout-sentinel-root` with a fresh pytest `--basetemp` and retained JUnit, pytest output and `closeout-sentinel-PASS.txt`. The root must not be deleted, rebuilt or used for another authoritative run. The execution 0007 retained root was not touched.

完整一次性流程冻结在 [`closeout-gate.ps1`](closeout-gate.ps1)。其规范 LF 仓库字节为 Git blob `6f5e8119de66a36f0f93f75a5f5e27ef1bf2ec18`，SHA-256 为 `d56f9108c2f5d2ddc01d8d9da26657ef5f95a25024017d52c6c169db7016c853`；checkout 可按 `.gitattributes` 把 PowerShell 文件渲染为 CRLF。脚本保存精确 22 个函数节点、pytest 调用、12 项值/前缀扫描、fail-closed 路径/内容遍历、Windows alias 验证、SQLite 逻辑/sidecar 与 11 行权限检查、精确留存树统计、限定 Git 检查及回执写入。权威运行使用全新 pytest `--basetemp` 创建此前不存在且已忽略的 `.media-sync/verification/0008-closeout-sentinel-root`，并保留 JUnit、pytest 输出及 `closeout-sentinel-PASS.txt`。不得删除、重建该根或再次用它执行权威运行；执行 0007 的留存根未被触碰。

Canonical one-shot invocation from the repository root / 从仓库根执行的规范一次性调用：

```powershell
pwsh -NoProfile -File docs/executions/0008-mediacrawler-acceptance-closeout/closeout-gate.ps1
```

This invocation is now documentary only: the script's first write-side precondition rejects the existing retained root. It was not rerun while transcribing the fixed recipe. Only PowerShell and embedded-Python syntax were parsed afterward; neither syntax check executes the gate or reads/writes the retained root.

该调用现在只作记录：脚本的第一个写侧前置条件会拒绝已存在的留存根。固定流程转录后没有重跑；之后只解析 PowerShell 与内嵌 Python 语法，两项语法检查均不执行门禁，也不读写留存根。

Exact syntax-only checks / 准确语法检查：

```powershell
$path = (Resolve-Path -LiteralPath 'docs/executions/0008-mediacrawler-acceptance-closeout/closeout-gate.ps1').Path
$tokens = $null
$errors = $null
[void][Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { $errors | Format-List; exit 1 }

$lines = Get-Content -LiteralPath $path
$python = ($lines[96..345] -join [Environment]::NewLine)
$python | uv run python -c "import sys; compile(sys.stdin.read(), 'closeout-gate-embedded.py', 'exec'); print('Embedded Python syntax OK')"
```

Result / 结果：`PASS` — PowerShell parser reported zero errors; embedded Python printed `Embedded Python syntax OK`; neither command invoked the gate / PowerShell parser 报告零错误；内嵌 Python 输出 `Embedded Python syntax OK`；两条命令均未调用门禁。

| Measurement / 指标 | Exact result / 准确结果 |
| --- | ---: |
| Gate process / 门禁进程 | `CLOSEOUT_PASS`, exit `0` |
| Function nodes / 函数节点 | 22 |
| Pytest cases / Pytest case | 45 |
| Pytest result / Pytest 结果 | `45 passed in 69.82s` |
| Gate wall time / 门禁墙钟时间 | `71.41s` |
| Matrix cases / 矩阵 case | 12 |
| Matrix cells / 矩阵 cell | 33 |
| Exact value/prefix scans / 精确值或前缀扫描 | 12 |
| SQLite authority rows / SQLite 权限行 | 11 |
| SQLite files / SQLite 文件 | 35 |
| SQLite sidecars / SQLite sidecar | 22 |
| Validated pytest `current` aliases / 已验证 pytest `current` alias | 24 |
| Real files / 真实文件 | 370 |
| Real directories including root / 含根的真实目录 | 483 |
| Retained bytes / 留存字节 | 10,104,859 |
| Tracked files below root / 根下已跟踪文件 | 0 |
| Git status lines below root / 根下 Git 状态行 | 0 |

All 24 Windows pytest `current` aliases were proved to have exactly one existing same-parent target inside the retained root. Every real target was independently enumerated and scanned. The final scan covered all hidden and ignored real files and path names with no exclusions. Scanner errors, SQLite locks at final scan, non-regular databases, unreadable sidecars or traversal failures make the gate fail closed.

全部 24 个 Windows pytest `current` alias 均被证明只指向一个现存、同父且位于留存根内的目标；每个真实目标均独立枚举与扫描。最终扫描无排除地覆盖全部隐藏/忽略真实文件及路径名。扫描器错误、最终扫描时 SQLite 锁定、非普通数据库、不可读 sidecar 或遍历失败都会使门禁 fail-closed。

The twelve zero-match values/prefixes combine the eight execution 0007 safe-artifact fixtures with four execution 0008 matrix/pre-seal runtime sentinels. They are test-only values, not real credentials. `QUARANTINED`, `UNRESOLVED` and persistent browser profiles are intentionally excluded and covered by the negative-boundary gate instead.

12 个零匹配值/前缀由执行 0007 的 8 个安全产物夹具与执行 0008 的 4 个矩阵/密封前运行时哨兵组成；它们只用于测试，不是真实凭据。`QUARANTINED`、`UNRESOLVED` 与持久 browser profile 被有意排除，改由负向边界门禁覆盖。

### Exact retained-negative exclusions / 精确留存负向排除

The 22-node allowlist is closed; it is not a module-level selection with a fragile `-k` exclusion. The following credential-bearing, authority-retaining or deliberate scanner-fixture functions are therefore named explicitly outside the whole-tree zero-match claim:

22-node allowlist 是封闭集合，不是依赖脆弱 `-k` 排除的模块级选择。下列可能携带凭据、保留权限或故意制造扫描器夹具的函数因此被明确排除在整树零匹配声明之外：

- Persistent profile / 持久 profile：`tests/contract/test_mediacrawler_bridge.py::test_saved_session_and_profile_path_isolation`.
- Supervision quarantine/unresolved / 监督 quarantine/unresolved：`test_runner_hard_stops_and_records_redacted_block_when_attempt_cleanup_is_unresolved`, `test_cleanup_is_unresolved_when_atomic_quarantine_and_direct_removal_both_fail`, `test_cleanup_quarantines_when_post_move_scrub_is_denied`, `test_existing_quarantine_directory_mode_is_tightened_before_isolation`, `test_quarantined_cleanup_returns_only_fixed_operator_status` in `tests/contract/test_mediacrawler_supervision.py`.
- Handler authority/cleanup / Handler 权限/清理：`test_unresolved_cleanup_fences_current_and_recovery_without_successor_or_spawn`, `test_cleanup_incident_persistence_failure_still_fences_without_terminal_write`, `test_lease_loss_cancels_and_joins_runner_before_worker_returns`, `test_task_cancellation_signals_and_joins_runner`, `test_repeated_task_cancellation_still_joins_runner_before_unwind`, `test_repeated_cancellation_between_ingestion_batches_joins_before_unwind`, `test_repeated_cancellation_during_unresolved_cleanup_records_block_before_unwind`, `test_repeated_cancellation_during_untrusted_recovery_records_block` in `tests/integration/test_mediacrawler_scheduler_handler.py`.
- Deliberate CLI redaction fixture / 故意 CLI 脱敏夹具：`tests/unit/test_cli.py::test_scheduler_controls_are_bounded_and_redact_every_output_sink`; it intentionally persists three raw projection fixtures in temporary SQLite and is covered by the full suite, not the zero-match retained tree / 它会故意向临时 SQLite 持久化 3 个原始投影夹具，由完整套件而非零匹配留存树覆盖。
- Fail-closed scanner fixtures / Fail-closed 扫描器夹具：`test_filesystem_sink_scanner_checks_path_names_and_fails_closed` and `test_sqlite_sink_scanner_requires_a_regular_database_and_sidecars` in `tests/integration/test_mediacrawler_security_matrix.py`; they deliberately create rejected path/sidecar conditions and are covered by the 14-case matrix-module gate / 它们会故意创建应拒绝的路径/sidecar 条件，由 14-case 矩阵模块门禁覆盖。

The exact negative-boundary command above selects the profile, five supervision and seven handler functions needed for the credential/authority claim. The additional between-batch, CLI and scanner functions remain explicitly outside the retained root and are covered by the related-module or full-suite gates.

上方精确负向边界命令选择凭据/权限声明所需的 profile、5 个 supervision 与 7 个 handler 函数；额外的批次间、CLI 与扫描器函数继续明确位于留存根之外，并由相关模块或完整套件门禁覆盖。

## Live qualification / 真人资格验证

| Platform / 平台 | QR login / 二维码登录 | Cookie login / Cookie 登录 | Saved session / 保存会话 | Creator scheduled run / 作者定时运行 | Live CDN / 真人 CDN | Real Emby/Jellyfin / 真实 Emby/Jellyfin |
| --- | --- | --- | --- | --- | --- | --- |
| `xhs` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `dy` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `ks` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `bili` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `wb` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `tieba` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `zhihu` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

Phone login remains unsupported rather than merely untested. The offline fake-child and fixture results must not be represented as live compatibility.

手机号登录仍属于不支持，而不是仅未测试；不得把离线 fake-child 与夹具结果写成真人兼容性。

## Deferred implementation and residual boundary / 延期实现与剩余边界

Signed-locator refresh remains unimplemented through execution 0008 and is execution 0009 scope. Successful sealed v3 attempt JSONL may still contain an unknown short-lived signed query that the parent could not pre-register; it remains an explicit credential-bearing temporary boundary until execution 0009 implements refresh plus successful/recovery terminal cleanup or isolation.

签名 locator refresh 在执行 0008 结束时仍未实现，属于执行 0009。成功密封的 v3 attempt JSONL 仍可能含父进程无法预先登记的未知短效签名 query；在执行 0009 实现 refresh 及成功/恢复终态清理或隔离前，它继续作为明确的可能携带凭据临时边界。

Durable automatic `sync → download → Emby` planning remains execution 0010 scope. Real platform/CDN/Emby qualification, downloadable assets for `wb`/`tieba`/`zhihu`, platform derivatives, per-request HTTP spacing, bounded live pagination, QR/challenge UX, REST, resident supervision, Docker and HA/PostgreSQL remain deferred or `NOT_RUN` according to their truthful category.

持久自动 `sync → download → Emby` 规划仍属于执行 0010。真人平台/CDN/Emby 验收、`wb`/`tieba`/`zhihu` 可下载资产、平台衍生物、逐 HTTP 请求间隔、真人分页有界性、二维码/challenge UX、REST、常驻监督、Docker 及 HA/PostgreSQL 按各自真实类别继续延期或保持 `NOT_RUN`。
