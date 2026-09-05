[English](goal.md) | **中文**

# 执行 0055 阶段 A 目标

- 状态：冻结规划基线；尚未开始实现
- 日期：2026-09-05
- 基线：`d0a8cc2`
- 计划数据库 revision：`0008_playback_evidence`

## 目标

为 `media-sync serve` 增加关闭失败的单操作者鉴权边界，再增加 append-only、经鉴权的真人播放确认账本。该切片关闭当前最高的控制面残余风险，并让 `playback_evidence` 可实现，同时绝不混淆“刷新已接受”“已观察到项目”“provider 任务完成”与“实际播放”。

这是执行 0055 的最小安全切片，不包含浏览器可写媒体服务器配置、多 profile、保留、删除、修复、强制覆盖或自动 export-to-scan。

## 基线与威胁模型

在 `d0a8cc2`，FastAPI 应用共有 51 条路由且没有鉴权中间件。任何能访问端口的客户端都能访问业务 API、二维码、归档字节、Operation SSE、支持包、深度就绪、自动生成的 OpenAPI/docs、`/legacy` 与 SPA fallback。默认只绑定回环及 `MEDIA_SYNC_MEDIA_SERVER_OPERATIONS_ENABLED` 可以降低暴露，但都不是访问控制。

阶段 A 假设单个可信操作者、单个前台 API 进程、无分布式 HA、无可信转发 header。攻击者可以访问监听 socket，伪造 Host/Origin/header/cookie/请求体，重放已捕获的非秘密 API 响应，竞争重复请求，并提交任意 UUID 或 digest；攻击者尚未控制进程账户、配置的 secret provider、数据库文件、导出树或 TLS 终止层。XSS、已失陷操作者浏览器、多用户授权、SSO/MFA、反向代理身份及同权限恶意本机进程不在本切片内。

## 验收标准

1. `media-sync serve` 在绑定端口前解析类型化操作者凭据引用。缺失、畸形、空、过长、含控制字符或无法解析的凭据均以固定码停止启动，且不回显引用或值。生产环境不存在匿名模式开关。
2. 非浏览器自动化可选配置另一条独立的类型化 Bearer token 引用。若配置，它必须在绑定前解析、满足相同有界 secret 规则且不得与浏览器凭据相同。token 只允许出现在 `Authorization: Bearer` header，绝不进入 URL、query、form、cookie、WebSocket、EventSource 或日志上下文。
3. 非回环部署必须显式配置有界的规范操作者 origin allowlist；回环绑定可由 host/port 派生精确 HTTP origin。每个请求都用原始 Host 对照 allowlist，转发的 host/proto header 不授予权威；非回环浏览器 origin 必须使用 HTTPS。
4. 匿名路由 allowlist 必须精确：`GET`/`HEAD /api/v1/health`、`GET`/`HEAD /api/v1/ready`、`POST /api/v1/operator-auth/login`、`GET /api/v1/operator-auth/session`、`GET`/`HEAD /`、`/favicon.svg`、`/_app/version.json` 以及 `/_app/immutable/` 下已经解析为普通文件的既有资源。不得用 prefix 或 fallback 公开其他内容。
5. 其余所有路由在进入 handler、数据库、文件系统、reconcile 或 stream 之前必须完成鉴权，包括 OpenAPI/docs/redoc/oauth redirect、深度就绪、支持包、设置、QR PNG、归档 GET/HEAD/Range、Operation SSE、全部业务读写、`/legacy` 与已鉴权 SPA 深链接。未来未知路由默认拒绝。
6. 浏览器登录只接受一个严格 JSON credential 字段，要求允许的 Host 与精确 Origin，应用有界的进程全局失败限流，并以常量时间比较解析后的 secret。响应与结构化审计日志只使用固定码，不保留提交的凭据、cookie、CSRF、Origin、Host、IP 或 User-Agent。
7. 登录成功会轮转唯一的进程内浏览器 session 并使前一 session 失效。cookie 为不透明随机值，具有 `HttpOnly`、`SameSite=Strict`、Path `/`、无 Domain、最长八小时的有界 TTL，并在 HTTPS 部署设置 `Secure`。重启、登出、过期或凭据轮换都会使其失效。
8. 已鉴权 session bootstrap 返回仅供同源内存使用的有界 CSRF 值。每个使用 cookie 的不安全方法请求都要求精确允许的 Origin 与 CSRF header。缺失、畸形、过期、伪造、跨域或已登出的 session 材料全部关闭失败。Bearer 请求不是 ambient credential，因此不使用 CSRF，但仍必须通过 Host 门。
9. 鉴权失败使用固定 401/403/429 响应并带 `Cache-Control: no-store`；HEAD 无 body。安全 header 必须覆盖中间件拒绝响应。CORS 保持禁用，任何 secret 都不得进入 HTML、生成 JavaScript、local/session storage、service-worker 状态、URL 或响应诊断。
10. 作者项目 lookup 只有在 matched 时才发出 domain-separated 的不透明 `observation_fingerprint`，它绑定作者、当前 profile、完整 publication、selector 与精确 item 指纹。not-found、incomplete、ambiguous 或失败 lookup 不提供确认权威。
11. `POST /api/v1/media-server/playback-evidence` 只接受规范 author UUID 与该不透明 fingerprint，并且只允许具有有效 CSRF 的已鉴权浏览器 session。即使 Bearer 有效，也不得用于该真人确认 mutation。请求不能接受 provider、profile、Library、path、item ID、Etag、publication ID、timestamp 或自由文本。
12. 写入前，服务端必须执行完整 target resolve/manifest 检查、一次有界唯一 item lookup，再次完整 resolve；两个 target 与重算 fingerprint 必须一致。publication/profile/selector/item 任一漂移、伪造 digest、不完整工作或远端歧义都必须零写入。
13. Revision `0008_playback_evidence` 只新增一张 append-only 表，保存安全 UUID、四个上下文 digest、observation fingerprint、服务端观察时间与操作者确认时间，并以 RESTRICT 外键关联 Author 和 publication Job。不得保存 raw JSON、state/update 列、远端 item ID、path、provider value、Etag、credential、session、CSRF、IP、Host、Origin 或 User-Agent。
14. Observation fingerprint 是自然唯一身份。串行或并发重复请求都返回原始行及原始时间作为 replay；SQLite 与 PostgreSQL 最多生成一行。同一 fingerprint 下字段冲突关闭失败。该 endpoint 不接受通用 `Idempotency-Key` 契约。
15. 本阶段永不更新或删除证据。当前身份变化后，历史证据保留但标为 stale。Qualification schema v3 将 `playback_evidence` 标记为 `IMPLEMENTED`；只有与当前 profile/publication/selector/item 权威一致的证据才授予真人 `PASS`，否则保持 `NOT_RUN` 并另行返回有界 stale 事实。
16. `provider_task_completion` 继续为 `NOT_IMPLEMENTED / provider_api_unsupported`，`automatic_post_export_scan` 继续为 `NOT_IMPLEMENTED`。已接受刷新、已观察项目、Bearer 自动化、本地/mock 测试或旧 stale 确认都不能推断 provider 完成或播放 PASS。
17. Web 控制台增加登录壳、统一 401/session 过期处理、内存 CSRF 传播、安全的 SSE/媒体/QR cookie 兼容，以及只在当前 matched lookup 后启用的显式确认弹窗。文案必须说明这是操作者对实际播放的确认，应用并未远程测量播放。
18. 测试枚举每条应用路由来证明匿名 allowlist，而不是抽样 endpoint；覆盖 auth/session/CSRF/Host/Origin/限流/脱敏、archive HEAD/Range、SSE handler 前拒绝、QR、docs、legacy、migration、repository 竞态、TOCTOU、qualification 真值、Web、打包与回滚。

## 回滚与证据真值

浏览器 session 有意只存在于进程内，重启即消失，不属于备份数据。播放证据是持久审计数据。只有 evidence 表为空时才能从 revision 0008 在线 downgrade；只要存在一行，就以固定码阻止 downgrade。offline downgrade 被拒绝。旧 binary 不得服务 revision 0008 数据库，也绝不能用于恢复匿名访问；回滚必须有兼容鉴权层或网络隔离，并保留全部证据行。

本地与 mock 验证只证明实现行为。在获授权操作者使用真实 Emby/Jellyfin、实际播放项目并显式确认前，仓库真人播放状态保持 `NOT_RUN`。

## 明确排除

- 浏览器可写媒体服务器设置或 secret、多 profile、凭据轮换 UI、反向代理信任。
- Subscription/Account 删除、保留、级联清理、孤儿修复、强制覆盖及 evidence DELETE/PATCH/PUT。
- 自动 export-to-scan、provider-specific 后台任务完成、播放遥测、转码与内嵌播放器。
- 多用户、角色/RBAC、SSO、OAuth/OIDC、MFA、密码重置、恢复码与持久浏览器 session。
- 七平台/CDN/Linux 部署或 Emby/Jellyfin 真人资格执行；这些继续归执行 0047。
