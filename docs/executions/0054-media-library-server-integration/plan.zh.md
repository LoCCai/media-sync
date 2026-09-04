[English](plan.md) | **中文**

# 执行 0054 计划

- 状态：已冻结，进入实现
- 计划日期：2026-09-05
- 基线：`22b5864`
- 计划数据库 revision：`0007_media_server_operations`

## 基线与决策

`git pull --ff-only origin main` 确认 `main` 已是最新的 `22b58646e79b17b2d49ff803df34e976466999c3`，工作树只保留既存未跟踪 `.mimosa/`。执行 0053 已交付安全内容/资产目录与归档预览，但 `/api/v1/library` 只是数据库聚合，Web 页面也明确把物理树和媒体服务器行为后移。

既有导出器已经具备严格布局计划、规范 `.media-sync-managed-v1.json`、按作者锁、完整哈希校验、CAS 发布、崩溃恢复，以及对已修改受管文件和非受管文件的保护。整作者发布身份存在成功 `export.emby` Job 的前驱链中；单独的逐内容 `ExportRecord` 不是媒体树权威。当前完全没有媒体服务器 HTTP 客户端或服务器配置。Operation 和数据库 CHECK 只有五种封闭 kind，因此扫描支持必须通过统一 migration、payload 和 coordinator 更新，不能只加 endpoint 走捷径。

冻结的最小范围是一个由环境变量托管的服务器配置。缺少操作者鉴权时，在浏览器写配置并不安全，所以继续延期。连接测试和扫描请求体都不能提供远端目标。扫描成功只表示已配置服务器接受了目标刷新请求；除非之后记录真实操作者证据，真人扫描完成和播放仍是独立的 `NOT_RUN` 资格行。

## 交付顺序

1. 在实现前提交本双语目标、计划、进行中日志与变更前验证基线。
2. 新增公开不可变的导出检查模型与只读检查方法；复用规范 manifest 解析、路径检查、同描述符哈希/身份检查与固定漂移分类，不暴露私有文件系统对象。单独新增 existing-only 作者锁原语：它与发布锁不同，绝不能调用 `mkdir`、`O_CREAT`、恢复或清理。
3. 新增应用层读服务，解析作者 UUID、当前可导出源 fingerprint、发布 scope 身份及唯一成功发布链 head，返回带有界稳定文件分页和固定允许动作的 `not_published`、`current`、`outdated`、`drifted` 或 `inconsistent`。
4. 保持 `GET /api/v1/library` 字节级兼容，并新增带有界 offset/limit 的 `GET /api/v1/library/{author_id}`。响应必须显式投影，只含作者内逻辑相对路径。每个文件页都做哈希校验；响应区分 `page` 与 `complete` 完整性，确保分页或检查字节/文件预算不会把未检查文件说成健康。
5. 为不可变 Settings 增加全有或全无的媒体服务器配置：provider、规范 base URL、library ID、API-key secret reference、服务端 library 路径映射、显式允许 IP/CIDR、TLS 校验、有界超时及默认关闭的扫描门。新增不包含 secret reference、网络范围和本机宿主路径的安全配置摘要。
6. 新增平台无关、可 mock 的媒体服务器 connector。仅在请求边界解析 secret；DNS 与连接绑定；保留 Host/SNI；禁用环境代理和重定向；实施精确 origin、HTTP 方法/路径白名单、响应大小限制、固定 JSON schema 与安全错误码。同时支持 Emby/Jellyfin 兼容的服务器信息、virtual folder 发现和一次已配置 library 刷新。
7. 把 `media-server-probe` 与 `media-server-scan` 加入封闭 Operation 契约、ORM 约束、请求/结果白名单、恢复策略、API 标签及 migration `0007_media_server_operations`。两者都是无 target、绑定 profile fingerprint 的操作；扫描使用按配置互斥键，并在每个网络阶段前检查取消。由于没有持久远端 task 身份，重启对账保守标为 `interrupted`。
8. 新增 `GET /api/v1/media-server`、`POST /api/v1/media-server/probe` 与 `POST /api/v1/media-server/scan`。第一个不联网；两个 POST 只提交持久工作，绝不接受 URL/key/path/library 覆盖。状态投影只带最近一次白名单 Operation 证据。
9. 新增资格投影。七平台真人行继续明确为 `NOT_RUN`；本地内容/归档/导出计数只作为自动化证据。媒体服务器探测和扫描触发证据关联精确 Operation；没有操作者证据时，扫描完成和抽样播放继续 `NOT_RUN`。
10. 升级 Library，检查真实受管树，并且只有后端 `allowed_actions` 允许时才请求导出/探测/扫描。升级 Settings，展示脱敏只读配置摘要；Jobs 增加两种新 kind 标签。状态/query 派生放入有测试的 TypeScript 纯函数。
11. 运行安全、导出器、应用、API、migration、Operation 与 Web 专项，然后运行全仓 Ruff/format、strict mypy、完整 Python 套件、Web format/test/check/build、compile/build、文档/上游、tracked-output、本机路径、空白及推送对账门。

## 冻结契约

- 发布权威是 `(作者 UUID, publication scope 摘要, output 身份, 唯一成功 Job 链 head, manifest 身份)`；`ExportRecord.output_path` 或单独文件系统扫描都不能授权媒体树。
- 浏览器只能提交作者 UUID 和有界分页参数，不能提交 path、filename、URL、server host、library ID、远端路径、key 或 secret reference。
- 树响应只列 manifest 受管项；非受管项永远不能成为可浏览入口。漂移分类可以说明非受管或已修改内容阻止安全发布，但不得暴露其名称或字节。
- 已修改的受管文件必须受到保护，不得静默修复；本执行不提供破坏性恢复。
- 媒体服务器 origin 与允许 IP/CIDR 在启动时规范化，并共同成为唯一网络权威；每个 DNS 答案都必须落在配置策略内，跨 origin 或任意重定向都必须在转发凭据前拒绝。
- secret material 只在 connector 边界以 `SecretValue` 存在；异常消息、响应样本、服务器正文和 header 不得进入持久状态。
- Probe/scan Operation 摘要只使用固定 provider/state、保守版本字符串、已配置 library 身份摘要以及计数/时间。服务器 URL、library 名称/路径、key/ref、请求 header、响应正文及远端错误正文全部缺席。
- `media-server-scan` 只表示目标刷新已接受，不表示已完成或可播放。资格视图必须使用不同标签区分自动化证据和真人资格。

## 验证计划

- 导出器/应用：golden tree、确定性分页与精确 page/complete 范围、current/outdated/not-published、manifest 畸形、错误身份、缺失/修改/替换/链接/大小写碰撞、existing-only 锁、检查预算、无修复、无锁/目录创建及哨兵不泄露。
- 配置/connector：全有或全无校验、URL/CIDR 规范化、精确 origin 与路由方法、显式允许的私网目标、全 DNS 答案网络策略、DNS 绑定、TLS 模式、无代理/重定向、认证 header sink、超时/header/正文/条目限制、畸形 JSON、provider 差异、library 缺失/重复及 secret/错误脱敏。
- Operation/migration/API：全新与升级 SQLite 上的新 kind 约束，并在已有覆盖中检查 PostgreSQL SQL；请求 fingerprint、结果摘要、幂等重放、扫描互斥、取消边界、保守重启对账、安全状态投影、旧 library 响应兼容及读取不修改持久状态。
- Web：树分组/分页、状态/动作派生、资格标签、无路径/ref 呈现、请求竞态、Operation 链接、format、Vitest、Svelte check、生产 build，以及 fake API 或有界本地测试服务上的浏览器 smoke。
- 外部：真实 Emby/Jellyfin、真实播放、自动扫描、Linux 主机演练、账户、平台 API 与 CDN 在本工作区继续 `NOT_RUN`。

## 提交与回滚策略

按以下顺序使用可评审的双语提交：计划/基线；媒体库检查；媒体服务器 connector；Operation/API/migration；Web 控制台；收尾证据。每个通过的边界都推送到 `origin/main`。migration 只放宽 Operation kind CHECK，并提供空数据库 downgrade 路径；不计划破坏性数据迁移。`.mimosa/`、`.upstream/`、数据库、secret、archive/export/job 运行数据、`node_modules`、Web build、`.svelte-kit`、`dist`、缓存与 XML 报告继续排除。
