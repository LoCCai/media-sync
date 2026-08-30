# Execution 0008 verification / 执行 0008 验证

- Verification state / 验证状态：`NOT_RUN`
- Planning date / 计划日期：2026-08-30
- Network/account policy / 网络与账户策略：offline fixtures and repository-owned helper processes only; no browser, real credential, platform/CDN endpoint or Emby/Jellyfin server / 仅离线夹具与仓库自有 helper process；不使用浏览器、真实凭据、平台/CDN 端点或 Emby/Jellyfin 服务器
- Implementation state / 实现状态：`NOT_RUN`

This is the frozen verification contract for execution 0008, not implementation evidence. Planning-baseline documentation checks are recorded separately below; no cancellation barrier, security-matrix, retained-sentinel or live row is promoted until its exact command and result are recorded.

本文件是执行 0008 的冻结验证契约，不是实现证据。计划基线文档检查单独记录在下方；在记录准确命令与结果之前，不提升任何取消 barrier、安全矩阵、留存哨兵或真人行。

## Planning-baseline checks / 计划基线检查

The following rows were run after the four records and project indexes were written. They qualify only the planning baseline; every implementation and behavioral row remains `NOT_RUN`.

下列各行在四份记录与项目索引写入后运行，只验收计划基线；全部实现及行为行继续保持 `NOT_RUN`。

| Check / 检查 | Exact command / 准确命令 | Result / 结果 |
| --- | --- | --- |
| Documentation links / 文档链接 | `uv run python scripts/check_docs.py` | `PASS` — exit `0`; `Documentation links OK (48 Markdown files checked).` |
| Locked upstreams / 锁定上游 | `uv run python scripts/check_upstreams.py` | `PASS` — exit `0`; `Upstreams OK (2 locked checkouts verified).` |
| Patch whitespace / 补丁空白 | `git diff --check` | `PASS` — exit `0`; no output / 无输出 |

## Planned behavior evidence / 计划行为证据

| Scope / 范围 | Required evidence / 必需证据 | Status / 状态 |
| --- | --- | --- |
| Child-exit/pre-seal cancellation / Child 退出后、密封前取消 | Real helper returns `0`; tree joins; final inspection barrier cancels; receipt writer is never called; handler normalizer/ingestor spies prove zero entry; attempt cleans; lock reacquires / 真实 helper 返回 `0`；整树 join；最终检查 barrier 取消；不调用 receipt writer；handler normalizer/ingestor spy 证明零进入；attempt 清理；锁可重获 | `NOT_RUN` |
| Post-seal/pre-ingest cancellation / 密封后、导入前取消 | Valid receipt exists; blocking normalizer observes repeated cancellation; join-before-unwind; zero Content/Asset/checkpoint/success writes / 有效 receipt 存在；阻塞 normalizer 观察重复取消；先 join 再 unwind；Content/Asset/checkpoint/成功写入均为零 | `NOT_RUN` |
| Closed failure rows / 封闭失败行 | Exact eleven-value failure set, each with a unique generated sentinel / 精确 11 值失败集合，每行使用唯一生成哨兵 | `NOT_RUN` |
| Filesystem sink / 文件系统落点 | Every ordinary row ends `ABSENT`/`REMOVED` and retained safe roots contain no sentinel / 每个普通行终态为 `ABSENT`/`REMOVED`，保留安全根无哨兵 | `NOT_RUN` |
| SQLite sink / SQLite 落点 | Every row scans logical text/JSON, database files and authority state; no sentinel or post-fence stale mutation / 每行扫描逻辑文本/JSON、数据库文件及权限状态；无哨兵或 fencing 后旧 owner 变更 | `NOT_RUN` |
| Operator sink / 运维落点 | Every row scans result/CLI/captured output and `str`/`repr` for sentinel, authority, roots and raw errors / 每行扫描结果/CLI/捕获输出及 `str`/`repr` 中的哨兵、权限、根路径与原始错误 | `NOT_RUN` |
| Matrix completeness / 矩阵完整性 | Exact equality with eleven rows × three sinks = 33 cells / 与 11 行 × 3 落点 = 33 cell 精确相等 | `NOT_RUN` |
| Credential-bearing negatives / 可能携带凭据负向边界 | Exact quarantine/unresolved/profile exclusion list; fixed marker attempt plus unconditional fence; no retained path in operator output / 精确 quarantine/unresolved/profile 排除清单；尝试固定 marker 且无条件 fence；运维输出无留存路径 | `NOT_RUN` |
| Existing protocol boundaries / 既有协议边界 | Seven-platform offline chain, parent death, retry/restart, v3/v2 and immutable manual v2/v1 compatibility remain green / 七平台离线链、父死亡、重试/重启、v3/v2 及不可变手工 v2/v1 兼容保持通过 | `NOT_RUN` |

## Planned quality gates / 计划质量门禁

Exact focused nodes and retained-sentinel statistics will be finalized after implementation. Results remain `NOT_RUN` until the final invocation, exit code, count, timing and material output are recorded.

准确专项节点与留存哨兵统计会在实现后定稿。在记录最终调用、退出码、数量、耗时及关键输出前，结果保持 `NOT_RUN`。

| Check / 检查 | Planned command or scope / 计划命令或范围 | Status / 状态 |
| --- | --- | --- |
| Locked dependencies / 锁定依赖 | `uv sync --all-groups --locked` | `NOT_RUN` |
| Lint / 代码规范 | `uv run ruff check .` | `NOT_RUN` |
| Format / 格式 | `uv run ruff format --check .` | `NOT_RUN` |
| Strict types / 严格类型 | `uv run mypy src/media_sync` | `NOT_RUN` |
| Full branch-aware suite / 完整分支感知套件 | `uv run pytest --cov=media_sync --cov-report=term` | `NOT_RUN` |
| Focused cancellation/matrix gate / 取消/矩阵专项 | Exact contract, scheduler-handler and security-matrix nodes / 准确 contract、scheduler-handler 与安全矩阵节点 | `NOT_RUN` |
| Build / 构建 | `uv build` | `NOT_RUN` |
| Packaged migrations/resources / 随包迁移/资源 | Existing packaged migration tests; no empty revision / 既有随包迁移测试；不新增空 revision | `NOT_RUN` |
| Documentation / 文档 | `uv run python scripts/check_docs.py` | `NOT_RUN` |
| Pinned upstreams / 锁定上游 | `uv run python scripts/check_upstreams.py` | `NOT_RUN` |
| Patch whitespace / 补丁空白 | `git diff --check` | `NOT_RUN` |
| Runtime artifacts untracked / 运行产物未跟踪 | Scoped `git ls-files`, `git status` and ignore checks / 限定 `git ls-files`、`git status` 与 ignore 检查 | `NOT_RUN` |
| Fresh retained sentinel / 全新留存哨兵 | `.media-sync/verification/0008-closeout-sentinel-root` exact allowlist/scans / 精确 allowlist/扫描 | `NOT_RUN` |

## Planned retained-artifact rules / 计划留存产物规则

- The 0008 sentinel root must not exist before its authoritative run and must never be deleted or recreated. The 0007 root remains untouched. / 0008 哨兵根在权威运行前必须不存在，之后不得删除或重建；0007 根保持不动。
- Use an exact safe-test allowlist. List all quarantine, unresolved, cancellation-authority and browser-profile retention negatives excluded from whole-tree zero-match evidence. / 使用精确安全测试 allowlist；列出从整树零匹配证据排除的全部 quarantine、unresolved、取消权限及 browser-profile 留存负向测试。
- Validate Windows pytest `current` aliases as existing same-parent in-root targets and scan each real target independently. / 把 Windows pytest `current` alias 验证为根内同父现存目标，并独立扫描每个真实目标。
- Record cases, 33 matrix cells, exact sentinels, SQLite authority checks, aliases, files, directories, bytes and elapsed time. / 记录 case、33 个矩阵 cell、精确哨兵、SQLite 权限检查、alias、文件、目录、字节与耗时。

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

## Deferred implementation / 延期实现

Signed-locator refresh with implemented successful/recovery-attempt terminal cleanup/isolation is execution 0009 scope. Durable automatic `sync → download → Emby` planning is execution 0010 scope. Real platform/CDN/Emby qualification, downloadable assets for `wb`/`tieba`/`zhihu`, platform derivatives, per-request HTTP spacing, bounded live pagination, QR/challenge UX, REST, resident supervision, Docker and HA/PostgreSQL remain deferred or `NOT_RUN` according to their truthful category.

签名 locator refresh 及已实现的成功/恢复 attempt 终态清理/隔离属于执行 0009；持久自动 `sync → download → Emby` 规划属于执行 0010。真人平台/CDN/Emby 验收、`wb`/`tieba`/`zhihu` 可下载资产、平台衍生物、逐 HTTP 请求间隔、真人分页有界性、二维码/challenge UX、REST、常驻监督、Docker 及 HA/PostgreSQL 按各自真实类别继续延期或保持 `NOT_RUN`。
