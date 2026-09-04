[English](plan.md) | **中文**

# 执行 0054 阶段 B 计划

- 状态：规划基线已冻结；尚未开始实现
- 计划日期：2026-09-05
- 基线：`4945df1`
- 前序：执行 0054-A
- 计划数据库 revision：无

## 基线与冻结决策

执行 0054-A 已提供一个不可变、由环境拥有的服务器 profile、精确 Library discovery、抗 SSRF 连接器、持久 targetless `media-server-probe` 与 `media-server-scan` Operation、只确认接受的定向刷新，以及 SSE 进度投影和脱敏的 Library/Settings/Jobs 界面。其空对象 `{}` scan 请求与结果 `scan_state=accepted` 是公开兼容契约，继续有效。

阶段 B 保留以 `{}` 调用 `POST /api/v1/media-server/scan` 的既有 acceptance-only 语义；该 legacy 模式继续 targetless。同一路由额外精确接受 `{"author_id":"<uuid>"}` 进入新的 observation 模式，其 Operation 以该作者为 target。显式 null、未知字段和所有远端 selector 仍无效。两种请求共用既有 Operation kind 与 profile-exclusive domain，但具有不同 request fingerprint 和结果契约。

官方 Emby/Jellyfin API 不为定向 item refresh 提供持久 task ID。因此阶段 B 冻结 `provider_task_completion` 为不支持，只实现 absent-to-unique-match 的 `post_refresh_item_observation`。不得把 Scheduled Task、空闲状态、WebSocket、时间戳或 Etag 启发式升级为完成。

## 交付顺序

1. 将双语阶段 B 规划基线与实现分开提交，并排除既有未跟踪 `.mimosa/`。
2. 新增内部 publication-target resolver。它只接收作者 UUID，解析唯一当前成功 publication head，核验其完整严格 manifest，派生确定性 server path 与 provider key/value，并仅返回内存 selector 和安全 fingerprint。
3. 扩展 provider-neutral port，增加有界只读 item lookup 结果：完整 `not_found`、完整唯一 `matched`、ambiguous 或 incomplete。原始 selector 与响应对象留在连接器内。
4. 按 provider 拆分请求模板。实现带过滤的 Emby lookup 与完整有界的 Jellyfin lookup，包括响应形状、分页一致性、唯一性、累计预算和本地精确匹配检查。
5. 在启用 lookup 前封闭 query 日志边界。selector-bearing 请求的依赖库 wire record 变成固定消息；原始和编码后的 query 值都不得保留。
6. 新增作者作用域 lookup GET 及其安全响应。它保持同步、有界，不创建新 Operation kind。
7. 扩展既有 scan 请求解析器，使其只接受两种精确 body。保留 `{}` acceptance-only 行为；作者模式编排 baseline lookup、一次 refresh dispatch、持久 accepted checkpoint 与有界 observation polling。
8. 扩展 `OperationRepository` 与 `OperationCoordinator`，新增受 lease/revision fence 保护的 running-result checkpoint；这不是当前已有能力。再加入 phase-aware 取消、最终 CAS 和重启 reconcile。该转换把持久 accepted 或 observed 证据写入既有 `result_summary` JSON，并复用 `operation_phase_changed`；不新增 Event kind、表或 migration。
9. 更新 Library 与 Jobs：保留顶部 acceptance-only 刷新；只为当前完整 publication 的作者行增加“刷新并核验”；分别标记接受、观察、完成未知与可播放。
10. 仅在 focused 与 complete 实现门禁通过后，更新 qualification schema 与双语架构/部署/安全文档。mock 证据不改变真人状态。

## Lookup 契约

resolver 权威是作者 UUID、publication-scope identity、确定性 output identity、唯一成功 predecessor-chain head、source/tree/manifest fingerprint 与完整严格 manifest 的组合。`ExportRecord`、调用方路径或文件系统发现均不能单独成为权威。远端 mutation 前必须再次解析；权威变化则在 POST 前中止。

服务器 selector 为：

- provider key：`media-sync-{platform}-creator`；
- provider value：已存作者 remote ID；
- path：精确配置的 server Library root 加确定性单段作者目录；
- parent：配置的 Library item ID。

路径拼接使用配置的服务器路径语法，而不是宿主操作系统语法。路径样式有歧义或无法表达时，在网络活动前失败。无法无损表示为 Emby AnyProviderIdEquals 单 token 的 provider value 可以省略该服务端优化，但 Path 过滤和完整、本地核验的双重匹配仍是硬要求。

Emby 发送一次 `GET /Items`，固定 `Path`、可无损时的 `AnyProviderIdEquals`、`ParentId`、`Recursive=true`、`Fields=Path,ProviderIds`、`EnableImages=false`、`EnableUserData=false`、`StartIndex=0` 与 `Limit=2`。若报告总数超过已返回的有界集合、计数畸形或过滤外响应使完整唯一性无法证明，则为 incomplete。

Jellyfin 发送由本地计算索引的 `GET /Items` 分页，固定 `parentId`、`recursive=true`、`fields=Path,ProviderIds,Etag`、`enableImages=false`、`enableUserData=false`、`enableTotalRecordCount=true`、`startIndex` 与 `limit=128`。不得发送 Path 或 AnyProviderIdEquals。总数与起始索引必须存在、非负且稳定；各页 item ID 必须唯一；完整 pass 必须覆盖声明总数。可在总预算内为变化的枚举重新开始一次，否则为 incomplete。

每个候选必须具有完全相等的派生 path、恰好一个 canonical provider-key entry、完全相等的 provider value 与有界非空 item ID。完整 pass 后零精确匹配为 `not_found`；一个为 `matched`；两个不同 item ID 为 `media_server_item_lookup_ambiguous`。重复页、重复 ID、不稳定总数、缺少必需字段或预算耗尽均为 `media_server_item_lookup_incomplete`。

## Scan 与 Operation 契约

两种请求模式都复用 `media-server-scan`、既有 profile-exclusive key、幂等处理、lease fencing、Event stream 与结果大小边界。

对于 `{}`：

- `target_type` 与 `target_id` 保持为 null，精确保留 0054-A request fingerprint 参数 `{profile_fingerprint}`，并保留 acceptance-only 结果形状，供旧客户端与 idempotency replay 使用；
- discovery 配置的 Library，只 dispatch 一次 provider-specific refresh，持久化 `accepted` 后成功结束；
- 不做 item lookup，也不暗示 observation。

对于 `{"author_id":"<uuid>"}`：

- 创建 `target_type=author`、`target_id=<author UUID>` 的 Operation；request 参数使用 `{profile_fingerprint, mode=post_refresh_item_observation, publication_fingerprint}`，使 target 与参数共同绑定 request identity，且不改变 legacy fingerprint；
- 使用既有 target relation 关联 author，并在 worker 启动前把 publication Job 以 `related` subject 原子关联；
- 要求完整 baseline；ambiguous/incomplete baseline 不发送 POST；
- absent baseline 才具备 observation 成功资格；
- baseline 已 matched 时，在 POST 前以 `media_server_scan_observation_precondition_failed` 终止；响应指引只想执行手动刷新的操作员使用保留的 legacy `{}` 请求。

observation 模式 phase 为 `preparing → baselining → dispatching → accepted → polling → observed`。acceptance-only 模式可以省略 baselining/polling/observed。`dispatching` 在 transport entry 前持久化。经核验的 2xx 后，`accepted` 与其安全 checkpoint 写入既有 `result_summary`；第二次确认 lookup 后，`observed` 与其安全 checkpoint 使用同一字段。两种 checkpoint 转换都复用 `operation_phase_changed`。progress 使用 `total=null` 的核验 `steps` 单调递增，不估算远端工作。

终态规则为：

| 最后一个权威事实 | 终态结果 |
| --- | --- |
| transport entry 前取消或失败 | `cancelled` 或已分类的 pre-dispatch failure；POST 次数为零 |
| author baseline 已 matched | `failed_terminal / media_server_scan_observation_precondition_failed`；POST 次数为零 |
| transport 已进入，可信 2xx 未建立 | `failed_terminal / media_server_scan_acceptance_unknown` |
| 可信 2xx 且为 acceptance-only 模式 | `succeeded`，保持既有 accepted 结果 |
| 可信 2xx、baseline absent、同一唯一 item 连续观察两次 | `succeeded`，accepted 加 `absent_to_unique_match` observation |
| 可信 2xx，但无法证明 observation | `failed_terminal / media_server_scan_completion_unknown`，保留 accepted checkpoint |

transport、connector、coordinator、idempotency replay、restart reconcile 和 UI 都不得重试 POST。只读 lookup attempt 只能在冻结累计预算内重试。

重启 reconcile 使用 author target、publication Job subject 与持久 phase/checkpoint：

- `preparing` 或 `baselining`：pre-dispatch interrupted；新建一次手动请求是安全的。
- `dispatching`：终态 acceptance unknown，不可重试。
- `accepted` 或 `polling`：终态 completion unknown，保留 accepted checkpoint，不可重试。
- 最终 CAS 前的 `observed`：只有已存 observed checkpoint 有效时才 succeeded；否则以 completion unknown 终止并保留已有 accepted 证据。
- legacy targetless `{}` scan 保持 0054-A 的保守 reconcile 行为不变。

每次 phase/checkpoint/final 转换都校验 revision、lease owner、lease token 并执行权威 locked read。cancel-before-entry 阻止 POST；entry 之后不能把结果改写成 cancelled。一旦已知可信 2xx，accepted checkpoint 即使遇到并发 cancel 仍可持久化，因为接受事实是权威事实。若 cancel 在权威锁内先于 observed checkpoint 胜出，则阻止该 checkpoint 并以 completion unknown 结束；若 observed checkpoint 先胜出，则迟到的 cancel 或 finalization 竞态不得覆盖它。coordinator 异常与通用 finalization 路径必须保留 accepted summary，绝不能用 `{}` 替换它，也绝不能把 post-dispatch 工作改成可重试。

## API 与 Web 契约

`POST /api/v1/media-server/scan` 是 legacy 空对象与作者 observation 对象的严格 union。响应继续为 202 Operation submission。幂等键 replay 返回同一 Operation；相同键但 mode、author、profile 或 publication 不同则冲突。

`GET /api/v1/media-server/items/by-author/{author_id}` 返回 schema version、作者 UUID、provider、Library digest、publication/selector digest、`matched|not_found`、精确匹配数、可选 domain-separated item digest、观察时间与 `complete=true`。它不返回任何 selector component 或远端 payload，并携带 `Cache-Control: no-store`。

scan result 为 acceptance-only 行保留 legacy 精确形状。observation 行使用单独校验的安全形状，包含 `scan_state=accepted`、observation state/evidence、profile/Library/publication/selector digest、可选 item digest、匹配数与观察时间。既有已存行保持可读；公开形状变化时 API 与 qualification schema version 升级，但这不意味着数据库 migration。

Library header 保留“定向刷新——仅确认接受”。只有 server-provided allowed actions 确认当前完整 publication 且没有 profile-exclusive Operation 在运行时，作者行才显示“刷新并核验”。Jobs 展示 phase 与“核验 N 次”，不显示百分比条。文案明确：“已接受不等于已观察”“已观察不等于 provider task completion”“已观察不等于可播放”。

## 安全与上限

每个请求都重新解析全部当前 DNS answer，要求全部位于配置 CIDR policy 内，pin 选定地址，保留 Host 与 TLS SNI，禁用环境代理与重定向，并且永不跟随服务端提供的 URL。API key 在最终请求边界解析，只进入 `X-Emby-Token`。

单响应继续沿用 0054-A 上限：64 个 header、单 header 行 8 KiB、header 总计 64 KiB、body 256 KiB、JSON 深度 8、JSON item 2,048、单字符串 4,096 字符。阶段 B 新增：Jellyfin 每页 128 行；每个 lookup pass 32 页、4,096 个唯一 item、8 MiB；每个 observation Operation 总计 128 页、检查 16,384 行、32 MiB；观察 deadline 120 秒；poll 间隔至少两秒。这些是部署代码拥有的硬默认值，可由有界 operator setting 降低，API 请求不能提供。

原始 path、provider value、远端 item ID、Etag、header、body、远端错误、凭据或完整 secret reference 都不得进入结构化日志、Operation request/result/event JSON、SQLite、SSE、API 响应、support bundle 或 Web state。digest 必须做 domain separation，并绑定高熵 profile/publication 上下文，不能暴露低熵 remote ID 的独立 digest。

profile-exclusive 数据库 key 只串行化持久 probe、legacy scan 与 author-observation scan Operation。直接 author lookup 是独立的只读 snapshot，只受 connector 进程内 gate 保护；它不具备数据库互斥、跨进程关联或与 scan Operation 的状态关系。

## 验证计划

- Provider 矩阵：Emby 4.8.10/4.9.5 与 Jellyfin 10.10.7/10.11.11 的精确路由、参数、大小写、分页、200/204 接受和禁止 fallback 路由。
- Lookup 真值表：仅 path、仅 provider、近似匹配、零/一/多 identity、重复页、变化总数、过滤器违约、畸形 DTO 以及 complete/incomplete 结果。
- Observation：absent 后同一唯一 item 两次；一次匹配后消失；item ID 变化；baseline 已存在且 Etag 变/不变；观察耗尽；无假成功。
- Mutation 边界：entry 前取消/deadline、entry-first 竞态、所有 post-entry transport/status/cleanup 歧义、durable accepted checkpoint、POST 最多一次与无重试。
- 安全：混合 DNS answer、每页重绑定、IP pinning、Host/SNI、proxy/redirect/next-link 拒绝、仅 header 凭据、原始与百分号编码 selector sentinel、恶意远端正文和 support-bundle 扫描。
- 持久化：两种请求形状的幂等、subject link、legacy row 读取、phase-aware reconcile、SQLite 与真实 PostgreSQL 的 cancel/final/checkpoint 竞态、lease 丢失和唯一 terminal Event。
- Web：两种 scan action、作者 gate、SSE replay、无 stale response 覆盖、如实文案、无假百分比与安全 unknown 详情。
- 回归：当前 connector、Operation、migration、API、qualification、Library、Jobs、完整 Python/Web 质量门禁、distribution、docs、upstream、tracked-output、host-path、secret-pattern 与 whitespace 检查。

## 数据库与回滚

计划不新增 schema migration。Alembic 保持 revision `0007`：其既有 vocabulary 已允许 author Operation target、带 `target` 与 `related` role 的 author 和 Job subject、既有 `result_summary`，以及复用 `operation_phase_changed` Event code。阶段 B 不新增数据库 kind、state、Event kind、subject type、role、表、列或 constraint value。新增 lookup Operation kind、远端 task/baseline 表，或需要更丰富持久 checkpoint 的可恢复 polling，都必须另行评审 migration。

任何阶段 B 代码提交前，回滚只删除本规划目录。实现后回滚必须保留全部 0054-A acceptance-only 行和阶段 B observation 行。旧 binary 绝不能接管仍在 active 的 author-observation Operation；回滚前必须等待这些行全部进入终态，或部署具备兼容 reconcile 的 binary。公开 payload 兼容应由应用 decoder 处理，不得删除审计证据。既有未跟踪 `.mimosa/` 与所有常规 runtime/generated output 始终排除在提交之外。
