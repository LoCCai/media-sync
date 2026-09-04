[English](plan.md) | **中文**

# 执行 0054 计划

- 状态：已冻结，进入实现
- 计划日期：2026-09-05
- 基线：`22b5864`
- 计划数据库 revision：`0007_media_server_operations`

## 基线与决策

`git pull --ff-only origin main` 确认 `main` 已是最新的 `22b58646e79b17b2d49ff803df34e976466999c3`，工作树只保留既存未跟踪 `.mimosa/`。执行 0053 已交付安全内容/资产目录与归档预览，但 `/api/v1/library` 只是数据库聚合，Web 页面也明确把物理树和媒体服务器行为后移。

既有导出器已经具备严格布局计划、规范 `.media-sync-managed-v1.json`、按作者锁、完整哈希校验、CAS 发布、崩溃恢复，以及对已修改受管文件和非受管文件的保护。整作者发布身份存在成功 `export.emby` Job 的前驱链中；单独的逐内容 `ExportRecord` 不是媒体树权威。当前完全没有媒体服务器 HTTP 客户端或服务器配置。Operation 和数据库 CHECK 只有五种封闭 kind，因此扫描支持必须通过统一 migration、payload 和 coordinator 更新，不能只加 endpoint 走捷径。

冻结的阶段 A 最小范围是一个由环境变量托管的服务器配置。缺少操作者鉴权时，在浏览器写配置并不安全，所以继续延期。连接测试和扫描请求体都不能提供远端目标。扫描成功只表示已配置服务器接受了精确定向刷新。已实现 probe/刷新功能的真人使用是 `NOT_RUN`；扫描完成轮询、项目查找、播放证据写入与自动联动在后续 0054/0055 切片前明确为 `NOT_IMPLEMENTED`。

## 交付顺序

1. 在实现前提交本双语目标、计划、进行中日志与变更前验证基线。
2. 新增公开不可变的导出检查模型与只读检查方法；复用规范 manifest 解析、路径检查、同描述符哈希/身份检查与固定漂移分类，不暴露私有文件系统对象。单独新增 existing-only 作者锁原语：它与发布锁不同，绝不能调用 `mkdir`、`O_CREAT`、恢复或清理。
3. 新增应用层读服务，解析作者 UUID、发布 scope 身份、唯一成功发布链 head 及当前源状态。新鲜度为 `not_published`、`current`、`outdated` 或 `blocked`；完整性独立为 `not_available`、`unchecked`、`page_verified`、`complete`、`budget_exhausted`、`drifted` 或 `inconsistent`。只暴露固定安全原因码与动作。
4. 保持 `GET /api/v1/library` 的响应形状、顺序、默认值和字段语义兼容；新增 `GET /api/v1/library/{author_id}`，每页最多 128 个文件。首个响应生成绑定发布 Job 与 manifest SHA 的 cursor；后续页必须带该 cursor，head 变化时返回 409 并重新开始。每页只哈希返回项，使用默认 1 GiB、10 秒的可配置预算，并受进程级 single-flight 限制。只有全部受管文件都落在已验证范围时完整性才是 `complete`。
5. 为不可变 Settings 增加全有或全无的媒体服务器配置：provider、规范 base URL、library ID、API-key secret reference、服务端 library 路径映射、显式允许 IP/CIDR、TLS 校验、有界超时、probe/scan 共用且默认关闭的 operation gate，以及媒体库检查预算。新增不包含 secret reference、网络范围和本机宿主路径的安全配置摘要。
6. 新增平台无关、可 mock 的媒体服务器 connector。仅在请求边界解析 secret；每个 DNS 答案必须符合配置 IP/CIDR；连接绑定；保留 Host/SNI；禁用环境代理和重定向；实施精确 origin、HTTP 方法/路径白名单、响应大小限制、固定 JSON schema 与安全错误码。Probe 使用带认证的 `GET /System/Info` 与 `GET /Library/VirtualFolders`。精确唯一匹配 `ItemId` 后，扫描只调用带固定 recursive/default metadata 参数的 `POST /Items/{ItemId}/Refresh`。不支持定向刷新时关闭失败，绝不回退 `/Library/Refresh`。
7. 把 `media-server-probe` 与 `media-server-scan` 加入封闭 Operation 契约、ORM 约束、请求/结果白名单、恢复策略、API 标签及 migration `0007_media_server_operations`。两者都是无 target、绑定 profile fingerprint 的操作并共用一个 active exclusive key。端点强制默认关闭的 operation gate。Probe 的 GET 阶段只有明确实现时才允许有界安全重试；变更远端的 POST 只尝试一次。POST 前取消可返回 cancelled，dispatch 后任何 transport 不确定性都必须 terminal `acceptance_unknown`。由于没有持久远端 task 身份，重启对账保守标为 `interrupted`。
8. 新增 `GET /api/v1/media-server`、`POST /api/v1/media-server/probe` 与 `POST /api/v1/media-server/scan`。第一个不联网；两个 POST 只提交持久工作，绝不接受 URL/key/path/library 覆盖。状态投影只带最近一次白名单 Operation 证据。
9. 新增 schema version 1 的 `GET /api/v1/qualifications`。每个平台行把 `automated_evidence` 计数与封闭真人状态（`PASS`、`FAIL`、`NOT_RUN`、`BLOCKED_EXTERNAL`）分开；阶段 A 不推导真人 PASS。媒体服务器行关联最近 probe/刷新 Operation，在本工作区将其真人使用标为 `NOT_RUN`，并把扫描完成、项目查找、播放证据与自动联动标为 `NOT_IMPLEMENTED`，而非 `NOT_RUN`。
10. 升级 Library，检查真实受管树，并且只有后端 `allowed_actions` 允许时才请求导出/探测/扫描。升级 Settings，展示脱敏只读配置摘要；Jobs 增加两种新 kind 标签。状态/query 派生放入有测试的 TypeScript 纯函数。
11. 运行安全、导出器、应用、API、migration、Operation 与 Web 专项，然后运行全仓 Ruff/format、strict mypy、完整 Python 套件、Web format/test/check/build、compile/build、文档/上游、tracked-output、本机路径、空白及推送对账门。

## 冻结契约

- 发布权威是 `(作者 UUID, publication scope 摘要, output 身份, 唯一成功 Job 链 head, manifest 身份)`；`ExportRecord.output_path` 或单独文件系统扫描都不能授权媒体树。
- 浏览器只能提交作者 UUID 和绑定 manifest 的不透明 cursor，不能提交 path、filename、脱离 manifest 的 offset、URL、server host、library ID、远端路径、key、网络范围或 secret reference。
- 树响应只列 manifest 受管项；非受管项永远不能成为可浏览入口。漂移分类可以说明非受管或已修改内容阻止安全发布，但不得暴露其名称或字节。
- 已修改的受管文件必须受到保护，不得静默修复；本执行不提供破坏性恢复。
- 媒体服务器 origin 与允许 IP/CIDR 在启动时规范化，并共同成为唯一网络权威；每个 DNS 答案都必须落在配置策略内，跨 origin 或任意重定向都必须在转发凭据前拒绝。
- secret material 只在 connector 边界以 `SecretValue` 存在；异常消息、响应样本、服务器正文和 header 不得进入持久状态。
- Probe/scan Operation 摘要只使用固定 provider/state、保守版本字符串、已配置 library 身份摘要以及计数/时间。服务器 URL、library 名称/路径、key/ref、请求 header、响应正文及远端错误正文全部缺席。
- Probe 与 scan 共用一个互斥域。服务端 operation gate 是权威；Web `allowed_actions` 只负责呈现。
- `media-server-scan` 只表示精确定向刷新已接受，不表示已完成或可播放。已经 dispatch 但未确认的 POST 必须是不可重试的 `acceptance_unknown`，任何代码都不得把它翻译成 cancelled 或可安全重试。资格视图必须分别标记自动化证据、真人资格及 `NOT_IMPLEMENTED` 能力。

## 验证计划

- 导出器/应用：golden tree、绑定 manifest 的 cursor、head 变化 409、精确 page/complete/budget 范围、current/outdated/blocked/not-published 新鲜度、manifest 畸形、错误身份、缺失/修改/替换/链接/大小写碰撞、existing-only 锁、single-flight 与检查预算、无修复、无锁/目录创建及哨兵不泄露。
- 配置/connector：全有或全无校验、URL/CIDR 规范化、精确 origin 与路由方法、显式允许的私网目标、全 DNS 答案网络策略、DNS 绑定、TLS 模式、无代理/重定向、认证 header sink、超时/header/正文/条目限制、畸形 JSON、provider 差异、library 缺失/重复及 secret/错误脱敏。
- Operation/migration/API：全新与升级 SQLite 上的新 kind 约束，并在已有覆盖中检查 PostgreSQL SQL；请求 fingerprint、结果摘要、幂等重放、共用配置互斥、端点门、dispatch 前取消、dispatch 后接受状态不确定、保守重启对账、安全资格投影、旧 library 响应兼容及读取不修改持久状态。
- Web：树分组/分页、状态/动作派生、资格标签、无路径/ref 呈现、请求竞态、Operation 链接、format、Vitest、Svelte check、生产 build，以及 fake API 或有界本地测试服务上的浏览器 smoke。
- 外部：已实现 Emby/Jellyfin probe 和定向刷新的真人使用继续 `NOT_RUN`。扫描进度、项目查找、播放证据和自动联动在阶段 A 是 `NOT_IMPLEMENTED`。Linux 主机演练、账户、平台 API 与 CDN 继续 `NOT_RUN`。

## 提交与回滚策略

按以下顺序使用可评审的双语提交：计划/基线；媒体库检查；媒体服务器 connector；Operation/API/migration；Web 控制台；收尾证据。每个通过的边界都推送到 `origin/main`。一旦存在新 kind 行，revision `0007_media_server_operations` 就是承载数据的 forward-only migration：downgrade 必须在不删除审计行的前提下关闭失败，旧应用也不得针对该数据库回滚；空数据库或不存在新 kind 行的数据库可以走已测试 downgrade。不计划破坏性数据迁移。`.mimosa/`、`.upstream/`、数据库、secret、archive/export/job 运行数据、`node_modules`、Web build、`.svelte-kit`、`dist`、缓存与 XML 报告继续排除。
