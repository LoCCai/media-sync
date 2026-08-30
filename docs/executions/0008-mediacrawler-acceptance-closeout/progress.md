# Execution 0008 progress / 执行 0008 推进结果

- Status / 状态：Planned / 已计划
- Started / 开始时间：2026-08-30 15:48 +08:00
- Implementation / 实现：`NOT_RUN` / 未运行
- Verification / 验证：`NOT_RUN` / 未运行
- Predecessor / 前置执行：Execution 0007 implementation commit `d071618`

## Planning baseline / 计划基线

- Execution 0007 delivered the offline scheduled handler but truthfully closed with AC6 and AC13 `PARTIAL`. Execution 0008 is the narrow successor that targets only those two gaps.
- 执行 0007 已交付离线定时 handler，但如实以 AC6 与 AC13 `PARTIAL` 收口；执行 0008 是只针对这两个缺口的窄范围继任执行。
- Read-only code review found one concrete pre-seal race: after final output inspection the runner calls receipt publication without another cancellation check. A deterministic test must fail first; the planned repair is one final check, not a new production hook.
- 只读代码复核发现一个具体 pre-seal 竞态：最终输出检查后，runner 未再次检查取消就调用 receipt 发布。必须先让确定性测试失败；计划修复是一次最终检查，而不是新增生产测试 hook。
- The post-seal/pre-ingest path already uses a repeated-cancellation-safe join helper, but no deterministic barrier proves that exact window. The new test will block the existing injected normalizer after receipt creation and verify zero ingestion.
- post-seal/pre-ingest 路径已经使用可抵御重复取消的 join helper，但尚无确定性 barrier 证明该精确窗口。新测试会在 receipt 创建后阻塞既有注入 normalizer，并验证零导入。
- The security matrix is frozen at eleven failure cases and three sink classes, yielding 33 required cells. Every row will use a runtime-generated sentinel and assert all sinks in the same run.
- 安全矩阵冻结为 11 个失败 case 与 3 类落点，共 33 个必需 cell。每一行都会使用运行时生成哨兵，并在同一次运行中断言全部落点。
- No schema migration, locator refresh or downstream Job planning is part of this baseline. No browser, real account, platform/CDN request or Emby/Jellyfin server is authorized.
- 本基线不包含 schema 迁移、locator refresh 或下游 Job 规划；不授权浏览器、真人账户、平台/CDN 请求或 Emby/Jellyfin 服务器。
- The planning baseline passed the documentation checker for 48 Markdown files, verified both pinned upstream checkouts and passed `git diff --check`. These checks qualify only the plan; all execution 0008 behavior remains `NOT_RUN`.
- 计划基线通过 48 份 Markdown 文档检查、两份锁定上游 checkout 校验及 `git diff --check`。这些检查只验收计划；执行 0008 的全部行为仍为 `NOT_RUN`。

## Entry gaps to close / 必须关闭的入口缺口

| Gap / 缺口 | Planned closure / 计划关闭方式 | Status / 状态 |
| --- | --- | --- |
| Child exit before receipt seal / Child 退出到 receipt 密封 | Event-driven real-helper barrier plus final cancellation check / 事件驱动真实 helper barrier 与最终取消检查 | `NOT_RUN` |
| Sealed receipt before ingestion / 已密封 receipt 到导入 | Blocking normalizer, repeated cancellation, joined cleanup and zero SQLite ingest / 阻塞 normalizer、重复取消、join 清理及 SQLite 零导入 | `NOT_RUN` |
| Incomplete failure/sink cross-product / 失败/落点交叉积不完整 | Eleven rows × three sinks plus exact set-equality test / 11 行 × 3 落点及精确集合等式测试 | `NOT_RUN` |
| Retention negatives mixed with safe-tree claims / 留存负向与安全树声明混淆风险 | Exact negative exclusion list and separate credential-bearing boundaries / 精确负向排除清单与独立凭据边界 | `NOT_RUN` |

## Planned implementation sequence / 计划实现顺序

1. Pre-seal cancellation regression and minimal runner repair. / Pre-seal 取消回归与最小 runner 修复。
2. Post-seal/pre-ingest repeated-cancellation regression and any required handler repair. / Post-seal/pre-ingest 重复取消回归及必要 handler 修复。
3. Eleven-row security matrix, three-sink assertions and 33-cell meta-test. / 11 行安全矩阵、三落点断言及 33-cell 元测试。
4. Existing boundary regressions, full gates, fresh retained sentinel and exact documentation. / 既有边界回归、完整门禁、全新留存哨兵及准确文档。

## Current qualification / 当前验收状态

| Scope / 范围 | Status / 状态 | Truth / 真实性说明 |
| --- | --- | --- |
| Execution 0007 AC6 successor closeout / 执行 0007 AC6 继任收口 | `NOT_RUN` | Two deterministic barriers have not run / 两个确定性 barrier 尚未运行 |
| Execution 0007 AC13 successor closeout / 执行 0007 AC13 继任收口 | `NOT_RUN` | Eleven-row, three-sink matrix has not run / 11 行三落点矩阵尚未运行 |
| Signed locator refresh / 签名 locator refresh | Unimplemented / 未实现 | Planned for execution 0009 / 计划由执行 0009 交付 |
| Automatic downstream DAG / 自动下游 DAG | Unimplemented / 未实现 | Planned after refresh, currently execution 0010 / 计划在 refresh 后交付，当前为执行 0010 |
| Live login, creator traffic, CDN and Emby/Jellyfin / 真人登录、作者流量、CDN 与 Emby/Jellyfin | `NOT_RUN` | No authorization or environment was supplied / 未提供授权或环境 |

## Deferred truthfully / 如实延期

- Successful sealed output remains a documented credential-bearing recovery boundary until execution 0009 implements terminal cleanup/isolation together with refresh. / 成功密封输出继续作为已记录的可能携带凭据恢复边界，直到执行 0009 与 refresh 一并实现终态清理/隔离。
- `wb`, `tieba` and `zhihu` downloadable assets, platform-specific derivatives, live pagination/rate qualification and phone login are not promoted. / 不提升 `wb`、`tieba`、`zhihu` 可下载资产、平台特有衍生物、真人分页/速率验收或手机号登录。
- REST, QR/challenge presentation, resident supervision, Docker, public deployment and HA/PostgreSQL remain later work. / REST、二维码/challenge 展示、常驻监督、Docker、公网部署及 HA/PostgreSQL 仍属于后续工作。
