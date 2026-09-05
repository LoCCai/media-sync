[English](security-review.md) | **中文**

# 安全与隐私审查（执行 0046）

范围：执行 0046 首次建立的逐项自审，已校准到执行 0054 阶段 B、执行 0055 后端鉴权提交 `f19bfaa`、播放证据持久化提交 `1d5b448` 及当前仅浏览器确认检查点；每项声明均附强制机制。这是自审，不是外部审计。后端边界、仅 matched observation 身份、append-only 持久化及防 TOCTOU 的确认 service/API 已实现并通过离线验证；安全 current/stale 投影、qualification schema v3 与 Web login/CSRF/确认客户端尚未实现。

## 1. 凭据与机密

| 声明 | 强制机制 |
| --- | --- |
| 原始 Cookie/密码绝不进入数据库、配置、日志、argv 或 Git | 需求 AUTH-004；账户只存不透明 `credential_ref`；QR/OTP 材料只存在于登录子进程内 |
| 管理凭据在 `serve` 绑定前解析且绝不持久化 | 必需的类型化操作者引用通过 `env:` / 受限 `file:` / `keyring:` 解析，值只转为进程内摘要；可选自动化 Bearer 使用不同的引用和值。固定启动/登录/审计码都不披露它们 |
| 浏览器权限只存在于进程内且不可导出 | 唯一轮换的不透明 HttpOnly、`SameSite=Strict` session Cookie 与仅存内存的 CSRF 值会在超时、退出、重启或凭据替换时失效；二者都不属于备份或支持包 |
| 爬虫/账户机密只在对应进程边界解析；媒体服务器 API key 只在最终 connector 边界解析 | `security/secrets.py` 提供 `env:` / `keyring:` / 受限相对 `file:` scheme；执行 0054 阻止完整媒体服务器 reference 与值进入 API 响应、Operation payload 和 SQLite |
| 播放 observation 身份不披露原始服务器 selector | 只有完整且唯一 `matched` 的 lookup 才派生该值：先在 profile/publication/selector 上下文中哈希有界远端 item ID，再把摘要绑定规范作者。`not_found` 既不携带 item fingerprint，也不携带 observation fingerprint；原始 item ID 与路径绝不进入账本 |
| 播放证据持久化会保留首个持久行 | Revision `0008` 约束规范 UUID、小写 SHA-256 摘要、时间顺序、唯一 observation 身份及 `RESTRICT` 作者/publication Job 父项。仓储只提供 create-or-exact-replay；冲突身份会关闭失败，非空表会阻止 downgrade，且 service 只在应用拥有的事务提交后发送固定成功审计码。默认 `serve` 日志会为 `media_sync` 命名空间配置独立 stderr handler，使固定 INFO 审计可见且不修改或移除 Uvicorn 默认项 |
| 签名 CDN URL 仅运行时存在 | 详情协议子进程在有界 frame/内存中携带；持久化前递归剥离（执行 0009、0013+）；留存树扫描断言零匹配 |
| 创作者权限引用为机密类型 | `creator_input.secret_ref` 走 `SecretValue` 来源；含义不明的 query/fragment URL 默认拒绝 |
| API 请求不能提供媒体服务器配置 | 启动时只校验一个不可变、由环境变量托管的配置；API 仅返回手工安全摘要，不包含 API key、完整 reference、Library ID、服务器路径或网络范围 |

## 2. 进程边界

| 声明 | 强制机制 |
| --- | --- |
| 上游爬虫绝不导入主服务 | ADR-0001：外部锁定 checkout 作为子进程；模块身份检查（`_module_belongs_to_checkout`）拒绝外来模块 |
| Cookie 只走私有环境通道 | 桥接经环境变量注入、由小型 runner 读取并在导入前移除；公开 argv 只含入口 + 受限 spec 路径 |
| 登录/抓取子进程被确定性回收 | 父进程 START/CANCEL/EOF framing、结果后 guardian、Windows Job 对象 / POSIX 进程组（执行 0012） |

## 3. 网络与文件系统策略

| 声明 | 强制机制 |
| --- | --- |
| 下载只到达公网已验证地址 | 每一跳 DNS 答案必须为公网；连接钉定；手动重定向跨源丢弃 Range validator |
| 媒体服务器调用只到达已配置 origin 与显式网络策略 | 每一页 lookup 与 POST 都会按操作者允许的 IP/CIDR 重新校验全部 DNS 答案，固定连接并保留 Host/TLS SNI，禁用环境代理，拒绝重定向和服务器 next link；请求不能覆盖目标 |
| 下载路径无法逃逸配置根 | 路径收容 guard；每个目录做 symlink/lstat 检查；归档 blob 为不可变 no-clobber 链接 |
| 上游二进制下载保持关闭 | 桥接配置强制 `ENABLE_GET_MEIDAS/GET_MEDIAS = False` |

## 4. 服务暴露

| 声明 | 强制机制 |
| --- | --- |
| 缺少有效操作者权限时 `serve` 在绑定前失败 | 缺失、畸形、弱、无法解析或冲突的凭据输入会在 Uvicorn 启动前统一成为固定配置错误；不存在生产匿名模式开关 |
| 默认拒绝的路由边界 | 首先校验精确原始 Host。只有 health/readiness、login/session bootstrap、公开根与实际存在的 immutable 启动资源可匿名访问；业务 API、二维码/归档字节、SSE、深度就绪、支持包、OpenAPI/docs、`/legacy` 与经鉴权 SPA 深链接都要求有效 session，或在允许处使用可选 Bearer |
| 浏览器 mutation 要求同源证明 | 登录要求精确配置的 Origin；每个 Cookie 鉴权不安全请求还要求同一 Origin 与绑定 session 的 CSRF header。CORS 关闭；转发 Host/proto header 不授予权限 |
| 播放确认仅允许浏览器并重新校验当前权威 | 最外层 middleware 会在读取正文或进入 handler 前拒绝该 endpoint 的 Bearer-only 及任意 Cookie/Authorization 混用请求。Handler 再要求浏览器 auth 标记、精确 Origin 与 CSRF，拒绝 `Idempotency-Key`，并且只接受最大 1 KiB、无重复成员、包含规范作者 UUID 与小写 observation fingerprint 的 JSON 对象。Service 使用一个有界 deadline 与 authority lock 执行 resolve A → 一次完整唯一 lookup → resolve B，比对两个 target 与重算身份，释放 authority lock 后才打开短 create-or-replay 事务。任一漂移、不匹配、未完成或歧义 lookup 都零写入 |
| 容器回环拓扑是显式配置 | 镜像内部绑定 `0.0.0.0`，示例 Compose 只发布 `127.0.0.1:8632`，从仓库外挂载必需凭据，并只允许 `http://127.0.0.1:8632`；非回环浏览器 origin 必须使用 HTTPS |
| 不夸大 Web 集成 | Console v2 与 `/legacy` 尚未 bootstrap session 或传播 CSRF；即使后端边界已启用，它们当前也不是可操作的管理客户端 |
| 结构化日志与持久 Operation/证据界面已脱敏 | 机密分类名称在落点掩码；原始适配器异常绝不进入 CLI/API 输出。含 selector 的依赖 wire 消息会整体替换为固定文本；原始或百分号编码的媒体服务器路径/provider 值、远端 item ID、Etag 与远端错误正文不能进入日志、SQLite、Event、SSE、API 结果或支持包；revision `0008` 只保存绑定上下文的摘要与规范本地身份。确认响应只返回 schema version、证据/作者 ID、服务端时间戳及 replay 状态，绝不返回提交的 fingerprint、publication Job 或四个内部 digest |

## 5. 隐私

- 归档有意把内容关联到用户订阅的作者；采集受每订阅 `max_items`、请求延迟与封闭 request profile 约束；评论与关键词抓取为明确非目标。
- 浏览器 profile 按“平台 × 账户”隔离在 0o700 运行根下；为 Web 控制台中继的二维码图也在同一根内，并随登录尝试删除（执行 0040）。

## 6. 残余风险（如实清单）

1. Web 客户端暂时落后于后端契约：不能登录、在内存持有 CSRF 或统一恢复 session 过期。Web 只同步了 matched lookup response 类型，尚无确认 UI。该状态以 401/403 关闭失败，不会重新开放匿名访问，但会阻塞 Web 管理与真人扫码资格，直到 0055 剩余前端工作完成验证。
2. 这是单操作者鉴权，不是多用户授权。可选 Bearer 拥有广泛自动化权限；非回环部署仍要求经过审查的 HTTPS 终止及精确 Host 保留。公网部署、RBAC、SSO/MFA 与可信反向代理身份均不受支持。
3. 仅浏览器确认 service/API 现已提供经鉴权写入权限，但尚无有界按作者 current/stale 投影、qualification schema v3 或 Web 确认 UI。因此 schema-v2 qualification response 继续把整体 `playback_evidence` 报为 `NOT_IMPLEMENTED` 且真人状态为空，真人播放继续为 `NOT_RUN`。本地/mock 确认不是远端播放遥测，不能产生检入仓库的真人 PASS。
4. SQLite 是唯一受支持的生产存储；拿到磁盘即拿到全部数据，包括凭据*引用*（仍需 secret provider 才能使用）与任何未来播放关联摘要。PostgreSQL 仓储语义带有隔离可选竞态 harness，但新用例尚未在本工作站运行，且不能证明完整 schema 或生产 PostgreSQL 支持。
5. 上游平台行为变化可能改变锁定爬虫的行为；许可证门是确认书，不是对上游行为的技术控制。
6. 未执行外部审计（`NOT_RUN`，操作者可选项）。
