# Execution 0008 goal / 执行 0008 目标

- Status / 状态：Complete for the offline acceptance scope / 离线验收范围已完成
- Started / 开始时间：2026-08-30 15:48 +08:00
- Completed / 完成时间：2026-08-30
- Predecessor / 前置执行：Execution 0007 implementation commit `d071618`
- Network boundary / 网络边界：offline fixtures and repository-owned local helper processes only / 仅离线夹具与仓库自有本地辅助进程

## Outcome / 结果目标

Close execution 0007 acceptance criteria 6 and 13 without expanding the product surface. Execution 0008 must prove the two remaining cancellation windows deterministically and complete a closed failure-type × retained-filesystem/SQLite/operator-sink secret matrix. It may repair races exposed by those tests, but it does not implement signed-locator refresh, real media retrieval or an automatic downstream DAG.

在不扩大产品面的前提下，关闭执行 0007 的验收标准 6 与 13。执行 0008 必须确定性证明剩余两个取消窗口，并补齐封闭的“失败类型 × 保留文件系统/SQLite/运维落点”密钥矩阵。测试若暴露真实竞态，可以修复；本执行不实现签名 locator refresh、真实媒体获取或自动下游 DAG。

## Acceptance criteria / 验收标准

1. All implementation and verification stay offline. Tests may start only repository-owned helper processes that perform no browser or network work. No real secret reference, platform/CDN endpoint, Emby/Jellyfin server or Git remote is used.
2. A deterministic child-exit/pre-seal barrier cancels after a real helper child has returned `0` and the complete process tree has joined, but before `write_completion_receipt()` begins. No receipt is published, normalization/ingestion never starts, the runner reaches a definite cancelled verdict before unwind, the ordinary attempt root is secured, and the account/profile lock is reacquirable.
3. A deterministic post-seal/pre-ingest barrier cancels after a valid receipt exists but before ingestion starts. The handler joins any active normalization/security task before propagating cancellation; no Content/Asset is created, the checkpoint does not advance, the SyncRun does not become succeeded, and the ordinary attempt root is secured. Repeated cancellation must not make the outer task unwind early.
4. The closed failure set is exactly `known_secret_echo`, `nonzero_exit`, `timeout`, `output_bytes`, `output_items`, `output_files`, `output_line_bytes`, `output_tree`, `receipt_rejected`, `cancellation` and `lease_loss`. Every case injects a unique generated sentinel into attempt-private output before its failure is observed.
5. Every failure case verifies all three sink classes in the same case: retained filesystem, SQLite, and operator output. Ordinary active attempt roots end `ABSENT` or `REMOVED` and the retained safe tree has no sentinel; every SQLite text/JSON value and retained database file has no sentinel or scheduler authority inconsistent with the documented terminal/fenced state; serialized results, CLI/captured output, and exception/result `str`/`repr` have no sentinel, lease token, local root or raw cleanup error.
6. A matrix-completeness test proves set equality for `required_failure_cases × {filesystem, sqlite, operator}`. Adding or removing a failure type without updating all three sink assertions must fail collection or the focused gate.
7. `QUARANTINED`, `UNRESOLVED` and the persistent browser profile remain explicit credential-bearing negative boundaries, not false whole-tree zero-match evidence. Quarantine may retain a sentinel only below the ignored restricted quarantine root. Unresolved cleanup must attempt to persist fixed redacted markers and must hard-fence later secret resolution, run attachment, bridge preparation and spawn whether marker persistence succeeds or fails; a successful marker write remains durable. Paths and raw cleanup errors never enter operator output.
8. Fixed failure semantics remain unchanged: nonzero exit maps to `temporary_upstream`; timeout to `upstream_timeout`; output, receipt and secret rejection to `output_security_failed`; cancellation and lease loss propagate fencing and the stale handler never finalizes.
9. Execution 0007's four records remain historical `PARTIAL` evidence. Execution 0008 alone records the successor closeout. Manifest v2/receipt v1 compatibility stays byte-exact, read-only and manual-ingest/shared-normalization-only; scheduled recovery still trusts v3 only.
10. Ruff, format, strict mypy, the full branch-aware suite, the focused cancellation/matrix gate, build, packaged migrations/resources, documentation, upstream pins, patch checks, ignored/untracked-runtime checks and a fresh retained-artifact sentinel all pass with exact recorded results.

1. 全部实现与验证保持离线。测试只允许启动不执行浏览器或网络工作的仓库自有 helper process；不得解析真实 secret reference，不访问平台/CDN 端点、Emby/Jellyfin 服务器或 Git 远端。
2. 确定性的 child-exit/pre-seal barrier 在真实 helper child 返回 `0`、完整进程树已 join、但 `write_completion_receipt()` 尚未开始时取消。不得发布 receipt，不得开始归一化/导入；runner 必须先得到确定取消 verdict 再 unwind，普通 attempt 根必须安全收口，账户/profile 锁必须可重新获取。
3. 确定性的 post-seal/pre-ingest barrier 在有效 receipt 已存在、导入尚未开始时取消。handler 必须先 join 正在运行的归一化/安全任务再传播取消；不得创建 Content/Asset，不得推进 checkpoint，SyncRun 不得成功，普通 attempt 根必须安全收口。重复取消不得让外层 task 提前 unwind。
4. 封闭失败集合精确为 `known_secret_echo`、`nonzero_exit`、`timeout`、`output_bytes`、`output_items`、`output_files`、`output_line_bytes`、`output_tree`、`receipt_rejected`、`cancellation` 与 `lease_loss`。每个 case 都会在失败被观察前向 attempt 私有输出注入唯一生成哨兵。
5. 每个失败 case 都在同一次运行中验证三类落点：保留文件系统、SQLite 与运维输出。普通 active attempt 根终态为 `ABSENT` 或 `REMOVED`，安全留存树不得含哨兵；SQLite 全部文本/JSON 值及保留数据库文件不得含哨兵，也不得保留与文档化终态/fencing 不一致的 scheduler 权限；序列化结果、CLI/捕获输出及异常/结果的 `str`/`repr` 不得含哨兵、lease token、本地根或原始清理错误。
6. matrix-completeness 测试必须证明 `required_failure_cases × {filesystem, sqlite, operator}` 的集合相等；新增或移除失败类型而未同步三类落点断言时，collection 或专项门禁必须失败。
7. `QUARANTINED`、`UNRESOLVED` 与持久 browser profile 继续作为明确的可能携带凭据负向边界，不纳入虚假的整树零匹配。Quarantine 只允许在已忽略且受限的 quarantine 根下保留哨兵；unresolved 清理必须尝试持久化固定脱敏 marker，无论 marker 持久化成功或失败都必须硬 fence 后续密钥解析、run attach、bridge prepare 与 spawn，写入成功时 marker 保持持久；路径及原始清理异常不得进入运维输出。
8. 固定失败语义保持不变：非零退出映射为 `temporary_upstream`；timeout 映射为 `upstream_timeout`；输出、receipt 与密钥拒绝映射为 `output_security_failed`；取消与 lease 丢失传播 fencing，旧 handler 绝不收尾。
9. 执行 0007 的四份记录继续保留当时的 `PARTIAL` 历史事实，只由执行 0008 记录继任收口。Manifest v2/receipt v1 兼容继续保持逐字节精确、只读，且仅用于手工导入/共享归一化；定时恢复仍只信任 v3。
10. Ruff、格式、严格 mypy、完整分支感知套件、取消/矩阵专项、构建、随包迁移/资源、文档、上游锁定、补丁、忽略/未跟踪运行产物及全新留存产物哨兵均通过，并准确记录结果。

## Truth boundary and non-goals / 真实性边界与非目标

- Execution 0008 closes only offline acceptance evidence. It does not promote any live login, creator traffic, scheduled platform run, CDN retrieval or Emby/Jellyfin row.
- Signed-locator refresh remains execution 0009 scope. Current successful sealed attempt JSONL may contain an unknown expiring signed query that the parent could not pre-register as a known secret; that crash-recovery artifact is an explicit credential-bearing temporary boundary until execution 0009 implements terminal cleanup/isolation as part of refresh.
- Automatic `sync → download → Emby` planning remains execution 0010 scope. The current `adapter_refresh.key` is one-way and the download entry point lacks the required subscription/account/license context, so execution 0008 does not create blocked downstream Jobs.
- `wb`, `tieba` and `zhihu` currently normalize no downloadable assets; this is unavailable/deferred functionality, not a successful or merely untested media-download claim.
- Phone login remains unsupported. Per-request HTTP spacing, bounded live pagination, QR/challenge presentation UX, REST, resident supervision, Docker, public deployment and HA/PostgreSQL remain unimplemented or deferred.

- 执行 0008 只关闭离线验收证据，不提升任何真人登录、作者流量、平台定时运行、CDN 获取或 Emby/Jellyfin 行。
- 签名 locator refresh 仍属于执行 0009。当前成功密封的 attempt JSONL 可能包含父进程无法预先登记为已知密钥的未知短效签名 query；在执行 0009 把终态清理/隔离作为 refresh 的一部分实现之前，该 crash-recovery 产物是明确的可能携带凭据临时边界。
- 自动 `sync → download → Emby` 规划仍属于执行 0010。当前 `adapter_refresh.key` 单向不可逆，下载入口也缺少所需 subscription/account/license 上下文，因此执行 0008 不创建必然 blocked 的下游 Job。
- `wb`、`tieba`、`zhihu` 当前不会归一化出可下载资产；这是不可用/延期功能，不是成功或“仅未测试”的媒体下载声明。
- 手机登录仍不支持。逐 HTTP 请求间隔、真人分页有界性、二维码/challenge 展示 UX、REST、常驻监督、Docker、公网部署及 HA/PostgreSQL 仍未实现或延期。
