# Execution 0007 verification / 执行 0007 验证

- Verification state / 验证状态：`NOT_RUN`
- Planning date / 计划日期：2026-08-30
- Network/account policy / 网络与账户策略：offline fixtures and local helper processes only; no browser, real credential, platform/CDN endpoint or Emby/Jellyfin server / 仅离线夹具与本地辅助进程；不使用浏览器、真实凭据、平台/CDN 端点或 Emby/Jellyfin 服务器
- Implementation state / 实现状态：`NOT_RUN`

This file is a planned verification contract, not execution evidence. None of the execution 0007 commands, tests, process hard-kill scenarios, sentinel scans or live qualification rows below has run. Execution 0006 results must not be reused as proof for execution 0007.

本文件是计划验证契约，不是执行证据。下列执行 0007 命令、测试、进程硬杀场景、哨兵扫描及真人资格行均未运行；不得把执行 0006 的结果复用为执行 0007 证据。

## Planning-baseline checks / 计划基线检查

These checks ran after the four planned records and project indexes were written. They qualify only the documentation-only planning baseline; every implementation, behavioral and live row below remains `NOT_RUN`.

以下检查在四份计划记录与项目索引写入后运行，只验收纯文档计划基线；下方全部实现、行为及真人资格行继续保持 `NOT_RUN`。

| Check / 检查 | Exact command / 准确命令 | Result / 结果 |
| --- | --- | --- |
| Documentation links / 文档链接 | `uv run python scripts/check_docs.py` | `PASS` — exit `0`; `Documentation links OK (44 Markdown files checked).` |
| Locked upstreams / 锁定上游 | `uv run python scripts/check_upstreams.py` | `PASS` — exit `0`; `Upstreams OK (2 locked checkouts verified).` |
| Patch whitespace / 补丁空白 | `git diff --check` | `PASS` — exit `0`; no output / 无输出 |

## Planned behavior evidence / 计划行为证据

| Scope / 范围 | Required evidence / 必需证据 | Status / 状态 |
| --- | --- | --- |
| Policy v1 / 策略 v1 | Closed fields, explicit acknowledgements, numeric bounds, opaque refs only, hostile/legacy policy rejection / 封闭字段、显式确认、数字边界、仅不透明 ref、恶意/legacy 策略拒绝 | `NOT_RUN` |
| Manifest v3/receipt v2 / Manifest v3/回执 v2 | Strict writer, exact identity binding, unknown-field rejection and v2/v1 immutable dual-read / 严格 writer、精确身份绑定、未知字段拒绝及 v2/v1 不可变双读 | `NOT_RUN` |
| Pinned upstream shape / 锁定上游形状 | Faithful `parse_cmd()` configuration order, dummy Cookie non-disclosure, exact delay binding and downloads disabled / 忠实 `parse_cmd()` 配置顺序、虚拟 Cookie 不泄漏、精确延迟绑定及下载关闭 | `NOT_RUN` |
| Attempt isolation / Attempt 隔离 | One scheduler Job retries across distinct roots; stale attempt cannot seal, ingest or delete successor / 同一 scheduler Job 在不同根重试；旧 attempt 不能密封、导入或删除后继 | `NOT_RUN` |
| Heartbeat and short transactions / Heartbeat 与短事务 | Long fake child plus independent SQLite writer; exact lease renewal continues off loop / 长 fake child 加独立 SQLite writer；精确续租移出事件循环并持续运行 | `NOT_RUN` |
| Cooperative cancellation / 协作取消 | Barriers before spawn, during run, before seal, before ingest and between batches; tree joined and no post-loss writes / spawn 前、运行中、seal 前、导入前及批次间 barrier；整树 join 且所有权丢失后零写入 | `NOT_RUN` |
| Parent hard death / 父进程硬死亡 | Exact helper worker PID is hard-killed; child/grandchild exit, account/profile lock excludes overlap, bounded recovery / 精确硬杀 helper worker PID；子/孙进程退出、账户/profile 锁阻止重叠并有界恢复 | `NOT_RUN` |
| Ownership and ABA / Ownership 与 ABA | Independent SQLite cancel/reclaim, exact SyncRun attachment, same-session batch guards and one durable winner / 独立 SQLite cancel/reclaim、精确 SyncRun attach、同 session 批次 guard 与唯一持久胜者 | `NOT_RUN` |
| Failure mapping / 失败映射 | Every fixed process result maps to the closed scheduler vocabulary; raw exceptions/results never persist / 每个固定进程结果映射到封闭 scheduler 词表；原始异常/结果不持久化 | `NOT_RUN` |
| Secret-bearing artifact cleanup / 含密钥产物清理 | Known-secret echo plus nonzero/timeout/limit/receipt/cancel failures leave no attempt-owned sentinel bytes after return/recovery / 已知密钥回显及非零/timeout/超限/回执/取消失败在返回/恢复后不留 attempt-owned 哨兵字节 | `NOT_RUN` |
| Seven-platform offline flow / 七平台离线流程 | Mocked process plus versioned fixtures for `xhs`, `dy`, `ks`, `bili`, `wb`, `tieba`, `zhihu`; forward restart/retry identity / 七平台 mock 进程与版本化夹具；forward 重启/重试身份 | `NOT_RUN` |

## Planned quality gates / 计划质量门禁

The command set will be finalized after implementation so paths and test modules match the delivered tree. Commands listed here are planned entry points only; each result remains `NOT_RUN` until its exact final invocation, exit code, count, timing and material output are recorded.

命令集合会在实现后根据实际目录与测试模块定稿。此处只列计划入口；在记录准确最终命令、退出码、数量、耗时及重要输出前，所有结果保持 `NOT_RUN`。

| Check / 检查 | Planned command or scope / 计划命令或范围 | Status / 状态 |
| --- | --- | --- |
| Locked dependencies / 锁定依赖 | `uv sync --all-groups --locked` | `NOT_RUN` |
| Lint / 代码规范 | `uv run ruff check .` | `NOT_RUN` |
| Format / 格式 | `uv run ruff format --check .` | `NOT_RUN` |
| Strict types / 严格类型 | `uv run mypy src/media_sync` | `NOT_RUN` |
| Full branch-aware suite / 全量分支感知套件 | `uv run pytest --cov=media_sync --cov-report=term` | `NOT_RUN` |
| Protocol and legacy compatibility / 协议与 legacy 兼容 | Manifest/receipt/policy contract and ingestion suites / Manifest/receipt/policy 契约与导入套件 | `NOT_RUN` |
| Supervision and ownership / 监督与 ownership | Heartbeat, cancel, parent-death, exact guard and ABA integration suites / Heartbeat、取消、父死亡、精确 guard 与 ABA 集成套件 | `NOT_RUN` |
| Seven-platform restart / 七平台重启 | Mocked scheduled-handler and versioned-fixture integration suite / Mock 定时 handler 与版本化夹具集成套件 | `NOT_RUN` |
| Secret sinks and retained artifacts / 密钥落点与保留产物 | Reproducible ignored-root sentinel generation plus byte scans / 可复现忽略根哨兵生成与字节扫描 | `NOT_RUN` |
| Build / 构建 | `uv build` | `NOT_RUN` |
| Packaged resources and database compatibility / 随包资源与数据库兼容 | Source and unpacked-wheel resource tests; migration tests only if a real schema revision is introduced / 源码与解包 wheel 资源测试；仅在引入真实 schema revision 时运行对应迁移测试 | `NOT_RUN` |
| Documentation / 文档 | `uv run python scripts/check_docs.py` | `NOT_RUN` |
| Pinned upstreams / 锁定上游 | `uv run python scripts/check_upstreams.py` | `NOT_RUN` |
| Patch whitespace / 补丁空白 | `git diff --check` | `NOT_RUN` |
| Runtime artifacts untracked / 运行产物未跟踪 | Scoped `git status`, `git ls-files` and ignore checks for generated roots / 对生成根执行限定 `git status`、`git ls-files` 与 ignore 检查 | `NOT_RUN` |

## Planned sentinel rules / 计划哨兵规则

- Tests use generated dummy Cookie, signed creator-reference, raw exception, hostile status and scheduler-authority sentinels only. No configured user secret is resolved. / 测试只使用生成的虚拟 Cookie、签名作者引用、原始异常、恶意状态及 scheduler 权限哨兵；不解析用户配置的密钥。
- Exact scans cover SQLite, Job/lane/operator projections, manifests/receipts and returned successful/failed attempt roots. A negative test may intentionally create a leak before cleanup; only the documented post-cleanup retained root may support a zero-match claim. / 精确扫描覆盖 SQLite、Job/lane/运维投影、manifest/receipt 及返回后的成功/失败 attempt 根。负向测试可以在清理前有意创建泄漏；只有记录明确的清理后保留根才能用于零匹配声明。
- The persistent account browser profile is a credential-bearing boundary and is excluded from a whole-tree zero-secret claim. Its path and contents must still remain ignored and absent from operator output. / 持久账户 browser profile 是可能携带凭据的边界，不纳入整树零密钥声明；其路径与内容仍必须保持忽略，且不出现在运维输出中。
- Manifests necessarily contain confined local paths. Therefore path redaction is asserted on operator/Job/lane surfaces, not as a false no-path claim over manifest bytes. / Manifest 必然包含受限本地路径，因此路径脱敏只对运维/Job/lane 表面断言，不对 manifest 字节作虚假的无路径声明。

## Live qualification / 真人资格验证

| Platform / 平台 | QR login / 二维码登录 | Cookie login / Cookie 登录 | Saved session / 保存会话 | Creator scheduled run / 作者定时运行 | Status / 状态 |
| --- | --- | --- | --- | --- | --- |
| `xhs` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `dy` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `ks` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `bili` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `wb` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `tieba` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `zhihu` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

## Deferred implementation / 延期实现

Scheduled backfill, signed-locator refresh, real CDN/media retrieval, automatic sync → download → export planning, per-request HTTP throttling, QR/challenge presentation UX, REST, resident production supervision, Docker, distributed HA/PostgreSQL and live Emby/Jellyfin operations are outside execution 0007. They are unimplemented/deferred scope rather than successful or failed qualification evidence.

定时 backfill、签名 locator refresh、真实 CDN/媒体获取、自动 sync → download → export 规划、逐请求 HTTP 节流、二维码/challenge 展示 UX、REST、常驻生产守护、Docker、分布式 HA/PostgreSQL 及真人 Emby/Jellyfin 运维不属于执行 0007。它们是未实现/延期范围，而不是成功或失败的资格证据。
