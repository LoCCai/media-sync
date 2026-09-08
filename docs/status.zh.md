[English](status.md) | **中文**

# 项目统一状态（单一事实来源）

## 最新：部署来源身份与 XHS 金丝雀预检（0077）

[执行 0077](executions/0077-deployment-provenance-preflight/progress.zh.md)已在 `d6db86a` 实现，关闭了当前 Docker 部署无法识别镜像内应用代码的证据缺口。合格构建只接受完整小写源码 SHA，把它写入 `/opt/BUILD-MANIFEST.txt` 与 OCI revision 标签，并继续排除项目自身 `.git`。缺少来源身份显式为 `not_run`；畸形或重复值安全失败且不反射原值。

经认证的 deep-readiness API、诊断页与 `media-sync doctor --deep --accept-mediacrawler-license --json` 现在共享同一份安全证据：经过验证的应用 SHA、数据库当前/预期 migration、B 站/XHS 实际续跑间隔、钉定 MediaCrawler checkout/runtime/browser 检查及固定状态。已知旧 migration 可见但不是 current；未知数据库文本与畸形前端值保持隐藏。CLI 可以在不启动驻留 supervisor 的情况下独立检查 API/supervisor 服务定义。

最终本地门禁通过：Python 完整套件 `7140 passed, 42 skipped, 1 warning`；Web 完整套件 `28 files / 825 tests`；Svelte 检查/构建、Prettier、Ruff lint/format、160 个源码文件 strict mypy、compileall、62 包锁文件、两个钉定上游、制品构建及文档检查均通过。准确修正与命令见[0077 验证](executions/0077-deployment-provenance-preflight/verification.zh.md)。

当前 Windows 工作站没有 Docker，未构建/检查 Linux 镜像，也未修改服务器。真实 Docker/OCI 证据、migration `0015`、API/supervisor 比较、XHS 登录/采集/CDN/目录/重启金丝雀、驻留 supervisor、PostgreSQL 与可选媒体服务器读取仍为 `NOT_RUN`。后续遵循[部署交接](executions/0077-deployment-provenance-preflight/deployment-handoff.zh.md)；XHS 结果形成记录前不得开始抖音交付。

## 上阶段：XHS 创作者笔记耐久交付（0076）

[执行 0076](executions/0076-xhs-creator-notes-delivery/progress.zh.md)已在 `47ca107` 实现，完成一个精确 XHS 创作者笔记 Subscription 的确定性本地路径。锁定版 MediaCrawler 作者接口被封装成逐页有界单元，逐字保留不透明 cursor、页面见证及已完成笔记身份，因此较小的 `max_items` 不会丢弃一个已列出 30 条页面的剩余内容。列表页 `xsec_token` 只存在 child 内存中，以摘要绑定精确笔记身份；详情重试前会重新列出页面取得新 token。

Migration `0015_xhs_creator_notes` 增加取得交付资格的 `backfill -> reconciling -> incremental` 进度及显式 `blocked` 阶段。只有精确来源 Run 的精确 pipeline receipt 才能推进状态。已交付的 `has_more=false` 是源末尾证据；`access_restricted`、`empty_page_stalled`、单元上限和逐笔记详情失败保持独立。进入增量前必须完成稳定头部对账，源末尾观察不代表历史已永久完整。

已接受的 normal/video 笔记会通过精确 Run 内容选择进入既有可验证下载、SHA-256 归档和已配置的本地 Emby/Jellyfin 兼容目录/NFO 写入器，无需连接媒体服务器。一条不可用或不支持的笔记会如实形成部分结果，不隐藏同页有效内容。REST/Web 公开封闭进度与固定失败码，但不泄露 token、cursor、作者引用、平台原始载荷或宿主路径。API 与 supervisor 必须配置相同的 `MEDIA_SYNC_XHS_SCAN_CONTINUATION_DELAY_SECONDS`；`0` 只关闭快速节奏，仍保留普通调度与进度。

最终本地门禁通过：Python 完整套件 `7128 passed, 42 skipped, 1 warning`；Web 完整套件 `27 files / 820 tests`；Svelte 检查/构建、Prettier、Ruff lint/format、160 个源码文件 strict mypy、compileall、62 包锁文件、两个钉定上游、制品构建及文档检查均通过。准确修正记录和命令见[0076 验证](executions/0076-xhs-creator-notes-delivery/verification.zh.md)。

Linux/Docker、真实 PostgreSQL、真人 XHS 登录/API/CDN、宿主 archive/library/NFO、重启、驻留 supervisor 及可选媒体服务器读取仍为 `NOT_RUN`。后续按[下一交付](executions/0076-xhs-creator-notes-delivery/next-delivery.zh.md)先做受操作者控制的部署金丝雀，再设计来源优先的抖音交付。执行 0077 尚未开始。

## 上阶段：暂停态订阅策略编辑器（0075）

[执行 0075](executions/0075-paused-subscription-policy-editor/progress.zh.md)已在 `aec3eac` 实现，为未删除、已暂停且空闲的 MediaCrawler 订阅增加一项封闭、带修订栅栏的策略修改。REST、CLI 与 Web 共用同一服务，覆盖同步周期、单次上限、上游请求间隔和浏览器模式；只有 B 站另有采集范围。XHS、抖音、快手、微博、贴吧和知乎使用四项通用控制，且不能接收 B 站 scope。

短事务会预占 SQLite writer 或锁定精确 PostgreSQL 行，在事务内复核活动 Job/Run/operation 所有权并比较 `expected_schedule_revision`。真实变化只递增一次，精确 no-op 不递增。全历史确认、不透明作者引用、cursor、checkpoint/水位/时间/失败状态、`next_run_at`、扫描/交付证据、历史及媒体均保持不变；编辑器不会把暂停、恢复、取消、采集、下载或导出作为副作用。

最终本地门禁通过：Python 专项 `40 passed, 2 skipped, 1 warning`；Python 完整套件 `7067 passed, 43 skipped, 108 warnings`；Web 完整套件 `27 files / 818 tests`；Svelte 检查/构建、Prettier、Ruff lint/format、156 个源码文件 strict mypy、compileall、62 包锁文件与两个上游检查，以及新 wheel/sdist 构建。合成 Chrome QA 在 1440×900 与 390×844 下通过 B 站和 XHS 保存，控制台警告/错误、页面异常及失败请求均为 0。准确命令和边界见[0075 验证](executions/0075-paused-subscription-policy-editor/verification.zh.md)。

0075 的两项 PostgreSQL 用例已收集，但因没有配置真实 PostgreSQL URL 而跳过。Docker/Linux、真人账户/平台/CDN、宿主归档/媒体库/NFO、媒体服务器及 supervisor 行为全部仍为 `NOT_RUN`。下一实现设计从 XHS 自身的有界作者笔记分页、源末尾证据、对账和交付资格增量开始，不复制 B 站 cursor 语义。

## 上阶段：B 站投稿耐久回填转增量交付（0074）

[执行 0074](executions/0074-bili-backfill-incremental-delivery/progress.zh.md)已在 `9c81c4b` 完成本地实现，贯通一个精确 B 站投稿 Subscription。每个成功 Run 最多记录 30 个有序 Content 观察；只有封闭的来源 Run pipeline receipt 才能推进耐久 `backfill -> reconciling -> incremental` 状态。到达源末尾会重置有界 head lane，只有稳定且已交付的头部对账才发布 `baseline_snapshot_complete`。认证、作者、策略、scope 或锁定上游漂移会使不兼容证据失效。

交付按完整 Content 隔离。损坏的多分段 Content 不会发布，也不会隐藏其他无关完整 Content；重试积压保持显式。receipt/API/Web 投影区分本轮来源与重试积压，显示固定的部分成功/失败计数，并安全保留 predecessor 媒体。受控 fixture 证明 67 条跨批次完成、漂移后的 68 条来源、后来一条投稿真实下载/归档/NFO 发布，以及不改变任何字节或 mtime 的零工作重跑。Emby/Jellyfin 服务器控制继续为可选项。

最终离线门禁通过：Python `7048 passed, 41 skipped, 108 warnings`、media-sync Web 完整套件（`26 files / 802 tests`）、Svelte 检查/构建、全仓 Prettier、Ruff lint/format、155 个源码文件的 strict mypy、两个锁定上游及 wheel/sdist 构建。完整审查、已修正门禁失败与精确边界见[0074 验证](executions/0074-bili-backfill-incremental-delivery/verification.zh.md)。

Docker/Linux 部署、真人 B 站登录/profile 认领、UID `252671524`、平台请求、CDN 字节、宿主最终归档/媒体库/NFO、后续真人增量周期及 supervisor restart 全部仍为 `NOT_RUN`。

## 上阶段：把 MediaCrawler 原生会话接入订阅（0073）

[执行 0073](executions/0073-mediacrawler-session-adoption/progress.zh.md)已在 `165516a` 实现，完成经鉴权原生 `/crawler/` 登录面到既有 Subscription 流水线的确定性接缝。操作者用上游 QR/Cookie 控件登录，等待控制台进程空闲，再把该平台保存的 profile 显式认领给同平台 Account。media-sync 不跟随链接地安全复制普通文件，用禁止 QR 回退的非交互 saved-session 探针校验快照，在 Account profile 锁下原子安装，并在认证 revision 冲突时恢复旧 profile。内部路径、Cookie 和原始异常不会进入公开 API。

认领成功会发布 `saved_session/authenticated`、递增 Account 认证 revision，并只恢复该 Account 的 `waiting_auth` 同步 Job。集成证明确认精确安装的 Account profile 不经 Cookie secret 解析即进入 scheduler BridgeRequest 与 process spec，随后成功完成规范化摄取。共享 `/data/mediacrawler/webui-output` 继续只是交互控制台产物区，不会导入无关 Job；既有 Job 级 receipt、下载/归档及平台/作者目录与 NFO 输出仍是权威。Emby/Jellyfin 服务器控制为可选项。

0073 最终离线证据通过：Python 完整 unit 套件（`4683 passed, 3 skipped, 1 warning`）、media-sync Web 完整套件（`26 files / 799 tests`）、Svelte 检查/构建、全仓 Prettier、Ruff lint/format、154 个源码文件的 strict mypy、两个锁定上游检查及 Python 制品构建。精确命令、一项已修正的过时路由数量失败与资格边界见[0073 验证](executions/0073-mediacrawler-session-adoption/verification.zh.md)。部署 `165516a` 前，既有线上 0072 `/crawler/` 返回 `license_acknowledgement_required`，证明其 API 容器尚未单独收到 `MEDIA_SYNC_MEDIACRAWLER_LICENSE_ACKNOWLEDGED=true`；supervisor CLI 确认不能替代，且该观察不能识别 0073 镜像。强制重建容器后的访问、真人 profile 认领及七平台采集/下载/CDN/历史/增量结果仍为 `NOT_RUN`。

## 上阶段：精确订阅交付与安全进程诊断（0069–0070）

[0069](executions/0069-exact-subscription-delivery/progress.zh.md)把一次订阅操作贯通为唯一精确耐久 scheduler → 采集 → pipeline → 兼容目录链；不消费无关任务，可从 supervisor 抢占、重试和重启中凭封闭 receipt 恢复，不要求连接 Emby/Jellyfin 服务器，并保留非永久的逐 feed 扫描证据。审查驱动的栅栏阻止重复链；迁移降级与 Windows exporter 目录 pin 已加固，实施提交 `b22e938` 已发布，证据见[验证](executions/0069-exact-subscription-delivery/verification.zh.md)。

[0070](executions/0070-process-output-diagnostics/progress.zh.md)把有界、脱敏安全的扫码/采集子进程诊断接入既有轮转日志中心，覆盖真实锁定版 MediaCrawler 前缀及精确 Operation/session/Job/Run 关联。账户页可把失败或中断登录直达精确日志查询。最终离线门禁为 Python 6924 个唯一测试、Web 781 项通过；所有修正过的失败见[验证](executions/0070-process-output-diagnostics/verification.zh.md)，操作步骤见[使用说明](executions/0070-process-output-diagnostics/usage.zh.md)。

两项增量都尚未部署或真人验收，旧扫码失败仍不可恢复。下一步：部署本 revision，只复现一个失败平台并读取新增安全进程证据，再执行一次有界订阅交付 canary。Cookie/profile/detail/download 子进程输出仍是明确披露的日志缺口；Linux/PostgreSQL/真人平台/CDN/目录播放验收及总体七平台目标继续开放。

## 上阶段：持久日志中心与精确登录证据（0068）

[0068](executions/0068-log-center/progress.zh.md)实现私有轮转分片、可观察扫码阶段、精确生命周期关联、鉴权查询及中文诊断下载。这解决证据丢失，不代表平台登录已修复。默认16MiB/日期轮转、7天、1GiB，不记录凭据和第三方原文。覆盖范围、审查修正及测试见[验证](executions/0068-log-center/verification.zh.md)，部署与保留限制见[使用说明](executions/0068-log-center/usage.zh.md)。

本轮没有生产部署/重试、Linux验收或supervisor恢复，旧扫码细节仍不可恢复。下一步是部署后受控单平台诊断、另行发现的Windows exporter目录pin修复，再继续精确订阅/历史转增量/下载验收。崩溃open自动回收和全部依赖原始日志尚未实现，总体目标继续活动。

## 上阶段：共享输出目录与扫码问题复核（0067）

[0067](executions/0067-output-directories/progress.zh.md)实现总目录/七平台覆盖、CAS保存、作者根绑定及API/CLI/独立调度器/媒体树接线。新库按平台分目录，旧库保留平铺；已有发布改根须显式迁移，迁移未实现。无需另外导出或连接媒体服务器。精确测试及发布见[验证](executions/0067-output-directories/verification.zh.md)。

只读浏览器确认DY/KS/贴吧/WB仍扫码超时，Bili/XHS/Zhihu保存为已认证。未宣称修复、未触发生产重试。[下版日志中心](executions/0067-output-directories/next-delivery.zh.md)优先补齐持久分片和精确登录阶段；随后继续精确订阅执行、历史转增量和真实落盘验收。日志中心、这些闭环及总体七平台目标尚未完成。

## 上阶段：失败登录诊断与订阅自动落盘（0066）

[0066 执行](executions/0066-login-failure-and-workflow/progress.zh.md)新增三类固定扫码失败状态，将控制台明确为订阅、自动下载、兼容目录写入流程。限速续跑只作用于严格绑定、确有待续上下文的 B 站扫描，不是永久历史完成。当前测试与发布事实见[验证](executions/0066-login-failure-and-workflow/verification.zh.md)。

紧接着实现[可编辑总目录/平台覆盖、精确订阅执行、历史转增量持久语义和真实下载验收](executions/0066-login-failure-and-workflow/next-delivery.zh.md)。本阶段目录配置仍只读。旧抖音失败不能从通用状态还原，未宣称线上登录已修复。未触发新生产登录、下载或恢复 supervisor，原目标继续。

## 上阶段：抖音/快手Cookie本人校验与知乎有限头像（0065）

[执行0065](executions/0065-cookie-auth-and-avatar/progress.zh.md)已接通两个独立单次本人请求、私密Cookie保存、账户能力与订阅复用，粘贴本人验证现有七平台实现。快手要求Cookie含kuaishou.web.cp.api_ph；抖音使用创作者中心接口；不以目标作者资料或本地标志授予认证。知乎追加有限来源形状头像，失败保留昵称/旧图片。

本轮受影响回归、Web/静态/包和实际失败记录见[验证](executions/0065-cookie-auth-and-avatar/verification.zh.md)，不继承0064全量PASS。小红书资料、剩余头像/媒体、Linux及真人平台/归档/播放仍待完成。历史B站canary未解决，无部署/生产重试/supervisor恢复，原目标保持活动。

## 上一检查点：抖音/贴吧作者资料与贴吧头像（0064，离线验证通过）

[执行0064](executions/0064-douyin-tieba-profiles/progress.zh.md)已贯通抖音单次真实签名资料和贴吧PC签名资料，强制精确返回身份与原始昵称。贴吧可选头像受固定来源路径、同作者portrait、唯一时间戳及既有隔离下载/同源PNG约束；失败保留昵称/旧头像。昵称现覆盖六平台，粘贴Cookie本人校验仍五平台，不因目标作者资料成功改变账户认证。

最终完整unit/contract/integration目录5841通过、37项环境跳过；Web699通过，静态/类型/构建/文档通过，两个包与149应用Python文件逐字节一致。精确耗时、早期失败/修正和发布核对见0064验证，不累加重叠专项。

小红书资料返回身份仍缺可靠来源，不能把请求ID回填称查询成功；抖音/快手本人校验、抖音/快手/知乎头像、剩余媒体和当前Linux/真实平台验收仍必需。资料单次查询不采集内容、无需全历史确认或连接Emby/Jellyfin。源码已冻结，最终回归/发布以[0064验证](executions/0064-douyin-tieba-profiles/verification.zh.md)为准；无生产动作、部署或supervisor恢复，历史B站canary仍未解决。

## 上一检查点：贴吧Cookie与快手/知乎作者昵称（0063，离线验证通过）

[执行0063](executions/0063-platform-access-and-profiles/progress.zh.md)把贴吧严格正向本人验证接入既有私密Cookie保存/账户原子发布，并贯通快手/知乎精确昵称的隔离worker、API、UI和订阅资料凭单。粘贴校验现覆盖B站/小红书/微博/知乎/贴吧；昵称查询覆盖B站/微博/快手/知乎。快手资料只证明作者观察，不是本人认证。统一身份、长ID API和实际script worker接线问题均已复现修正。

最终unit/contract/integration完整目录5456通过、37项环境跳过；Web671通过、静态/构建/文档门禁通过，wheel/sdist与147个应用Python文件字节一致。旧断言失败、最终重跑及账户页旧文案修正均单列保留，不用重复专项累加测试数。

快手/知乎头像仍未实现，需补可信CDN来源证据，UI明确仅昵称。抖音/快手粘贴Cookie本人校验，小红书/抖音/贴吧作者资料，剩余媒体形状和真实Linux/平台/归档/播放验收仍必需。贴吧严格整数no/id与现代portrait是保守接受子集，不代表所有合法响应格式已证明。[验证记录](executions/0063-platform-access-and-profiles/verification.zh.md)保留实际失败、最终门禁及发布。历史真实B站canary仍未解决；无部署、生产重试或supervisor恢复。

## 上一检查点：B站动态采集与本地输出（0062，离线验证通过）

[执行0062](executions/0062-bili-dynamic-workflow/progress.zh.md)接入显式投稿/动态/两者范围、可恢复私密页快照、精确WORD/DRAW/OPUS正文及自有AV引用，贯穿真实锁定client、封存输出、CLI、scheduler和原子入库。动态与普通投稿保持独立身份和计数；旧订阅不静默扩大。已有订阅可在暂停空闲状态按当前修订改范围，保留断点与媒体。

图片精确刷新、真实离线下载/归档/Emby兼容目录输出及重复执行测试已通过专项；无需连接Emby/Jellyfin服务器。图文输出供本地阅读和媒体目录保管，不保证任意HTML/图集可被这些服务器作为视频播放。当前完整回归与发布结果以[验证记录](executions/0062-bili-dynamic-workflow/verification.zh.md)为准，不继承上一轮PASS。

最终冻结源码受影响回归1250通过、15项环境跳过；Web642通过，静态/构建/文档检查通过，两包与144个应用Python源码字节一致。早先完整目录快照及其修正的路由数量失败单列，不合计为最新源码全量。最终组合已覆盖快照崩溃安全发布、范围与成功回读约束。

仍待：当前Linux镜像与真实平台采集/下载/播放验收；三平台粘贴Cookie远程本人校验（抖音/快手/贴吧）、五平台作者资料，以及其他平台的剩余采集闭环。B站转发原文、未知/付费/直播/专栏等子型不冒充已支持；OPUS未知段落不静默丢弃。私密页保留、每单元有界推进不等于完整历史证明。总体七平台目标继续活动，未部署或恢复supervisor。

## 上一检查点：内容归属与耐久冲突处理（0061）

[执行0061](executions/0061-bili-dynamic-authority/progress.zh.md)阻止已保存内容身份在upsert时改挂另一作者。SQLite/PostgreSQL在实际冲突更新中约束作者，同作者资料刷新及dynamic/投稿身份分离保持支持。固定`content_ownership_conflict`说明原归属被保留，不再降级成schema_invalid或Cookie错误；终止该Job，不自动重试、不影响账户熔断，未来正常订阅周期另计。

现已补齐确认丢失/租约过期时精确Run/Job冲突恢复，以及存储无法确认时报告unknown的CLI读回，不再虚报失败终态。验证与发布状态见[执行记录](executions/0061-bili-dynamic-authority/verification.zh.md)。不删除或隐式重归属已有文件/归档，也不抹掉旧模式此前已提交批次。无schema迁移、上游/依赖变更或生产动作。

最终源码受影响回归551通过（13项PG环境跳过），Web640通过，最终wheel/sdist与140个应用Python源码相同。先前完整目录快照及后续修正分开记录，不声称一个最新源码全量运行。损坏历史retry payload不会挡住无关队列，也不能覆盖更新后的订阅日程。

本次是阶段A前置条件，不是B站动态全功能。显式投稿/动态/两者范围、独立feed状态、有来源证据的附件及刷新、真实采集→归档→本地媒体库播放仍待完成。Emby/Jellyfin兼容目录继续不依赖连接服务器；其他五平台资料、三平台粘贴Cookie校验仍需实施，原七平台目标保持活动，未恢复supervisor。

## 上一检查点：微博作者昵称/头像查询（0060）

[执行0060](executions/0060-weibo-creator-profile/progress.zh.md)将自动作者查询扩展到微博保存会话及粘贴Cookie账户。稳定数字UID输入完成后执行一次认证config检查和一次精确作者请求，不遍历帖子。平台昵称、可选受限同源头像及本地备注保留账户/平台/身份和发布栅栏，不重命名历史作者/导出路径；查询无需全历史采集确认或连接媒体服务器。

最终完整Python目录**4729通过、23项环境跳过**，Web635通过，类型/格式/构建通过。wheel和sdist全部140个应用Python文件与冻结源码逐字节一致。精确执行、早期失败修正、打包及发布状态见[验证](executions/0060-weibo-creator-profile/verification.zh.md)，不作为真人资格。微博CDN路径及profile_image_url回退属于合成设计合同，不是锁定上游/真人已验证头像形状；未知形状安全保留文字/旧头像。

B站和微博资料已离线实现，其他五平台资料、抖音/快手/贴吧粘贴Cookie校验、B站动态及真人采集/归档/本地媒体库播放仍须完成。未操作生产、部署或恢复supervisor，原定七平台目标保持活动。

## 上一检查点：B站有界续抓单元（0059）

[执行0059](executions/0059-bili-bounded-capture/progress.zh.md)已接通真实bridge/scheduler/receipt/规范化/原子入库链路中的普通投稿有界采集。每轮最多校验min(max_items,30)条详情、最多两次作者列表尝试；浏览器/认证与最多两次WBI签名密钥读取另计。头部/历史通道保留待抓身份和页见证，历史不套用旧水位过滤。新B站请求无需无限历史确认，旧artifact仍门控。API/Web区分部分推进、保守重启、源末尾观察和全历史完整，不泄露cursor/ID。

离线验证覆盖签名查询/HTTP预算、超过30条的有界状态续抓、封存作者/投稿身份、来源/checkpoint/Run原子发布、取消/租约/CAS、真实封存恢复及更新检查点后的耐久成功。最终完整目录Python4386通过（23项环境跳过）、Web572通过，wheel的140个Python源码与工作区一致。精确打包/发布结果见[验证](executions/0059-bili-bounded-capture/verification.zh.md)。CLI提交确认不明时读取精确Run真值；另一次重复导入已消费artifact安全拒绝，不声称CLI重复调用幂等成功。

不代表B站全内容支持或真人金丝雀PASS。动态附件、剩余平台校验器/资料及真实采集/下载/归档/本地媒体库播放验收仍须完成。Emby/Jellyfin兼容目录输出仍独立于可选服务器连接。未部署、重试真人采集、修改订阅或恢复supervisor。

## 上一检查点：粘贴Cookie校验与复用（0058）

[执行0058](executions/0058-cookie-login/progress.zh.md)实现B站/小红书/微博/知乎远程本人认证检查、不可变managed私密保存、Account/Operation原子发布和账户粘贴弹窗。B站Cookie账户还支持单作者昵称/头像；后续Cookie上下文不再静默误用旧保存会话。完整离线目录检查4256通过（23跳过）、Web553通过，最终wheel源码与工作区一致。精确时间/范围、失败修正、打包/发布状态和真人边界见[验证](executions/0058-cookie-login/verification.zh.md)。

抖音/快手/贴吧粘贴校验、六平台资料、有界作者历史覆盖和真实采集/归档/Emby/Jellyfin验收仍须完成。四平台实现不等于七平台完成；历史B站零内容金丝雀仍失败/待定位，本增量未部署生产或恢复supervisor。

## 上一检查点：B站单作者资料查询（2026-09-05）

[执行0057](executions/0057-creator-profile-lookup/progress.zh.md)已实现 Bili saved-session 的独立单资料 runner、账户隔离昵称/头像、订阅本地备注、成功资料凭单和实际订阅界面。资料成功与 Operation 成功同事务；认证/代际/租约/取消均复核。头像为受限同源 PNG，不放宽 CSP。完整离线检查点3972项通过（22项跳过），最终加固源码联合回归575项通过，Web492项通过；这些是覆盖重叠的检查点，不相加计算。具体范围、合成浏览器限制和发布状态见[验证记录](executions/0057-creator-profile-lookup/verification.zh.md)。

0057发布时其他六平台及Cookie模式资料仍未实现；上面的0058新增B站Cookie资料和四平台粘贴校验。正确有界历史覆盖及实际采集/归档/Emby/Jellyfin验收仍开放。未部署生产、未真人查询、未恢复supervisor。0056和整体七平台目标保持开放。

## 上一检查点：订阅可用性与本地交付

[执行 0056](executions/0056-subscription-usability/progress.zh.md)已实现本地目录/可选服务器说明、可恢复订阅删除与暂停恢复、业务优先 UI 和精确 Job 安全报告。迁移保留文件和历史，忙碌任务拒绝删除。API/CLI 与后端专项回归、440 项 Web 门及有界合成浏览器检查通过；[验证记录](executions/0056-subscription-usability/verification.zh.md)单独说明全量/发布状态与真实环境未跑门。

自动获取创作者昵称/头像在 **0056发布时尚未实现**；[0057](executions/0057-creator-profile-lookup/progress.zh.md)已实现 Bili saved-session 首片，其他平台/模式仍须完成。仅本地输入预览不等于远程查询。粘贴 Cookie 登录、正确的 B 站有界历史覆盖及七平台采集/归档/Emby/Jellyfin 验收目标不变。本轮没有生产部署或重试，supervisor 仍由操作者停止。0056 未完成。

## 上一检查点：可操作的调度诊断

首次真实 B 站采集仍为 FAILED：终止的 schema_invalid Job、关联 running 且无错误的 Run、零内容。[本轮调度诊断](executions/0055-operator-auth-playback-evidence/scheduler-diagnostics/progress.zh.md)区分心跳失败、类型化 SQLite 写锁争用及收尾失败，不改变终止/熔断策略或改写历史 Run。API/CLI 与 Jobs 使用固定诊断投影，具体检查和边界见[验证](executions/0055-operator-auth-playback-evidence/scheduler-diagnostics/verification.zh.md)。实施和本地回归已通过（Python 联合 368、269 项，1 项 Windows 跳过；Web 343 项），不代表生产根因已修复或真人 PASS。supervisor 保持用户停止、测试订阅保持暂停；本增量不授权新采集。

后续产品工作仍是有界 B 站作者采集、粘贴 Cookie 远程校验/私密保存/复用，然后完成其他平台/归档/Emby/Jellyfin 验收；七平台目标不变。

## 上一检查点：B 站成功观察与后续修复

用户报告 B 站扫码成功；控制台直接核查确认精确匹配的成功 Operation/会话及 authenticated、saved_session 账户，但尚不能当新进程复用或采集证明。页面把已认证账户不能启动登录错误显示为红色失败；独立合成复现还发现扫码 Cookie 更新 hook 无需第二次远程 pong 就会报告成功。仅 UI/BILI 的有界修复已在[跟进计划](executions/0055-operator-auth-playback-evidence/bili-success-followup/plan.zh.md)冻结，[进展](executions/0055-operator-auth-playback-evidence/bili-success-followup/progress.zh.md)及[验证](executions/0055-operator-auth-playback-evidence/bili-success-followup/verification.zh.md)分别记录观察、实施和真人结果。不能据此断言用户此次是假成功。

用户指定验证作者，接受已说明的全历史边界与一次同步，随后确认已停止 supervisor，以防自动下载/导出。该尝试约 236 秒后 FAILED，零内容：Job 为 schema_invalid，关联 Run 仍 running 且无错误。测试订阅已暂停，未启动重试/下载/导出。账户预检、B 站扫码后确认及 Worker 结果展示已实现并本地验证（最终 Web 269 项）；实际采集根因仍未解决，不能推定是 Cookie 失效。粘贴 Cookie 登录仍是已接受的独立待实施增量；七平台目标不变，下述运行失败属于历史背景。

## 上一检查点：登录运行遗漏与诊断

已发布的浏览器环境修复通过 Windows 空白启动；操作者现又提供 Linux 有头持久 Chromium `151.0.7922.34` 冒烟及配置验证成功输出。但浏览器只读核查仍看到 17:47/17:48 的 B 站/抖音新登录失败（累计八条失败 Operation），最新抖音运行九秒后 runner/会话/认证均失败。操作者随后确认 `NODE_MISSING`。源码审查发现上游导入时 PyExecJS 依赖可用 JavaScript 运行时，二维码转发又静默丢弃了上游 base64 字符串。最终镜像 Node/真实 JS 预检与二维码规范化见[运行后续修复](executions/0055-operator-auth-playback-evidence/login-runtime-followup/progress.zh.md)；精确会话安全诊断与二维码终态 UI 见[登录诊断](executions/0055-operator-auth-playback-evidence/login-diagnostics/progress.zh.md)。这些修复不追认历史具体异常，也不构成平台 PASS。

用户追加的粘贴 Cookie 校验/保存需求已接受，本检查点尚未实现；下一步设计须要求真实远程认证证明、保护存储凭据，并在候选失败时保留原有效凭据。精确部署 SHA/镜像身份、修复镜像的二维码显示/扫码、会话复用、采集及 Emby/Jellyfin 仍开放，七平台总体目标不变。下文旧结果除链接记录明确更新外均属历史证据。

已推送的执行 0055 后端鉴权实现为提交 `f19bfaa`（冻结规划基线为 `4564b2a`）。它会在绑定端口前解析必需的类型化操作者凭据，支持可选且不同的 Bearer 凭据，强制精确 Host/Origin 策略，轮换进程内 HttpOnly `SameSite=Strict` session Cookie，对 Cookie 鉴权的不安全方法强制 CSRF，以精确匿名白名单配合默认拒绝的 ASGI 保护，只接受严格有界的登录 JSON，并把凭据/origin 契约接入 Docker Compose。其 190 项 auth/API 专项与完整离线回归（`2811 passed, 14 skipped, 1 warning in 561.43s`）通过，69 项 Web 测试及本机可用的静态/构建/docs/打包门也通过。3 项跳过为 Windows/POSIX 差异；本工作站无法运行 11 项真实 PostgreSQL 竞态与 Docker 验证，因此不作通过声明。

确认后端已发布为 `13de3b7`。已发布 `2e1949f` 的[投影检查点](executions/0055-operator-auth-playback-evidence/evidence-projection/progress.zh.md)增加有界作者证据读取与资格 schema v3。先在 publication/profile 权威稳定时完成一次新 lookup，再打开短读取事务；当前证据独立查询，历史默认 20 行、最多 50 行，总物化账本行不超过 `limit + 2`。历史页截断不否定独立当前行；远端 lookup 截断则不能 PASS。远端不确定使历史未知，完整不存在使其过期；只有精确持久确认可授予作者范围 PASS。无作者则 scope 为 `not_requested`，不查询证据或远端。Web login/session/CSRF 现已实现且本地合成浏览器门禁已通过；确认 UI 仍待实现。仓库真人资格继续为 `NOT_RUN`，provider completion 与自动扫描仍为 `NOT_IMPLEMENTED`。历史证据见[投影验证](executions/0055-operator-auth-playback-evidence/evidence-projection/verification.zh.md)，执行 0047 继续作为操作者门。

当前 `714c849` 冻结计划下的安全控制台与启动预检已实现，本地离线与合成浏览器门禁已通过；准确结果见[当前检查点](executions/0055-operator-auth-playback-evidence/secure-console/verification.zh.md)。本地合成浏览器门通过后优先验证当前 Linux 镜像并推进 Bilibili／小红书获授权金丝雀；P1 确认 UI 不阻塞既有 CLI 真人流程。

## 里程碑状态

| 里程碑 | 状态 |
| --- | --- |
| 离线功能开发 | 0075 已在 `aec3eac` 实现：全部 MediaCrawler 平台共用暂停态通用策略编辑器，且 B 站 scope 严格隔离。它建立在 0074 已取得交付资格的 B 站回填/增量状态之上，不改写断点、历史或媒体。Python/Web 完整套件及静态/制品门通过；共享控制台输出仍有意不作为摄取权威 |
| REST API + Web 控制台 | 0075 新增严格 `PUT /api/v1/subscriptions/{id}/policy`、对应 CLI 命令及带修订/session/弹窗栅栏的 Web 编辑器。既有认证 `/crawler/`、Cookie session/CSRF 和精确 Host/Origin WebSocket 保护保持不变；合成浏览器通过，真人平台行为未取得资格，Legacy 仍是受保护迁移提示 |
| 操作者鉴权 + 播放证据 | 后端鉴权、不可变身份／账本、仅浏览器确认、有界 current/stale/unknown 投影及资格 v3 已实现。无精确当前证据时 playback 为 IMPLEMENTED/NOT_RUN；PASS 只适用于选定作者。Web 会话集成已实现且本地合成浏览器门禁已通过；确认 UI 仍待实现，真人播放为 NOT_RUN |
| Docker 打包 | 0072 增加锁定上游 React 的隔离构建／复制阶段，真实锁定 React 源码已在临时副本成功构建。加固后生产依赖审计以 0 个漏洞通过；完整构建依赖图仍有 8 个仅开发／构建期发现。当前精确完整 Docker 构建／运行仍为 `NOT_RUN`。0041、0048–0050 历史候选镜像不能赋予当前工作树资格 |
| 运维文档 / 安全审查 / 发布清单 | 已交付（0045、0046） |
| 真人验收（最终门） | 仍开放——执行 0047 继续作为操作者门；精确 0075 镜像、原生 QR/Cookie 登录、profile 认领及七平台采集/下载/CDN/历史/增量均为 `NOT_RUN` |

## 验证矩阵

| 维度 | 状态 | 证据 / 阻塞 |
| --- | --- | --- |
| 实现（离线形状） | 七平台 15+ 冻结形状 | 执行 0013–0039 记录 |
| 离线完整套件 | 当前 0075 Python 完整套件以 `7067 passed, 43 skipped, 108 warnings in 1638.69s` 通过；Web 完整套件以 `27 files / 818 tests` 通过。跳过项均为明确记录的 OS/PostgreSQL/`uv` 资格分支，warning 为既有依赖弃用提示 | [0075 验证](executions/0075-paused-subscription-policy-editor/verification.zh.md) |
| API/控制台测试 | 0075 策略/API/CLI/鉴权联合为 `40 passed, 2 skipped`；两项真实 PostgreSQL 策略检查仍为 `NOT_RUN`。合成 Chrome 证明 B 站与 XHS 保存后仍暂停、平台 scope 保持隔离，浏览器/页面/请求错误数均为 0 | [0075 验证](executions/0075-paused-subscription-policy-editor/verification.zh.md) |
| 静态与制品门 | 0075 对 406 个文件的 Ruff lint/format、Web Prettier、156 个源码文件 strict mypy、compileall、62 包锁文件、两个上游及 wheel/sdist 构建通过；收尾重跑文档链接与 `git diff --check`。0072 加固后的生产依赖审计继续为 0，全构建依赖图仍有 8 个仅开发/构建期发现 | [0075 验证](executions/0075-paused-subscription-policy-editor/verification.zh.md) |
| 锁定上游 WebUI 依赖审计 | 生产 `PASS`／全构建依赖图 `FAIL`（仅开发依赖残余）——安全补丁后的构建副本生产漏洞为 0，全依赖图为 8 条：6 high、2 low、0 moderate、0 critical；对应 package 不会复制进最终运行镜像。未加固上游原始基线的 11 条（8 high、1 moderate、2 low）仅作为历史发现保留；版本化 checkout／lockfile 保持不变 | [0072 验证](executions/0072-mediacrawler-webui-integration/verification.zh.md) |
| Docker 镜像构建 | 独立的补丁后上游 React 构建继续通过，但本工作站没有 Docker，精确 0075 完整镜像构建/运行仍为 `NOT_RUN`；操作者历史线上门观察不能确认本 revision 或赋予镜像资格 | [0075 验证](executions/0075-paused-subscription-policy-editor/verification.zh.md)；执行 0050/0047 |
| 容器就绪 / 重启持久性 / 备份恢复演练 | 历史线上 API 曾通过关闭的许可证门返回响应，但精确 0075 身份、就绪与持久性未经验证；重启和备份恢复继续为 `NOT_RUN`。旧镜像深度预检仅为历史 `PASS` | [0075 验证](executions/0075-paused-subscription-policy-editor/verification.zh.md)；执行 0047；docs/operations.zh.md |
| 真人登录（任一平台） | 精确 0075 revision 的真人原生 QR/Cookie 登录与 Account profile 认领仍为 `NOT_RUN`；离线 saved-session 探针不等于登录资格。此前 B 站成功观察与其他失败保留为历史，新证明/复用仍开放 | [0075 验证](executions/0075-paused-subscription-policy-editor/verification.zh.md)；[历史 B 站跟进](executions/0055-operator-auth-playback-evidence/bili-success-followup/verification.zh.md) |
| 真人抓取 / 下载 / 增量性 | 七平台真人作者采集/下载/CDN/历史完整性及后续增量仍为 `NOT_RUN`。0074 只对 B 站确定性路径取得资格；XHS 及其他平台仍需各自源码驱动的耐久契约。历史首次 B 站金丝雀仍为失败 | [0074 验证](executions/0074-bili-backfill-incremental-delivery/verification.zh.md)；[0075 验证](executions/0075-paused-subscription-policy-editor/verification.zh.md) |
| 原生 WebUI 会话 → Account → Subscription scheduler/摄取/NFO | `IMPLEMENTED / OFFLINE PASS`：0073 提供 profile 认领，0074 增加 B 站交付资格回填/增量发布，0075 增加安全暂停态策略编辑。共享控制台输出有意不导入；真人端到端平台字节与最终目录检查仍为 `NOT_RUN` | [0075 进展](executions/0075-paused-subscription-policy-editor/progress.zh.md) |
| 交互式 `/crawler/` 输出自动导入 | `NOT_IMPLEMENTED / 有意分离`——`/data/mediacrawler/webui-output` 属于临时控制台运行，不是可信 Job receipt。定时摄取改从绑定 Account 的 Subscription 及其隔离 profile 启动 | [0073 目标](executions/0073-mediacrawler-session-adoption/goal.zh.md) |
| 真实 Emby/Jellyfin 连接、Library 发现与定向刷新接受 | `NOT_RUN`——0054-A 已实现，但未使用获授权真实服务器 | 执行 0054 与 0047 |
| Provider/path 项目查找与刷新后项目观察 | `IMPLEMENTED / NOT_RUN`——本地/mock 门禁通过，但未使用获授权真实 Emby/Jellyfin 服务器 | 执行 0054-B 验证 |
| Provider task completion | `NOT_IMPLEMENTED`——Emby/Jellyfin 共同刷新 API 不提供持久任务身份；阶段 B 不声明该能力 | 执行 0054-B 真实性边界 |
| 操作者访问控制 | 后端鉴权已发布；当前共享 `serve --check-config` 验证、含 `-- serve` 的迁移前入口检查及 Web 会话／CSRF 已实现且本地合成浏览器门禁已通过。预检不做 DNS／绑定，也不代表实际 Linux UID 或端口可用 | [当前验证](executions/0055-operator-auth-playback-evidence/secure-console/verification.zh.md) |
| 播放身份／持久化／确认后端 | 已在 `13de3b7` 实现并离线验证；读取／资格检查点现已消费账本。本工作站真实 PostgreSQL 竞态继续为 NOT_RUN | 执行 0055 |
| 证据投影与资格／自动扫描 | 作者证据与 schema v3 已 IMPLEMENTED；未选作者或无精确当前证据为 NOT_RUN，远端不完整／不确定权威不能授予 PASS。导出后自动扫描继续为 NOT_IMPLEMENTED | [投影计划](executions/0055-operator-auth-playback-evidence/evidence-projection/plan.zh.md) |
| 外部安全审计 | `NOT_RUN`——可选 | docs/security-review.md 残余风险 |

## 发布阻塞项（v0.1.0-rc1）

0075 暂停态策略编辑器已在 `aec3eac` 实现，建立在 0074 已取得交付资格的 B 站路径之上。Python/Web 专项与完整套件、合成浏览器渲染交互、静态/制品门及继承的加固后 0 漏洞生产依赖审计通过。精确镜像、修正配置后的 `/crawler/`、profile 认领及真人流水线均未取得资格。WebUI 全构建依赖图仍有 8 个仅开发/构建期发现。

1. P0：当前精确镜像的 Linux 基线未完成（运行用户 secret 可读性、迁移边界、宿主机端口、`/crawler/` 启动、重启持久性、备份恢复与进程基线）；旧镜像通过不能替代。
2. 发布前跟踪、缓解或显式接受锁定上游 WebUI 全构建依赖图的 8 个仅开发／构建期发现。生产审计为零；未加固上游原始基线的 11 条仅作为历史发现。
3. 精确 0075 的真人原生登录/profile 认领及七平台采集/下载/CDN/历史/增量行均为 `NOT_RUN`；任何 Supported 声明前须运行受控金丝雀，通用策略编辑不等于平台交付资格。

0.1 最低发布条件：至少两个金丝雀平台达到 **Supported**（登录、同步、下载、真实增量、Emby 重扫 + 抽样播放），其余平台如实分级（Experimental / Metadata-only / Blocked External / Unsupported），且项目自我表述为“七平台适配框架；实际资格状态见状态矩阵”，而非“支持七个平台”。
