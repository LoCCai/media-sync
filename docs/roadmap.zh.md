[English](roadmap.md) | **中文**

# 交付路线图

## 产品结果

构建一个可自托管的服务：覆盖锁定版本 MediaCrawler 支持的全部平台登录；允许订阅作者；增量收集作者的图文、图片和视频；最终输出 Emby/Jellyfin 兼容媒体库。

## 阶段

### 阶段 0 — 基线与许可证边界

- 锁定两个上游仓库并记录其许可证。
- 盘点平台、登录、作者与媒体能力。
- 建立执行日志与双语 Git 约定。
- 验收：源码可按 SHA 复现，许可证边界明确，路线图可审查。

### 阶段 1 — 核心领域与持久化

- Python 包、配置与 CLI 骨架。
- 为账户、凭据引用、作者、订阅、内容、资产与同步运行建立 SQLite schema。
- 适配器协议及用于测试的确定性 Fake 适配器。
- 验收：迁移可初始化数据库，CRUD 与状态转换通过自动测试。

### 阶段 2 — MediaCrawler 外部适配

- 状态：离线命令构造、夹具归一化与密封导入已交付；由于未授权账户或真人交互挑战，授权真人 smoke test 继续为 `NOT_RUN`。

- 发现并验证锁定版本的外部 MediaCrawler checkout。
- 把登录方式与作者订阅转换为隔离爬虫任务。
- 在不导入或复制受限源码的前提下，把 JSON/JSONL 结果导入归一化领域。
- 验收：七个平台标识的 dry-run 命令构造与夹具导入均可运行；经授权的真人 smoke test 另行记录。

### 阶段 3 — 下载与 Emby 导出

- 状态：执行 0005 的平台无关离线基础已完成，执行 0013–0024 建立覆盖全部七个平台的十二个冻结媒体形状；执行 0025–0026 增加 DASH/progressive 有序备用可靠性，执行 0027 增加显式“精确单段 FLV→MP4”衍生处理，执行 0029 增加有界 2–64 普通多段 `durl` 的逐段下载与单次 concat 拼接，执行 0030 把该拼接扩展到多段 FLV，执行 0031 为微博增加首个可播放视频形状，执行 0032 为抖音增加有界图集形状，执行 0033 为知乎增加有界回答图集形状，执行 0034 为快手增加有界图集形状，执行 0035 增加微博 `playback_list` 画质选择，执行 0036 增加微博视频封面，执行 0037 增加有界小红书多视频元组，执行 0038 增加小红书实况照片，执行 0039 增加小红书多图实况 gallery，均不改变稳定身份。精确 canonical detail 刷新、封闭 request profile、严格跨候选续传/restart、源/成品探测、有界 ffmpeg stream-copy、SHA-256 归档及确定性 Emby 发布在各自冻结切片中均已通过。截至 0038 的历史门为专项 355 项、完整套件 2032 项通过并仅跳过一项 Windows 不适用用例；0039 之后的当前测试事实以 [`status.zh.md`](status.zh.md) 和各执行验证记录为准。转发、GIF/直播/付费媒体、其他混合媒体帖、更广的贴吧媒体、转码/编解码修复、超过 64 个分 P、字幕/弹幕、CDN 排序/竞速/跨运行缓存及混合/非鉴权穷尽刷新，以及其他已记录扩展形状继续待实现；真人登录/作者/detail/play/CDN/平台字节及 Emby/Jellyfin 服务器验证保持 `NOT_RUN`。

- 以续传、校验和、类型/大小限制及安全文件名下载资产。
- 把视频和图文内容映射为稳定的作者/内容目录。
- 生成 XML NFO、封面、背景图与 sidecar manifest。
- 验收：夹具内容可渲染为通过 XML 验证与 golden-tree 测试的媒体库。

### 阶段 4 — 调度、API 与运维

- 状态：执行 0009 的功能优先刷新 MVP 已在提交 `98cf387` 中实现，执行 0010 的持久入队与显式有界 pipeline worker 已在提交 `f2e5899` 完成，执行 0011 的显式 QR 登录/saved-session 交接已在提交 `8bb16f6` 完成，执行 0012 的父进程硬终止收容、受截止时间 fencing 保护的登录回收和本地前台监督器已在提交 `28655f8` 完成。0012 专项门禁通过 283 项并跳过 1 项；完整套件通过 1156 项，跳过的仍是同一 Windows 不适用项。该前台监督器不是已安装或自动重启的 daemon。跨主机 HA、七平台完整下载和真人平台/CDN/Emby 验收仍未声明；全部真人行保持 `NOT_RUN`。

- Job 调度、重试/退避及启动并发/节流：已在执行 0006 的 Fake/离线边界内交付。
- 账户、订阅、同步与导出的本地 REST API 已在执行 0040 离线范围交付；执行 0050 新增 SvelteKit Console v2 基础、内容/媒体库读模型与浏览器一次性确认，同时保留 `/api/v1` 和 `/legacy` 回退。
- 执行 0051 交付：离线/API/前端账户与订阅工作台现由 API、CLI 与 UI 共享一套七平台能力与草稿校验契约；启动前提供登录专用预检；二维码读取绑定精确 LoginSession；交付三步订阅向导；policy/checkpoint 仅展示白名单安全摘要。专项离线、API、前端与浏览器验证均通过，未使用真实凭据，也未据此授予真人资格。
- 执行 0052 交付：migration `0006` 为账户登录、资产下载、scheduler run、pipeline run 与 Emby export 新增 lease-fenced 持久 Operation/Event/subject 状态机及事务提交有序 cursor。API 提供有界列表/详情/事件、严格幂等提交、跨 coordinator 两阶段取消、非阻塞单飞协调，以及 ready/`initial_cursor` 加 `Last-Event-ID` SSE；Jobs 路由提供筛选快照、进度、安全时间线与有界轮询回退。16 KiB 仅聚合 JSON 支持响应会执行输出后二次扫描。冻结套件 2315 项通过、3 项 Windows 不适用而跳过，全部仓库门通过。requester/lease/revision/idempotency 内部态保持私有；通用文件日志、独立 Logs 页面、统一 supervisor 接入、retry 与订阅 pause/resume/delete 审计继续延期。
- 执行 0053 交付：既有内容/资产数组契约继续保持兼容排序，并新增有界服务端筛选与安全精确详情。只接受 UUID 的 GET/HEAD 以同描述符验证/流式读取服务经过验证的内容寻址归档字节；单 Range 只在完整表示验证后的 GET 生效，HEAD 忽略 Range，`If-Range` 只接受精确匹配当前强 ETag。恢复复用持久 asset-download Operation。Contents、Assets 与 Library 现支持安全下钻且不暴露 raw、locator 或宿主路径；canonical 链接只允许匹配平台的官方域名。冻结套件通过 2456 项、跳过 3 项，query/弹窗浏览器 smoke 通过。媒体服务器树/控制留在 0054，鉴权/保留留在 0055。
- 执行 0054 交付：阶段 A 增加对数据库/manifest 精确授权受管树的有界只读检查、单个不可变环境托管 Emby/Jellyfin 配置、DNS/CIDR 固定且无代理/无重定向的 connector，以及 revision `0007` 持久 probe/定向刷新 Operation。[阶段 B](executions/0054-media-library-server-integration/phase-b/plan.zh.md) 增加当前 publication selector 派生、完整有界 provider/path 项目查找、严格 legacy `{}` 只确认接受兼容，以及带 fencing 的 accepted/observed checkpoint 与保守取消/重启真实性的作者 absent-to-unique-match 观察。Library、Settings 与 Jobs 只暴露白名单证据；资格 schema v2 把 lookup/observation 标为已实现且真人 `NOT_RUN`。启用真实 PostgreSQL 的收尾套件 2763 项通过、3 项跳过，其中包括 11 项真实 PostgreSQL Operation 竞态用例；69 项 Web 测试及 format/check/build 通过。未使用真实媒体服务器。Provider task completion 继续为 `NOT_IMPLEMENTED`（`provider_api_unsupported`），播放证据与导出后自动扫描也仍未实现；经鉴权播放证据写入及可写/破坏性运维继续归 0055。
- 执行 0055 阶段 A 现已按基于 `d0a8cc2` 冻结的计划完成部分实现。提交 `f19bfaa` 已交付后端单操作者鉴权边界：绑定前关闭失败的类型化凭据、可选独立 Bearer、精确 Host/Origin、默认拒绝的匿名白名单、唯一轮换的进程内 HttpOnly `SameSite=Strict` session、Cookie 鉴权不安全方法的 CSRF、严格有界的登录 JSON，以及 Compose 凭据/origin 契约；其 190 项 auth/API 专项通过。当前工作变更新增下一层持久化基础：只有完整且唯一 `matched` 的 lookup 才派生 observation fingerprint，Web 已同步该 lookup response 类型，revision `0008_playback_evidence` 建立 append-only 账本，专用仓储提供精确 replay/conflict 及 SQLite/PostgreSQL 竞态原语。当前完整工作树通过 `2868 passed, 22 skipped, 1 warning in 558.19s`；跳过项分别为 3 项 Windows/POSIX、11 项既有 Operation PostgreSQL，以及因没有测试 URL 而跳过的 8 项新增 PlaybackEvidence PostgreSQL。Web 69 项及 format/check/build、727 文件 Ruff/format、105 个源文件 strict mypy 与 compileall 均通过。真实 PostgreSQL 与 Docker 均未运行；隔离 Author/Job/PlaybackEvidence harness 不是完整 PostgreSQL 部署证据。0055 总退出门仍开启，因为 Console v2 与 `/legacy` 尚未集成 login/session/CSRF，经鉴权确认 service/API/UI 与资格 schema v3 也仍未实现。因此 `playback_evidence` 继续为 `NOT_IMPLEMENTED`，真人播放为 `NOT_RUN`。Provider task completion 与导出后自动扫描不属于本阶段，可写/破坏性运维、保留及多 profile 也明确排除。详见[目标](executions/0055-operator-auth-playback-evidence/goal.zh.md)、[计划](executions/0055-operator-auth-playback-evidence/plan.zh.md)、[进展](executions/0055-operator-auth-playback-evidence/progress.zh.md)与[验证](executions/0055-operator-auth-playback-evidence/verification.zh.md)。
- 健康/深度就绪端点与网络边界事实继续展示，Compose 模板现要求挂载操作者凭据并配置精确浏览器 origin。Docker 打包包含 0050 最终镜像不含 Node 的多阶段静态构建，宿主模板仍只发布回环。后端鉴权边界与播放证据持久化基础已经实现，但 Web 鉴权集成与经鉴权播放确认仍待完成；compose supervisor 之外的 daemon 化继续延期。执行 0047 仍是 P0 Linux/操作者门，其中尚未执行的持久性/恢复/进程与真人平台/CDN/Emby-Jellyfin 行继续保持 `NOT_RUN`。
- 执行 0007 离线验收：策略/产物/attempt 身份、移出事件循环的父进程 heartbeat、父死亡/control handshake、精确 fencing、保守状态映射、四状态清理及七平台协议链均已实现并执行。重复 runner 取消及确定性批次间取消 barrier 已证明先 join 再 unwind，且第二批无变更。AC6 仍为 `PARTIAL`，仅因为 child 退出后/seal 前及 seal 后/导入前的确定性 barrier 尚不完整。AC13 为 `PARTIAL`：清理/脱敏/哨兵覆盖已较充分，但“已知密钥/非零/timeout/全部超限/回执/取消/lease 丢失 × 保留文件系统/SQLite/运维落点”的完整矩阵尚不完整。
- 执行 0008 已完成上述两项 partial 的离线继任收口：child-exit/pre-seal 及单次/重复 post-seal/pre-ingest barrier 通过；精确“11 种失败 × 3 类落点”矩阵以 fail-closed 文件系统/SQLite 扫描及固定运维权限证明 33 个 cell。完整套件通过 837 项测试、1 项 Windows 不适用的 skip，分支感知覆盖率 79%。refresh 与 DAG 工作仍不属于本结论。
- 执行 0009 交付：精确当前来源、有界 detail 刷新及默认关闭的显式资产下载接线已实现。在该历史边界，离线形状为小红书 image/video、抖音 image/video/audio/cover、快手 video/cover 与 Bilibili cover；当前 Bilibili 能力已由下方执行 0013 扩展。小红书多 note 权限查找和更多平台 Asset 留待后续。
- 执行 0010 交付：sync 成功会原子 enqueue 一个 `pipeline.subscription` 协调器后停止；另一个由操作员调用的 `pipeline run` 命令有界扫描队列、续租、串行下载精确 Subscription 资产，再调用既有 Emby publisher。复用既有 Job schema、generation 恢复及发布恢复，不新增 migration。
- 执行 0012 交付：登录父进程硬终止收容、受截止时间 fencing 保护且公平的 LoginSession 回收，以及本地前台监督器现已覆盖 scheduler、订阅与 pipeline 阶段。停止时会取消并 join MediaCrawler 同步；对于一项已经 active 的线程型 pipeline 尝试，即使遭遇重复 task cancellation，也会保持 heartbeat 并精确等待收尾，不虚假声称可以强停。后续产品切片为更多平台可播放媒体、本地 REST/运维，以及经授权的逐平台/CDN/真实媒体服务器验收；每项都必须继续明确区分“不支持”与 `NOT_RUN`。
- 执行 0013 交付（`dd6cfec`）：一个 Bilibili 普通 numeric-aid 投稿现在会产生稳定的 `NULL` source `<aid>:video:0` Asset。绑定精确 Subscription 的刷新会校验当前首 CID，只接受一个 progressive `durl`，携带无 Cookie/Authorization 的封闭 UA/Referer/Origin request profile，并把合成字节接入受控探测、归档收尾及幂等 Emby `.mp4` 发布。专项门禁通过 223 项；完整套件通过 1199 项，另有一项在 Windows 不适用而跳过。由于 forward 元数据没有 CID，同 aid 首 CID 替换无法自动使已验证字节失效。DASH/mux、FLV remux、多段/多 P、字幕、弹幕、备用地址故障切换及付费/番剧/直播媒体继续延期；真人账户/CDN/媒体服务器行保持 `NOT_RUN`。
- 执行 0014 交付（`c4ab537`）：一条包含精确一个合法播放 URL 与可选封面的快手普通记录，现在已有锁定纯 ID detail/process 证据、绑定精确 Account/Subscription 的惰性刷新，以及通过默认 request profile 的确定性 MP4/PNG 下载证据。持久 raw 会移除 userinfo/query/fragment 与嵌套 schema 漂移；视频探测、SHA-256 归档及幂等 Emby `.mp4`/海报/NFO/source 发布全部通过。专项门禁通过 228 项；完整套件通过 1206 项，另有一项在 Windows 不适用而跳过。同 ID/同 path 字节替换、有界作者分页、图集/多 URL、专用 CDN header、清理失败 quarantine 及全部真人行继续延期或保持 `NOT_RUN`。
- 执行 0015 交付（`95d314d`）：一条 note/music 为空、精确一个视频 URL 与可选封面的普通 numeric-ID 抖音记录，现在已有锁定纯 ID detail/process 契约、绑定精确 Account/Subscription 的惰性刷新，以及通过默认媒体 profile 的确定性 MP4/PNG 下载证据。持久 raw 会从四个媒体字段移除 userinfo/query/fragment，把 note 逗号字符串转换为有序项，并按子项拒绝嵌套/逗号 schema 漂移。受控视频探测、SHA-256 归档及幂等 Emby `.mp4`/海报/NFO/source 发布全部通过；仅 query 变化的重放不会新增 detail、HTTP、DNS 或 probe 调用。专项门禁通过 231 项；完整套件通过 1209 项，另有一项在 Windows 不适用而跳过。图集、关联音乐语义、多媒体 URL、同 ID/同 path 字节替换、有界作者分页、专用 CDN header 及全部真人行继续延期或保持 `NOT_RUN`。

- 执行 0016 交付（`a77ca74`）：一个冻结的普通原创微博静态图片形状现已在不修改 `.upstream` 的前提下，于 creator 与 numeric-ID detail child 捕获有序且唯一的 `mblog.pics`，把一张/多张内嵌 `sinaimg.cn` 源 host、无 query 的合法 `.jpg/.jpeg/.png/.webp` `i1.wp.com` locator 归一化为 IMAGE/GALLERY Asset，并组合精确 Account/Subscription 刷新、mock 传输、SHA-256 归档及幂等 Emby poster/backdrop/gallery/NFO/source 输出。专项门禁通过 388 项，耗时 125.73 秒；完整套件通过 1251 项、跳过一项 Windows 不适用测试，耗时 359.38 秒。微博视频、转发、媒体 `page_info`、GIF/动图、有界作者分页、直连新浪 CDN 行为，以及全部真人登录/作者/detail/CDN/平台字节/Emby-Jellyfin 服务器行继续排除、延期或保持 `NOT_RUN`；七平台中的其他未验收媒体形状仍待推进。

- 执行 0017 交付（计划 `9d19e7e`，实现 `2f8dbaa`）：在该历史边界，小红书惰性刷新保留显式、瞬态的精确 note 引用作为覆盖项；否则从精确 `AssetRefreshSource → Subscription` 私下解析 `policy.mediacrawler.creator_input.secret_ref`。Refresh context、父请求及 child loader 三层会校验作者 URL 与作者身份，creator/detail 权限严格互斥，creator 运行受 `Subscription.max_items` 限制，返回多条 JSONL 时按精确 content ID 与 Asset kind/position/source hint 筛选。普通 `type="normal"` 单图/多图静态图片通过默认 profile mock HTTP、不可变 SHA-256 归档及幂等 Emby poster/backdrop/gallery/NFO/source 发布，且不保留签名权限或 query 值。完整套件通过 1298 项，另有一项 Windows 不适用而跳过。在该边界，自动小红书视频、实况照片、动图、混合媒体及权限过期恢复继续延期；贴吧/知乎可下载 Asset 发现仍未实现，全部真人登录/作者/detail/CDN/平台字节/Emby-Jellyfin 服务器行保持 `NOT_RUN`。

- 执行 0018 交付（计划 `c9d3586`，实现 `356e254`）：自动小红书 creator fallback 现在只接受一条普通 raw `type="video"` 行，要求标量 `video_url` 精确包含一个候选、标量 `image_list` 包含零或一个候选，并一一映射为 position 0 的唯一 VIDEO 与可选 IMAGE。初始 URL 限于合法 HTTP/HTTPS `xhscdn.com` host、默认端口及非根路径；畸形、外域、userinfo、fragment、多候选及容器漂移均关闭失败，重定向继续使用既有公网策略。锁定源码合约、真实 fake checkout、内嵌真实 H.264 的生产 ffprobe 检查，以及确定性 SQLite → mock DNS/HTTP → SHA-256 归档 → Emby `.mp4`/poster/NFO/source 组合全部通过；仅 query 变化的重放不新增工作。专项门禁通过 222 项，完整套件通过 1353 项，另有一项 Windows 不适用而跳过。多视频、多图片、更广混合/实况/动图、权限过期恢复及贴吧/知乎媒体 shim 仍为后续工作；全部真人登录/作者/detail/CDN/平台字节/Emby-Jellyfin 服务器行保持 `NOT_RUN`。

- 执行 0019 交付（计划 `dc1714c`，实现 `2edb9d7`）：校验 checkout shim 在锁定 extractor/store 丢失边界，从知乎作者普通回答捕获精确一个静态图片候选。它使用冻结的 `data-original` → `data-actualsrc` → `src` 优先级；竞争或重复选中属性、`srcset`/`data-src`/lazy 候选、多图片、可播放/容器漂移及无效 canonical URL 均关闭失败。捕获绑定到精确返回模型，`ContextVar` 只在嵌套存储阶段使用，因此 gather-child 提取能进入父任务存储，且不会泄漏到并发任务或序列化私有字段。Scheduled creator 回答循环受 Subscription `max_items` 约束，因此知乎从全历史确认集合移除。ARTICLE 加唯一 `<content_id>:image:0` IMAGE 贯穿精确持久 canonical 回答刷新、无凭据 DEFAULT-profile mock HTTP、有界 JPEG/PNG/WebP 结构资格校验、SHA-256 归档及 Emby poster/backdrop/gallery/body/NFO/source 输出，并支持 query 零工作重放；GIF/APNG/animated WebP/AVIF 在结构门失败。最终专项门通过 505 项、耗时 48.82 秒；完整套件通过 1543 项、跳过一项 Windows 不适用用例，耗时 318.39 秒；全部质量/审计门通过，独立 461 项复核未发现 P0/P1/P2。当前没有真实脱敏夹具，全部真人行保持 `NOT_RUN`；多图、文章、zvideo 与贴吧媒体继续待实现。

- 执行 0020 交付（计划 `df7a38a`，实现 `8a0e935`）：校验 checkout shim 在锁定 extractor 丢弃 locator 前，从贴吧普通主题首楼捕获精确一个当前整数 type-3 静态图片。精确对象绑定跨越 gather-child → parent-store，并只在嵌套存储使用 `ContextVar`。Scheduled creator wrapper 校验页面形状，把 `max_items=23` 精确变成 `20 + 3` 条成功详情/callback 行，无第三页或达到上限后的 sleep。ARTICLE 加唯一 `<note_id>:image:0` IMAGE 只持久化无 query hint；SQLite canonical 主题权限驱动 numeric-ID detail 与无凭据 DEFAULT-profile 签名刷新。合格 JPEG/PNG/WebP 通过结构门，GIF/APNG/animated WebP/AVIF 失败。确定性 SQLite → fake detail → mock DNS/HTTP → SHA-256 归档 → Emby poster/backdrop/gallery/body/NFO/source 组合及 query 零工作重放通过。专项回归通过 368 项，完整套件通过 1650 项且仅跳过一项 Windows 不适用用例；全部质量/构建/上游/审计门通过。真人登录/作者/detail/CDN 与 Emby/Jellyfin 服务器行保持 `NOT_RUN`；gallery、其他首楼内容类型及更广贴吧媒体继续待实现。

- 执行 0021 交付（计划 `5095ed6`，实现 `e0fb8d5`）：保持 v1 贴吧单图字段兼容，独立 v2 字段跨越同一锁定 gather-child → parent-store 边界捕获精确两个有序、互异 type-3 图片身份。ARTICLE 现产生 `<note_id>:image:0/1`；两个私有字段均递归移除，SQLite 只保留有序无 query hint。惰性刷新绑定完整持久 gallery，仅在当前详情按顺序复现两个身份时解析任一 position；缺图、重排、替换、重复或双重声明均关闭失败。两次 DEFAULT-profile 下载通过 JPEG/PNG 静态资格，发布两个 SHA-256 归档并组合 Emby poster/backdrop/两项 gallery/body/NFO/source；query 重放零新增工作。专项 413、完整 1668+1-skip 及全部质量/构建/文档/上游/审计门通过。在该历史边界，三张及以上图片仍待实现；混合/富内容/回复媒体、替换语义及全部真人行继续待实现或保持 `NOT_RUN`。

- 执行 0022 交付（计划 `fbcb7cf`，实现 `b6d03aa`）：v1 继续代表精确单图、v2 继续代表精确双图，独立 v3 声明跨越同一精确对象 gather-child → parent-store 边界捕获 3–64 张有序互异 type-3 图片。ARTICLE 产生 `<note_id>:image:0..N-1`；三个私有字段均递归移除，SQLite 只保留完整有序无 query hint 元组。共享 64 图上限由捕获、归一化、刷新上下文与惰性数据库加载共同强制；65 张图片、畸形/重复项与多版本声明均关闭失败。每个刷新 position 都要求当前数量/顺序/身份/position/remote-ID 完全一致，并拒绝缺失、新增、重排、替换与重复 gallery。三次 DEFAULT-profile JPEG/PNG/WebP 下载发布三个 SHA-256 归档，并组合 Emby poster/backdrop/三项 gallery/body/NFO/source；query 重放零新增工作。专项 `433 passed in 48.91s`、完整 `1688 passed, 1 skipped in 321.22s` 及全部质量/构建/文档/上游/审计门通过。超过 64 张的 gallery、混合/富内容/回复媒体、替换语义及全部真人行继续待实现或保持 `NOT_RUN`。

- 执行 0023 交付（计划 `bd45478`，实现 `24fd41c`）：源码校验、任务局部的 shim 在锁定 Bilibili JSONL store 丢弃 `View.pages` 前捕获 1–64 项规范有序 `page`/`cid` 身份；65、畸形、不连续与重复 CID 声明均关闭失败。精确单 P `<aid>:video:0` 保持兼容，合格 2–64 分 P 投稿产生有序、仅 locator 的 `<aid>:video:cid:<cid>` VIDEO Asset。详情协议 v4 只接收目标 `bili_video_cid`，调用该 CID 的 play API 并接受精确一个 progressive `durl`；惰性刷新绑定完整持久兄弟元组，并拒绝当前分 P 缺失、新增、重排、替换、重复或畸形。私有字段与签名 URL 在持久化前递归移除。三次定向 Bilibili-profile 下载发布不同 SHA-256 归档及确定性 Emby 主媒体/两个 part/NFO/source 输出；query-only 重放零新增 detail/DNS/HTTP/probe/archive/export 工作。专项 `436 passed in 53.96s`、完整 `1739 passed, 1 skipped in 321.25s` 及全部质量/构建/文档/上游/审计门通过。DASH/mux、多 `durl` 分段、FLV、字幕/弹幕、备用地址故障切换、超过 64 个分 P、更广 Bilibili 类型及全部真人行继续待实现或保持 `NOT_RUN`。

- 执行 0024 交付（计划 `a7d038e`，实现 `12314b9`）：严格 Bilibili 详情协议 v5 以 WBI 签名、`qn=127`、`fourk=1` 与 `fnval=4048` 请求精确 CID；选择器取最高受支持视频画质，同画质依次偏好 AVC → HEV → AV1，按锁定的普通/杜比/Hi-Res 音频顺序选择，并支持合法无声形状。签名主/备用/组件 URL 只存在于运行时。Generation-scoped store 提供严格续传、组件探测、组合字节上限、固定有界 `ffmpeg -c copy`、最终 `ffprobe` 与仅成品不可变发布。合并失败保留已验证组件；已准备且发布的成品无需 detail/DNS/HTTP/ffmpeg 即可恢复。本地真实 H.264+AAC 组合产生同时含音视频流的最终归档与 Emby MP4。专项 `456 passed in 66.47s`、完整 `1780 passed, 1 skipped in 333.43s`、生产 ffmpeg/ffprobe 集成及全部质量/构建/文档/上游/审计通过。备用 URL 已建模但故障切换继续待实现；全部真人行保持 `NOT_RUN`。

- 执行 0025 交付（计划 `8e9467d`，实现 `fe45abc`）：每个已选瞬态 DASH 视频及可选音频组件现在会在既有 Asset 锁、字节上限和共享截止时间下，按来源顺序尝试主地址及最多八个已校验互异备用地址。DNS、timeout、传输、中断、HTTP 及 partial Range 不兼容可推进；网络策略、重定向/header/encoding、chunk/size、文件系统、探测与合并失败仍立即关闭。跨候选追加要求 offset、总长度与 validator 完全连续；混合失败保留 partial，只有完整轮次拒绝后才允许有界丢弃/restart。全部 `401`/`403` 穷尽继续得到 `locator_refresh_auth_expired`，且不保留 URL/host/胜出序号。生产进程视频 `503` 加音频 `403` 组合会分别到达备用地址，并发布双流归档与 Emby MP4。专项 `466 passed in 66.96s`、完整 `1790 passed, 1 skipped in 331.33s`、真实 ffmpeg/ffprobe 备用路径集成及全部质量/构建/文档/上游/审计通过。progressive 备用故障切换、CDN 排序/缓存及全部真人行继续待实现或保持 `NOT_RUN`。

- 执行 0026 交付（计划 `0694934`，实现 `190488f`）：严格详情协议 v6 通过等价 `backup_url`/`backupUrl` 别名接受精确一个 progressive `durl` 主地址及最多八个已校验有序备用地址。有界单 P/多分 P 私有桥接保持历史仅主地址兼容，并在持久化前递归移除。普通 progressive 与 DASH locator 共用主地址优先候选轮次；可切换失败类别、严格跨候选 offset/长度/validator 连续、partial 保留与整轮 restart 均保持封闭。只有 adapter 一轮全部 `401`/`403` 才刷新详情一次；第二轮仍全鉴权失败返回 `locator_refresh_auth_expired`，direct 及混合/非鉴权穷尽不刷新。单 P 与三分 P 组合让每个主地址返回 `503`，到达备用地址、发布归档/Emby 输出并零新增工作重放，且不保留签名候选。专项 `490 passed in 73.31s`、完整 `1814 passed, 1 skipped in 342.33s`、progressive 备用组合、DASH 兼容及全部质量/构建/文档/上游/审计通过。多 `durl` 分段、FLV、CDN 排序/竞速/跨运行缓存、混合/非鉴权穷尽刷新及全部真人行继续待实现或保持 `NOT_RUN`。

- 执行 0027 交付（计划 `ec7095a`，实现 `7f99aa4`）：严格详情协议 v7 只允许合法、显式的顶层格式授予 FLV 权限，并通过防碰撞的单 P/多分 P 私有桥接重建一个 repr-safe 类型化 target。Generation-scoped 源 store 复用有序候选、严格 Range/validator 连续、整轮 restart 与一次全鉴权刷新。精确 FLV 源探测先于固定有界的单输入 `ffmpeg -c copy`；只有精确探测为 MP4 的成品可发布，失败会保留源并移除未准备成品。生成的本地 H.264+AAC FLV 在主地址 `503`/备用故障切换后贯穿生产 ffprobe/ffmpeg、双流 SHA-256 MP4 与 Emby 输出，随后零工作重放且不保留签名/私有信息或原始 FLV 发布。专项 `394 passed in 59.12s`、完整 `1848 passed, 1 skipped in 347.72s` 及全部质量/构建/文档/上游/审计门通过。多 `durl` 分段、FLV 拼接/转码及全部真人行继续待实现或保持 `NOT_RUN`。
- 执行 0029 交付（计划 `9a40968`，实现 `7eb188d`）：严格详情协议 v8 接受有界的 2–64 个有序普通（非 FLV）多段 `durl` 元组，每段一个主地址加至多八个备用地址；精确一段 payload 保持字节级兼容，顶层 FLV 且多段保持不支持。一个 repr-safe 的 `ResolvedSegmentsLocator` 通过防碰撞的 `{"cid", "segments"}` 私有桥接跨越单页与多分 P 页面元组，持久化前移除，且仅当 payload CID 精确匹配时重建。类型化下载分支在共享字节上限/截止时间下按序下载分段、复用既有候选故障切换，每段精确探测为 MP4，允许一次必须返回相同分段数的全鉴权刷新，并以只存在于受控 parts 目录内的相对文件名脚本执行一次固定 concat-demuxer `ffmpeg -c copy` 调用；仅精确 MP4 成品可发布，失败保留分段可续传，已备成品无网络恢复，清理丢弃全部分段 store。一条真实双段 H.264+AAC 组合贯穿 SQLite → 主地址失败 → 备用 → 生产 ffprobe/ffmpeg → SHA-256 MP4 → Emby，零工作重放且不保留签名 URL 或私有标记。专项 `447 passed in 70.97s`、完整 `1902 passed, 1 skipped in 409.85s` 及全部质量/构建/文档/上游/审计门通过；另修复两个仅测试侧的 `tasklist` 解码辅助以适配中文 Windows 工作站（干净树上可复现的既有失败）。多段 FLV 拼接、CDN 排序/竞速/跨运行缓存及全部真人行继续待实现或保持 `NOT_RUN`。
- 执行 0030 交付（计划 `e7395fb`，实现 `564f80f`）：严格详情协议 v9 只在封闭顶层格式分类加有界 2–64 `durl` 元组下授予多段 FLV 权限。一个 repr-safe 的 `ResolvedFlvSegmentsLocator` 精确包装一个 `ResolvedSegmentsLocator`，并通过既有私有桥接携带精确 `"format": "flv"` 标记；非精确标记、平面字段碰撞与无页面 payload 关闭失败，持久化前递归移除，且精确一段 FLV、多段普通与 DASH payload 保持字节级兼容。类型化下载分支以绑定 flavor 的续传指纹接受两种分段目标类型、逐段精确 FLV 结构探测、必须返回同类型同分段数的一次全鉴权刷新与一次固定 concat-demuxer `ffmpeg -c copy` 调用；仅精确 MP4 成品可发布，失败保留可续传分段，且不归档、导出或发布任何原始 FLV。一条真实双段 H.264+AAC FLV 组合贯穿 SQLite → 主地址失败 → 备用 → 生产 ffprobe/ffmpeg → SHA-256 MP4 → Emby，零工作重放。专项 `460 passed in 91.95s`、完整 `1916 passed, 1 skipped in 446.64s` 及全部质量/构建/文档/上游/审计门通过。转码、编解码修复、CDN 排序/竞速/跨运行缓存及全部真人行继续待实现或保持 `NOT_RUN`。
- 执行 0031 交付（计划 `1c79c6d`，实现 `666438d`）：锁定微博 store shim 在与 0016 图片捕获相同的精确对象边界上，为 `page_info.page_type` 精确为 `video`、非转发、numeric-ID 的普通 `mblog` 捕获精确一个标量 `media_info.stream_url`；转发与非视频 page 类型不捕获。私有 `{"url"}` payload 严格防碰撞、持久化前递归移除，并绑定封闭签名 URL 校验器（HTTPS `sinaimg.cn`/`*.sinaimg.cn`/`f.video.weibocdn.com`、非根 `.mp4` 路径、无 fragment/userinfo/端口）。`_normalize_wb` 物化 `ContentKind.VIDEO` 与一个 `{note_id}:video:0` VIDEO 资产并对漂移隔离；WB VIDEO 适配器刷新经一次 numeric-note detail 子进程在内存中重新捕获当前签名 URL，持久状态只保留无 query 提示。生产级 SQLite → 刷新 → mock DNS/HTTP → MP4 探测 → SHA-256 归档 → Emby 组合通过，零工作重放且不保留签名 URL、query 或私有字段。专项 `302 passed in 4.04s`、detail 契约 `100 passed in 70.92s`、完整 `1956 passed, 1 skipped in 408.57s` 及全部质量/构建/文档/上游/审计门通过。`playback_list`/画质选择、封面、转发、混合媒体及全部真人行继续待实现或保持 `NOT_RUN`。
- 执行 0032 交付（计划 `286dac9`，实现 `95758c2`）：锁定的抖音逗号拼接 `note_download_url` 图集被冻结为严格全有或全无解析器——每项必须恰为一个不含内嵌逗号的合法 URL，重复与畸形项以 `INVALID_RECORD` 隔离而非静默丢弃，图集边界为 1–64 张。`_normalize_dy` 物化 `ContentKind.IMAGE`（一张）或 `ContentKind.GALLERY`（2–64）及有序 `{aweme_id}:image:0..N-1` IMAGE 资产，video/music/cover 字段保持宽容解析、空字段回退字节级兼容；一个断言静默丢弃子项的既有集成 fixture 按隔离契约更新。每个图集 position 经一次精确 numeric-ID detail 运行重新解析当前签名 URL，路径漂移以 `locator_refresh_asset_mismatch` 关闭。生产级 SQLite → 刷新 → mock DNS/HTTP → 静态 PNG sniff 门 → SHA-256 归档 → Emby poster/backdrop/两张 gallery 图/NFO 组合通过，零工作重放且不保留签名、哨兵或签名 URL。专项 `316 passed in 5.09s`、DB 摄取契约 `25 passed in 2.64s`、完整 `1971 passed, 1 skipped in 390.84s` 及全部质量/构建/文档/上游/审计门通过。视频+图片混合 Asset 语义、图集音乐、动图漂移、同 ID 字节替换及全部真人行继续待实现或保持 `NOT_RUN`。

- 执行 0033 交付（计划 `92651bc`，实现 `966ccef`）：知乎 extractor 边界 shim 为 2–64 张静态图片物化一个完整有序元组（逐图属性优先级选择、两两互异），恰一张图的 v1 捕获保持字节级兼容，超界、无效、重复或禁用媒体的回答不捕获。一个私有 v2 字段以严格防碰撞与递归移除跨越边界；`_normalize_zhihu` 物化 ARTICLE 与 `{content_id}:image:0..N-1` IMAGE 资产并对双字段与畸形漂移隔离。惰性刷新通过应用层组装的 `zhihu_image_source_hints` 上下文绑定完整持久兄弟元组，每个 position 经一次精确 canonical-answer detail 子进程重新解析当前签名 URL，漂移以 `locator_refresh_schema_changed` 关闭。生产级 SQLite → 刷新 → mock DNS/HTTP → 静态 PNG 门 → SHA-256 归档 → Emby poster/backdrop/两张 gallery 图/body/NFO 组合通过，零工作重放。专项 `538 passed in 71.18s`、完整 `1984 passed, 1 skipped in 336.62s` 及全部质量/构建/文档/上游/审计门通过。文章、zvideo、动图漂移及全部真人行继续待实现或保持 `NOT_RUN`。

- 执行 0034 交付（计划 `eeff45e`，实现 `26c2b3e`）：锁定 store shim 在两个子进程的 `update_kuaishou_video` 边界精确捕获冻结的 `photo.ext_params.atlas.pics[].cdn` 形状（1–64 个两两互异、HTTPS 静态扩展名候选）；insecure、重复或超界图集不捕获。`_normalize_ks` 物化带有序 `{video_id}:image:N` 资产的 IMAGE/GALLERY 加可选 COVER 伴随，普通视频 photo 字节级兼容。KS IMAGE 加入适配器刷新支持集合，每个 position 经一次精确 numeric-ID detail 子进程重新解析当前签名 URL。生产级 SQLite → 刷新 → mock DNS/HTTP → 静态门 → SHA-256 归档 → Emby 双图 gallery 组合通过，零工作重放。专项 `445 passed`、detail 契约 `106 passed in 69.98s`、完整 `2002 passed, 1 skipped in 352.79s` 及全部质量/构建/文档/上游/审计门通过。图集文案、动图漂移、混合语义及全部真人行继续待实现或保持 `NOT_RUN`。
- 执行 0035 交付（计划 `ecc08da`，实现 `f2f4bc9`）：微博视频捕获新增有界封闭 `playback_list` 回退，在 `1080p > 720p > 540p > 480p > 360p` 偏好下选择最高合法项并经 0031 校验器重校验；标量路径保持第一且字节级兼容，不可用形状不捕获。真实子进程契约证明选择与关闭；集成证明与标量形状等价的归一化/下载/归档/Emby 与零工作重放。专项 `451 passed`、完整 `2010 passed, 1 skipped in 360.55s` 及全部质量/构建/文档/上游/审计门通过。杜比/Hi-Res 标签、封面及全部真人行继续待实现或保持 `NOT_RUN`。
- 执行 0036 交付（计划 `1ad49a7`，实现 `72e9f62`）：微博 shim 只与可捕获视频一同捕获封闭的 `page_info.pic_info.pic_big.url` 封面，新私有字段严格防碰撞跨越边界，`_normalize_wb` 物化 `{note_id}:cover:0` COVER 资产且 WB COVER 加入适配器刷新支持集合。生产级双资产 SQLite → 刷新 → 下载 → 归档 → Emby poster 组合通过，零工作重放。专项 `341 passed in 4.29s`、完整 `2016 passed, 1 skipped in 370.47s` 及全部质量/构建/文档/上游/审计门通过。其他封面尺寸及全部真人行继续待实现或保持 `NOT_RUN`。
- 执行 0037 交付（计划 `d858147`，实现 `c5682e5`）：逗号拼接的小红书 `video_url` 标量冻结为有界 1–16 有序多视频形状，超界归一化隔离、刷新标量放宽与完整视频元组的 creator 目标绑定。双视频集成组合双 position 下载并发布两个 Emby 集，零工作重放。专项 `344 passed in 6.32s`、完整 `2020 passed, 1 skipped in 370.56s` 及全部质量/构建/文档/上游/审计门通过。实况照片及全部真人行继续待实现或保持 `NOT_RUN`。
- 执行 0038 交付（计划 `650c256`，实现 `8c80073`）：新的锁定 store shim 为恰一张图的 `type="normal"` note 捕获冻结的 `image_list[0].live_photo.stream.h264[0].master_url`，`_normalize_xhs` 物化为一图加一视频的 MIXED，creator 回退绑定精确形状。共享 fake fixture 补齐最小 store 模块。生产级双资产组合发布带 poster 的 Emby 集，零工作重放。专项 `355 passed in 6.92s`、detail 契约 `116 passed in 80.18s`、完整 `2032 passed, 1 skipped in 371.84s` 及全部质量/构建/文档/上游/审计门通过。多图实况 gallery 及全部真人行继续待实现或保持 `NOT_RUN`。
### 阶段 5 — 平台逐项验收
- 状态：保持为最终操作者协助门；完成度归档（执行 0042，[`archive/upstream-replication-review.zh.md`](archive/upstream-replication-review.zh.md)）后收敛为执行 0047。全部真人行在部署主机记录前保持 `NOT_RUN`。
- 使用用户授权账户逐项验收小红书、抖音、快手、哔哩哔哩、微博、贴吧与知乎。
- 逐平台记录登录步骤、预期挑战、内容缺口与速率限制。
- 验收：每个平台都有能力矩阵条目与可复现 smoke-test 记录；缺少凭据时标记为外部验证阻塞，不能静默冒充通过。

### 阶段 6 — 发布准备
- 状态：文档项由执行 0045（备份恢复与升级运维指南）与 0046（安全与隐私审查加发布清单）交付；notices 与许可证审查截至 0046 为最新。干净 clone 验收按 [`deployment.zh.md`](deployment.zh.md) 在部署主机执行；恢复演练与任何外部审查仍为操作者行。
- 安全与隐私审查，以及备份/恢复和升级文档。
- 完成 notices、许可证审查与 GitHub 推送检查清单。
- 验收：干净 clone 可按文档安装、测试和运行；版本库不跟踪密钥或运行数据。

## 完成定义

只有当全部实现阶段通过自动验收，且七个平台的资格矩阵如实记录真人账户验证结果时，目标才算完成。需要真人扫码或账户凭据的登录挑战必须作为明确的用户协助验证步骤，不能用模拟结果冒充通过。
