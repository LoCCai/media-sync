[English](verification.md) | **中文**

# 执行 0054 阶段 B 验证

- 状态：仅规划基线；尚未运行实现验证
- 日期：2026-09-05
- 基线：`4945df1`
- 计划数据库 revision：无；Alembic 保持 `0007`

## 验证政策

本文档区分规划证据、未来自动化实现证据与未来真人 qualification。文档检查只能证明本启动包结构有效，不能证明 lookup、polling、真实服务器兼容性、远端完成或播放。

任何官方 API 响应都不得被解释得比其契约更强。refresh 200/204 只证明接受。完整精确 item lookup 只证明一次观察。mock provider test 只证明实现行为。只有经授权的真实服务器执行才能把真人状态从 `NOT_RUN` 改变。

## 基线证据

| 检查 | 命令或来源 | 状态 |
| --- | --- | --- |
| Git 基线 | `git rev-parse HEAD` | `PASS` — 规划修改前为 `4945df1969d4f4b8f2dd8c8da972b6183798f671` |
| 初始 tracked worktree | `git status --short` | `PASS` — 没有 tracked change；只有既有未跟踪 `.mimosa/` |
| 修改前 focused tests | `uv run --frozen pytest -q -p no:cacheprovider tests/unit/test_media_server_connector.py tests/unit/test_media_server_application.py tests/unit/test_api_media_server.py tests/unit/test_operation_payloads.py tests/integration/test_operation_repository.py tests/integration/test_operation_coordinator.py` | `PASS` — 218 passed、1 warning，耗时 10.06s；该 warning 是既有 Starlette/httpx deprecation |
| 官方路由复核 | goal 中链接的四份版本化 OpenAPI 与 Jellyfin 10.10.7 controller | `PASS` — 定向 refresh 无 task ID；已记录 provider 路由差异 |
| 文档结构 | `uv run --frozen python scripts/check_docs.py` | `PASS` — 490 个 Markdown 文件的文档链接均正常 |
| 文档集合 | 对 `phase-b/` 做精确文件名与数量审计 | `PASS` — 恰好为预期的 8 个 Markdown 文件 |
| Patch 空白 | 直接审计全部 8 个未跟踪文件的尾随空白与末尾换行，并运行 `git diff --check -- docs/executions/0054-media-library-server-integration/phase-b` | `PASS` — 无尾随空白、每个文件均以换行结尾，tracked diff 检查干净 |
| 范围审计 | `git status --short --untracked-files=all -- docs/executions/0054-media-library-server-integration/phase-b` 与排除 `.mimosa/` 的完整状态 | `PASS` — 仅出现预期的 8 个阶段 B 文件；父级 0054 文档与执行索引未修改 |

所有选择 deliverable 文件的命令和未来提交都排除既有 `.mimosa/`。

## 契约证据映射

| 冻结要求 | 计划证据 |
| --- | --- |
| 如实能力命名 | qualification 与 UI 断言 `post_refresh_item_observation`；`provider_task_completion` 保持不支持 |
| 向后兼容 scan | 精确测试确保 legacy 空对象 `{}` Operation 继续 targetless，并保留其 acceptance-only 结果与 golden `{profile_fingerprint}` request fingerprint |
| Observation identity | author 模式使用 `target_type=author`、`target_id=<author UUID>`、既有 author target relation，以及 worker 前原子关联的 publication Job `related` subject |
| 本地权威 | 当前完整 publication head/manifest 测试；无调用方远端 selector；POST 前重核验 |
| 精确 lookup | 完整 provider/path 双重匹配真值表与完整唯一性要求 |
| Emby/Jellyfin 差异 | 四版本请求 snapshot 与禁用参数/fallback 断言 |
| 有界工作 | 单响应、pass、Operation、页、item、字节、JSON、poll 与 deadline 耗尽测试 |
| Mutation 真实性 | matched baseline 不发送 POST；否则最多一次 POST，区分 acceptance unknown 与 completion unknown；accepted/observed checkpoint 使用既有 `result_summary` 与复用的 `operation_phase_changed`，不新增 Event kind |
| 取消与重启 | 明确覆盖 accepted/cancel、observed/cancel/final、coordinator fallback、transport-entry、phase-based reconcile 与 lease/final/checkpoint CAS 竞态 |
| 并发边界 | 数据库 profile exclusivity 只覆盖持久 probe 与 scan Operation；直接 GET 是独立有界 snapshot，只具备进程内 connector gate，不声称关联证据 |
| Migration 与回滚 | Alembic 保持 `0007` 且不新增数据库 vocabulary；旧 binary 不得接管 active author observation |
| 保密 | 日志、DB、Events、SSE、API、support bundle 与 Web 均无原始或编码 selector sentinel |
| 资格真实性 | automated、implementation 与 human 状态保持独立 |

## 计划自动化矩阵

1. Emby 4.8.10 与 4.9.5 使用有过滤的 `GET /Items`，本地核验每个候选，发送有文档的递归 refresh，并接受有文档的 200。
2. Jellyfin 10.10.7 与 10.11.11 使用有界 Library 分页，不使用 Path/AnyProviderIdEquals；refresh 不发送 Recursive 参数；接受有文档的 204。
3. 代码不得调用 Emby direct item GET、`/ScheduledTasks`、WebSocket completion、全局 `/Library/Refresh`、服务端 next link 或第二次 mutation attempt。
4. 完整零匹配为 `not_found`；完整唯一精确 identity 为 `matched`；多个 identity 为 ambiguous；部分、漂移、重复、畸形或预算耗尽遍历为 incomplete。
5. 只有 absent baseline、accepted POST、两次间隔观察到同一唯一 item 才成功。既有 baseline 在 POST 前以 `media_server_scan_observation_precondition_failed` 结束；任何 Etag 变化都不能证明完成。
6. legacy 空对象 `{}` scan 继续 targetless 和 succeeded/accepted，并保留其精确结果与 golden `{profile_fingerprint}` request fingerprint。author 模式使用 `target_type=author` 与 author UUID、既有 target relation，并在 worker 启动前原子关联 publication Job `related` subject。
7. accepted 与 observed running checkpoint 写入既有 `result_summary`，且只发出既有 `operation_phase_changed`；不新增 Event kind。之后任何 completion-unknown 或 coordinator fallback 都保留 accepted 证据，绝不以 `{}` 替换其 summary。
8. 权威锁竞态矩阵证明：已知可信 2xx 后，cancel-first 对 accepted-checkpoint 与 accepted-first 对 cancel 两种顺序都保留接受事实；cancel-first 对 observed-checkpoint 会阻止 observed 并以 completion unknown 结束；observed-first 对 cancel 或 finalization 保留 observed success；coordinator exception/finalization 保留 accepted 证据且不可重试。entry 前取消发送零 POST；entry-first 的 timeout/reset/5xx/redirect/cleanup 歧义最多发送一次 POST，并以 acceptance unknown 结束。
9. 相同 idempotency key 与相同 identity replay 同一 Operation；mode/author/profile/publication 变化冲突。profile exclusivity 只串行化持久 probe、legacy scan 与 author-observation scan Operation。直接 GET 保持有界且独立，只使用 connector 进程内 gate，不具备数据库互斥，也不是与 scan 关联的证据。
10. 每页重复全部 DNS answer/CIDR 验证与 pinning。混合 answer、rebinding、Host/SNI 漂移、proxy、redirect、next link、非 header 凭据和 route/query override 尝试都 fail closed。
11. 即使远端响应和异常包含敏感值，任何持久或返回出口都不存在原始 path/provider/item/Etag/token 与百分号编码变体。
12. SQLite 与真实 PostgreSQL 服务验证 phase-aware restart：`preparing`/`baselining` 为 pre-dispatch interrupted，`dispatching` 为终态 acceptance unknown，`accepted`/`polling` 为保留 checkpoint 的终态 completion unknown，`observed` 只有 checkpoint 有效时才 succeeded，legacy targetless `{}` 行为保持不变。lost-lease 与 duplicate-final 竞态仍只产生一个 terminal Event。
13. Migration-compatibility 测试保持 Alembic `0007`，并证明阶段 B 不新增数据库 kind、state、Event kind、subject type、role、表、列或 constraint value，同时使用已经有效的 author target、author/Job subject、`result_summary` 与 `operation_phase_changed`。
14. Web 单元与浏览器测试覆盖两种 action、author gating、SSE reconnect、request generation、如实文案、无假百分比、无原始 selector 与 unknown-state 恢复指引。
15. 部署回滚检查与文档禁止旧 binary 接管 active author-observation Operation；必须等待这些行进入终态，或部署具备兼容 reconcile 的 binary，且不得删除审计证据。

focused selection 之间可能重叠，不得相加。最终验证还包括完整 Python/Web suite、lint、format、strict typing、build/distribution、documentation、upstream、generated-output、host-path、secret-pattern 与 whitespace 门禁。

## 真人资格

本工作区没有真实 Emby/Jellyfin origin、Library 或凭据。启动时：

- 当前已实现的 connection、discovery 与 targeted-acceptance 能力保持真人 `NOT_RUN`；
- 阶段 B lookup 与 observation 在代码落地前保持实现状态 `NOT_IMPLEMENTED`；
- 代码落地后转为实现状态 `IMPLEMENTED`，但授权操作员真实执行前仍为真人 `NOT_RUN`；
- provider task completion 保持 `NOT_IMPLEMENTED`，不是 `NOT_RUN`；
- playback evidence 与 automatic post-export scan 继续在本阶段范围外。

## 退出门禁

只有每个冻结的本地/mock 要求都有精确 passing evidence、评审没有剩余 P0/P1/P2、兼容测试保留 legacy `{}` scan 行为与旧 row、所有 tracked output 都符合意图，阶段 B 才能收尾。收尾仍须声明 provider task completion 与 playback 未被证明。真实服务器运行是可选外部资格，不能用 mock 伪造。
