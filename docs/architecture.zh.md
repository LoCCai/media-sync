[English](architecture.md) | **中文**

# 架构设计

- 状态：已接受基线
- 日期：2026-09-01

## 总体形态

首版采用 Python 模块化单体。CLI、有界本地调度器与工作器目前共享同一领域层和 SQLite 数据库；执行 0040 的本地 REST API 与内置 Web 控制台（`media-sync serve`）已交付。平台特有行为全部位于适配器之后；媒体下载和 Emby 渲染不接触上游字段名。

```text
CLI / Scheduler / REST API + Web 控制台（执行 0040）
           |
     Application services
           |
  +--------+---------+----------------+
  |                  |                |
Subscription      Sync runs       Library export
  |                  |                |
SQLite <---- normalized domain ----> Filesystem
                     |
             PlatformAdapter
              /            \
   Fake/fixture adapter   MediaCrawler process bridge
                                  |
                     separately pinned checkout
```

## 技术基线

- Python `>=3.11,<3.14`、`uv` 与 `src/` 包布局。
- Typer 提供已实现 CLI，Pydantic 校验边界；FastAPI 承载执行 0040 的本地 REST 接口与内置控制台。
- 使用 SQLAlchemy 2.x 与 Alembic，受支持的默认数据库为 SQLite WAL。执行 0054-B 已用真实 PostgreSQL 验证四张 Operation metadata 表的竞态边界；完整 schema 迁移与生产 PostgreSQL 部署仍属后续工作。
- 已实现媒体工具使用 `httpcore`/`httpx` 流式下载、音视频强制且有界的 `ffprobe` 验证、标准库 XML 生成，以及受限冻结形状下的 FFmpeg stream-copy mux/remux/concat（DASH 合并、单段 FLV 转封装、多段拼接）。通用转码、编解码修复与幻灯片渲染仍延期。
- 使用 `pytest`、Ruff 与 mypy，并采用确定性夹具及 golden 目录树。

工具链把 uv 钉在锁文件作者版本（0.9.18，uv.lock revision 3），并在 Python 3.11/3.12/3.13 矩阵验证；容器镜像基于 Python 3.13 且使用同一钉版 uv。执行 0048 的 0.12.9 镜像钉版与已提交锁版本不兼容，已作为阶段 B 首个构建发现重新对齐。

## 模块边界

| 模块 | 职责 | 禁止 |
| --- | --- | --- |
| `domain` | 枚举、实体、值对象、状态转换 | 导入框架或上游模块 |
| `application` | 用例、端口、事务编排 | 解析平台原始字典 |
| `infrastructure.db` | 模型、迁移、仓库、任务领取 | 执行爬虫或下载 |
| `adapters` | 能力发现、登录会话、归一化发现 | 写 Emby 媒体库 |
| `integrations.mediacrawler` | 外部进程、安全环境、输出导入、兼容修正 | 内嵌或修改上游源码 |
| `media` | 安全下载、校验与强制音视频结构探测，以及有界冻结形状下的 FFmpeg stream-copy mux/remux/concat；通用转码与编解码修复仍延期 | 依赖爬虫实现 |
| `exporters.emby` | 确定性路径、NFO、图片边车 | 请求平台 API |
| `interfaces` | 已实现 CLI、依赖装配与执行 0040 的 REST API/控制台投影 | 包含业务规则 |

## 归一化模型

```text
Account 1 --- * Subscription * --- 1 Author
                                  |
                                  * Content 1 --- * Asset
Account/Subscription 1 --- * SyncRun --- * RunEvent
Subscription 1 --- * Job
Content 1 --- * ExportRecord
```

- 平台、适配器、登录方式、凭据引用、隔离 profile 路径与认证状态。
- `(platform, remote_id)`、显示名/handle/profile/avatar 与 raw envelope。
- 账户/作者关联、启用标志、间隔、条数上限、cursor 与调度时间戳。
- `(platform, remote_id)`、类型、标题、正文、URL、发布时间、指标与 raw envelope。
- 有序图片/视频/音频/字幕/封面引用、下载状态、本地路径、MIME、字节数与校验和。
- 持久同步状态、脱敏 manifest、计数器、时间戳与分类错误；它不拥有 worker 租约。
- 持久 attempt、调度 scope、租约 owner/token/expiry、payload/result 与分类错误；全部 worker 领取和 fencing 均归属于此。
- 导出器/版本、来源指纹、输出路径与渲染指纹。

数据库之外暴露的所有标识符都是 UUID。时间戳以 UTC ISO-8601 存储；原始时区/epoch 字段保留在 raw envelope 中。

## 状态机

```text
SyncRun: queued -> claimed -> awaiting_auth -> running -> ingesting -> succeeded
                         |          |            |            |
                         +----------+------------+----------> failed_retryable
                                                            -> failed_terminal
                                                            -> cancelled

Asset: discovered -> queued -> downloading -> downloaded -> verified
                         |           |              |
                         +-----------+------------> failed_retryable / failed_terminal

ExportRecord: pending -> running -> succeeded
                         |
                         +-------> failed_retryable / failed_terminal
```

Job 领取使用租约时间、worker ID 和每次尝试新生成的 fencing token。工作器崩溃后，只有租约过期的 Job 才能被回收；旧执行不能借用同一 worker ID 后续领取的新租约完成任务。对资产下载而言，精确且已到期的 owner/token 只有在 reclaim 尚未改变 token 时才可续期；renew 与 reclaim 是单胜者 CAS。状态变更使用 CAS，事件序号原子分配，计数在事务内更新。下载流使用绑定 generation 的 `.part`；归档和 Emby 发布分别使用下文的 no-clobber 协议。

Emby/Jellyfin 导出器绝不把资产推进到 `exported`。一个已验证的归档 blob 可能被多个导出器版本和目的地消费，因此单次导出的完成状态属于 `ExportRecord`。`AssetStatus.EXPORTED` 词表仅为兼容性保留，layout v1 不使用它。

迁移 `0003_media_download_emby` 引入了 `0002_checkpoint` 无法表达的 generation 身份。因此 downgrade 会先清空 `assets.download_job_id`，再删除所有与 generation 绑定的 `asset_download` Job。已成功的 `export.emby` Job 及 record 作为持久发布链保留。未成功的 Emby Job 及 record 会被删除，避免 natural identity 污染后续再升级；唯一例外是携带结构严格有效的封闭发布 intent 的 Job 及该 intent 明确点名的 records，它们会保留以便后续执行精确逐字节校验恢复。

### 持久订阅调度器

迁移 `0004_scheduler_control_plane` 新增单调递增的订阅 schedule revision、Job 调度 scope、active 周期部分唯一索引，以及持久平台/账户 lane。有界 tick 会按 null-due 与时间到期确定性排序，并把 `subscription:<id>:schedule:<revision>` 精确物化一次。终态收尾从完成时间按 fixed delay 推进 `next_run_at`，因此停机不会形成追赶风暴。downgrade 只在移除调度列前删除 scheduler Job/lane，并保留执行 0005 的下载/导出身份，包括原本会被 SQLite batch 重建意外清空的资产下载关联。

每个 `sync.subscription` Job 都冻结封闭 retry-policy payload。领取会先按 Job 类型限定 reclaim/requeue 变更，再同时执行全局容量与两条持久 lane：并发、最小启动间隔，以及带唯一精确探针的 closed/open/half-open circuit。有界 equal-jitter 指数退避会遵守合法 `Retry-After` 下界，并在达到 attempt 上限时终态化。认证与真人交互结果停留在休眠的 `waiting_auth`/`waiting_user`，只有显式 resume 才能恢复。pause、resume 与 run-now 控制后续物化；cancel 会 fence 当前精确租约。

worker 以短 claim/start/finalize 事务运行，并在 handler 等待外部工作时维持精确 token heartbeat。Fake handler 每次数据库变更前，都会在同一 session 中取得 SQLite writer slot，并校验仍为 running、未过期的 owner/token；每次 adapter await 前先提交当前事务。因此 cancel/reclaim 与 handler 持久化会串行决定胜者，不存在检查到使用之间的空隙。原始 handler 异常、畸形结果、恶意 adapter/domain 错误码及跨订阅 SyncRun ID 都会映射为封闭调度错误码，绝不进入 Job/lane/运维投影。通用 worker 只处理 `sync.subscription`；`asset_download` 与 `export.emby` 继续由执行 0005 的精确 owner 负责。

执行 0006 只随附确定性 Fake handler，并且只验收 scheduler 启动节流，不宣称覆盖每次上游 HTTP 请求。MediaCrawler 定时执行、manifest v3 请求延迟绑定、长子进程 heartbeat/cancel，以及自动 sync → download → export DAG 均属于后续独立工作。

基础 Fake 工作流使用调用方拥有的外层事务，并为单条内容使用保存点。分类后的爬虫失败可以提交失败运行记录及此前已成功归一化的内容；数据库失败或事务拥有者显式拒绝时会回滚整次尝试。MediaCrawler 在浏览器/网络等待期间不持有 SQLite 事务；父进程认证的完成回执会密封不可变输出快照，随后导入按旧到新的有界批次提交，并原子发布该批内容、run 计数与带 fencing 的 checkpoint。

适配器分页 cursor 本身不能充当可靠的增量高水位。因此订阅会同时保存发布时间及该时间点全部已知远端 ID，回填分页位置则单独跟踪。桥接/原生适配器必须从最新页开始、扫描重叠窗口、接收水位边界上的新 ID，并且只在其排序契约已验收时停止。

## 平台适配协议

每个适配器都会报告一个 `CapabilitySet`，并实现窄化的异步端口：

```python
class PlatformAdapter(Protocol):
    def capabilities(self) -> CapabilitySet: ...
    async def ensure_session(self, account: Account, interaction: InteractionPort) -> AuthResult: ...
    async def resolve_author(self, account: Account, reference: str) -> AuthorSnapshot: ...
    async def iter_author_content(
        self, account: Account, author: Author, cursor: Cursor | None, limit: int
    ) -> AsyncIterator[ContentSnapshot]: ...
```

能力集合包含登录方式、作者引用形式、内容种类、原生媒体可用性和真人交互要求。不支持的方法必须在任务入队前失败。

## MediaCrawler 桥接

桥接器是可选且需要明确接受许可证的组件。它把锁定 checkout 作为子进程启动，使用唯一输出根，且每个账户同时只运行一个爬虫。公开参数向量只包含已验证的 Python/runner 入口和一个受限的非机密 specification 路径；平台选项在独立运行器内部应用。

Cookie 值与含机密的创作者引用组件通过私有环境通道注入，由一个小型独立运行器读取，并在任何上游导入或后代进程启动前移除。解析后的机密创作者输入保留类型化 `SecretValue` 来源；含义不明的普通 query/fragment URL 默认拒绝。这避免了上游 WebUI 把 Cookie 同时放进命令行及其记录命令的方式（`api/services/crawler_manager.py:113-128, 205-239`）。运行器还提供隔离的账户 profile 路径，并在不修改上游文件的前提下绕过知乎创作者 CLI 缺失的赋值。上游二进制下载保持关闭；归一化发现后由 media-sync 负责可恢复获取。

由于 MediaCrawler 按日期命名并追加文件，每个任务使用唯一 `SAVE_DATA_PATH`，不会跟踪共享的每日文件。子进程退出并清理后代后，父进程先拒绝任何已知 Cookie/签名引用的精确回显，再把精确目录/文件集合、大小和 SHA-256 密封到与 manifest 绑定的完成回执。导入验证路径/链接不变量，并在归一化前只读取一次为不可变字节，从而消除“检查后重新打开”竞态。

MediaCrawler manifest v2 绑定账户、订阅、任务、爬取起始 checkpoint revision、前向/回填模式、登录方式、数量上限及作者指纹。旧密封爬取只能针对当前 revision 补齐缺失记录，不能携带 continuation，也不能回退现有游标或水位。

执行 0013 新增一个封闭的 Bilibili detail-only 桥，但不改变 forward 爬取产物。一个普通 numeric-aid 视频经 forward 归一化后会精确产生一个仅 locator 的 position 0 视频，其稳定 remote ID 为 `<aid>:video:0`、`source_url=NULL`；只有存在合法封面 URL 时才会另行产生封面，动态不会合成该视频。只有精确的 `bili/content/video/position=0/<aid>:video:0/NULL-hint` 形状才能进入可空刷新分支。detail child 把请求 aid 与 `View.aid` 绑定，选择首个经过校验的 CID，调用锁定的播放地址方法，并只接受一个合法主 progressive `durl.url`。

签名 URL 只存在于具名且 repr-safe 的 child 结果、有界进程 frame、内存私有 JSONL 字段及当前 HTTP 请求中。注入只发生在普通 JSONL 已读取之后，attempt 树绝不重写。内存桥会在归一化前拒绝预先存在的私有字段碰撞。normalizer gate 默认关闭；仅对 detail 字节显式开启时才接受该字段，并在创建持久 Content/Asset raw 元数据前递归移除它。既有 Asset 可空 source 持久化与稳定 `adapter_refresh` 来源已经满足需求，因此不需要 schema migration。

在执行 0013 的历史边界，Bilibili forward 元数据没有 CID，因此持久身份有意采用逻辑首 P 槽，而不是页面 generation。尚未解析时会校验当前首 CID，但后续同 aid 首 CID 替换无法自动使已验证字节失效或提升 generation。执行 0023 现为兼容多分 P 投稿增加 CID-aware 发现，同时保留该精确单 P 槽位。

执行 0014 对既有快手纯 ID detail 路径完成一个普通单视频记录的验收。精确一个合法播放 URL 产生 `<video_id>:video:0`；可选封面产生 `<video_id>:cover:0`。完整 URL 只留在内存发现 snapshot 与 detail/HTTP 边界；每份持久 raw 都会被结构化缩减为规范 HTTP(S) origin/path，不含 userinfo、query 或 fragment。非字符串及嵌套 schema 漂移会关闭失败，防止未来对象形状的签名 URL 变成持久元数据。隔离 detail child 通过 `KS_SPECIFIED_ID_LIST` 接收纯视频 ID；成功时 UUID-scoped attempt 数据会在返回前删除。

快手组合路径把惰性刷新绑定到精确合格的 AssetRefreshSource、Account 与 Subscription。视频和封面都使用封闭默认 HTTP profile，因此不会臆造平台专用 Referer/Origin 或凭据 header。强制视频探测、不可变 SHA-256 发布及既有 Emby layout 会产生主 `.mp4`、海报、NFO 与白名单 source 元数据。仅 query 轮换会保留同一语义身份/generation 与已验证字节；它无法检测同一 video ID 与 origin/path 下的字节替换。

执行 0015 关闭全部四个抖音媒体字段的持久 raw 边界：`video_download_url`、`cover_url`、`music_download_url` 与 `note_download_url`。已接受的平面 HTTP(S) URL 只保留规范 origin/path。逗号分隔的 note 标量会规范化为有序平面序列；mapping、嵌套容器及含逗号的 sequence 子项按子项变为 `None`，含逗号的非 note 标量按字段关闭失败。对应的抖音 Asset 解析器拒绝同一类歧义漂移，避免嵌入的第二 URL 经 Asset source hint 留存。合法且已接受的 Asset snapshot 可继续在内存携带完整瞬态 URL；漂移的不透明子项不会成为 Asset。

经过验收的抖音组合有意限制为一个 decimal aweme ID，note/music 字段为空、精确一个视频与可选封面。process-runner 契约使用真实隔离 fake checkout，证明 numeric `DY_SPECIFIED_ID_LIST`、detail 配置、稳定 profile 及成功 attempt 清理。另一个平台 E2E 使用 fake detail runner、mock DNS/HTTP、合成 MP4/PNG 与受控 probe，但会贯穿生产精确来源惰性 refresher、默认媒体 request profile、下载状态机、SHA-256 归档及 Emby `.mp4`/海报/NFO/source publisher。这两类测试互为补充；E2E 不会启动真实 child。仅 query 变化的重放会保留 generation，并读取实时计数证明不会新增 detail/网络/probe 调用，但无法发现同 ID/同 origin/path 字节替换。精确 Subscription 来源是选择权限，不是远端作品属于所声明作者的独立证明。

执行 0016 实现 `a77ca74` 在不改变已验证上游 checkout 的前提下增加共享微博图片捕获边界。只有 creator 或 detail child 已从已验证 checkout 导入模块后，集成才证明 `store.weibo` 属于该根目录，并包裹其精确 `update_weibo_note` → JSONL `store_content` 边界。任务局部 `ContextVar` 会在 note coroutine 重叠时仍把每次捕获的 `mblog` 绑定到对应内容行。私有字段碰撞或部分重复安装会关闭失败；私有捕获字段则在构建持久 raw 元数据前递归移除。

捕获门只接受具有规范正 numeric note ID、`retweeted_status is None`，且 `page_info` 缺失、为 `null` 或空对象的普通原创。`pics` 必须是非空、扁平、有序的列表，每项包含唯一且有界的 `pid`/URL。每个来源必须是精确 `sinaimg.cn` 或其子域上的无 query HTTPS URL，文件名扩展名不区分大小写地属于静态 `.jpg`、`.jpeg`、`.png` 或 `.webp`，随后按锁定规则转换为 `https://i1.wp.com/<sina-host>/large/<filename>`。一个 locator 产生 `ContentKind.IMAGE`，多个 locator 产生 `ContentKind.GALLERY`，有序 IMAGE Asset 使用 `<note-id>:image:<position>`；导入创建稳定 `adapter_refresh` locator 及精确 AssetRefreshSource → Subscription → Account 来源链。

微博精确 detail 权限在 refresh-context、父 request 与 child payload 三个边界重复执行。每层只接受隐式 `None` 引用，或与同一个规范 numeric content ID 完全相同的普通 `str`；URL、`SecretValue`、字符串子类、不同 numeric ID 与畸形 ID 都会在该层继续前失败。真实隔离 fake-checkout 契约覆盖 creator 与 detail process-runner 的 shim 安装、配置及清理；另一个双图组合测试有意替换为 fake detail payload、mock 公网 DNS/HTTP 与合成 PNG 字节，但会贯穿生产来源选择、`MediaRequestProfile.DEFAULT`、图片 sniff/probe 校验、两个不可变 SHA-256 archive 发布，以及幂等 Emby/Jellyfin poster/backdrop/双文件 gallery/NFO/白名单 source 渲染。默认媒体 profile 不提供 Cookie、Authorization、Referer 或 Origin。微博视频/有效 `page_info`、GIF/动图语义、长图专用处理、有界 creator 分页、直连新浪 profile、同 ID 替换检测及清理失败 quarantine 仍延期；全部真人登录、作者扫描、detail/图片代理/CDN 字节及 Emby/Jellyfin 服务器验证保持 `NOT_RUN`，贴吧/知乎媒体发现、七平台完整媒体覆盖、REST/服务打包及多 worker HA 仍是更大的产品差距。

执行 0017 在计划检查点 `9d19e7e` 之后以实现提交 `2f8dbaa` 补齐小红书作者权限自动查找，且不需要 schema migration。惰性刷新先选择唯一精确合格的 `AssetRefreshSource → Subscription → Account` 链；显式 `xhs_detail_reference_ref` 解析为目标 note URL，并作为兼容覆盖优先使用，否则只能解析该 Subscription policy 的 `mediacrawler.creator_input.secret_ref` 作为作者 URL，同时把 `subscription.max_items` 作为作者查找上限。逐 Asset runtime 会缓存已绑定 refresher，因此选择 preflight 与后续下载复用同一精确持久 scope 和已解析密钥。

小红书 detail 与 creator 输入构成 XOR，并由 `MediaCrawlerRefreshContext`、父级 `MediaCrawlerDetailRequest` 及反序列化后的 schema-v3 child loader 分别重复验证。note 权限必须使用允许的小红书 HTTPS note 路径，且 ID 等于可信 content ID；creator 权限必须使用精确 `/user/profile/<可信作者 ID>`。两类 URL 都拒绝 userinfo、port 与 fragment，并要求精确一个非空 `xsec_token` 及一个非空 `xsec_source`。creator 模式会清空所有无关 creator/detail 列表，只启用一个小红书作者 URL，使用单并发，关闭评论/媒体副作用，并把 `CRAWLER_MAX_NOTES_COUNT` 设为已经受 watchdog 约束的 Subscription 上限。child 可以返回多条 JSONL，但归一化后必须只有一个匹配的 content remote ID，并且只能选出一个精确匹配 Asset kind/position/source hint 的资产。在 Execution 0017 边界，自动目标必须是普通 `type="normal"`、Content 为 IMAGE 或 GALLERY，且具有非空、有序、全部为 IMAGE 的 Asset 集。

执行 0017 的双图组合使用 fake detail 结果、mock 公网 DNS/HTTP 与合成 PNG 字节，同时贯穿生产来源选择、`MediaRequestProfile.DEFAULT`、图片校验、两个不可变 SHA-256 归档发布，以及幂等 Emby/Jellyfin poster/backdrop/gallery/NFO/白名单 source 输出；重放不新增 detail、HTTP、归档或导出工作。DEFAULT 不添加 Cookie、Authorization、Referer 或 Origin。已验证的小红书归档缺失或无效时，必须先通过同一精确权限 preflight，才能隔离或持久重置以修复；即使 CLI 调用原本不需要重新下载也不例外。已解析的作者/note 权限与签名媒体 URL 只存在于 repr-safe 私有 runtime frame、内存及当前 HTTP 请求中。写入 SQLite 前，小红书 raw 会移除 `xsec_token`/`xsec_source`，并清除 `note_url`、`image_list`、`video_url` 的 query；归档元数据、Emby 输出、运维错误及成功 attempt root 均不保留这些密钥或签名。在该历史边界，此前显式 note 小红书视频刷新继续兼容，而自动视频、实况照片、动图及混合媒体尚未验收。

执行 0018 在计划检查点 `c9d3586` 之后以实现提交 `356e254` 增加第二条自动 creator 目标分支，且无需 migration 或上游修改。它只接受唯一匹配的 raw `type="video"` 行。在信任归一化 Asset 前，raw `video_url` 必须是精确包含一个候选的普通标量，raw `image_list` 必须是包含零或一个候选的普通标量；空分段、首尾空白、重复、畸形+有效列表、多候选及容器漂移均关闭失败。归一化目标必须把这些值一一映射为 position 0 的唯一 VIDEO 与可选 position 0 IMAGE，不得出现其他 Asset kind 或身份/source-hint 漂移。纯视频产生 `ContentKind.VIDEO`；一张封面加一个视频产生本次窄范围验收的 `ContentKind.MIXED`。

自动视频初始 locator 在 lowercase、IDNA 与单个尾点规范化后，必须是 `xhscdn.com` 或合法子域上的有界 HTTP/HTTPS URL，使用严格 LDH label、非根路径、无 userinfo/fragment/空白/控制字节，并且只能使用 scheme 默认端口；显式 `http:80` 与 `https:443` 可接受。重定向目标继续遵循既有逐跳公网策略，而不是小红书专属规则。刷新返回 `MediaRequestProfile.DEFAULT`，与锁定上游不带 header 的 GET 一致。绑定源码的合约会执行锁定的小红书 store 函数，真实隔离 fake checkout 证明 creator 进程行为，内嵌真实 H.264 MP4 则独立通过生产 `FFprobeMediaProbe`。确定性的 SQLite → mock DNS/HTTP → SHA-256 归档 → Emby 组合使用记录型 probe 获取精确调用数，并证明仅 query 变化时零工作重放。持久 raw、Asset hint、归档元数据与输出保持无 query/userinfo/fragment。多视频、多图片、更广混合媒体、实况照片及动图继续延期；全部真人登录、creator/feed/detail、小红书 CDN 字节及 Emby/Jellyfin 扫描/播放行保持 `NOT_RUN`，更大的七平台目标继续推进。

执行 0019 在计划提交 `dc1714c` 后以实现提交 `2edb9d7` 增加一条源码绑定的知乎回答图片分支，且无需 migration 或上游修改。锁定的默认 creator 路径已接收原始回答 HTML，但会在无媒体字段模型进入 JSONL 前把它压平成纯文本。校验 checkout 导入后，集成自有 shim 包装精确 extractor、`update_zhihu_content` 与 JSONL `store_content` 对象。捕获绑定到精确返回的 Pydantic 对象；任务局部 `ContextVar` 只在该对象进入嵌套存储时存在。这是因为上游 detail 在 `asyncio.gather` 子任务中提取、随后在父任务中存储。gather child → 父 store 及真实 Pydantic 携带/消费/不序列化合约现已通过。模块来源、版本、完整/部分安装、creator 上限及私有字段冲突漂移均关闭失败；creator 与 detail child 都在校验导入后安装 shim。

回答解析器只接受有界 `content_type="answer"` HTML、规范正整数回答/问题 ID、精确一个 `img` 节点及唯一无歧义静态 locator。属性选择遵循冻结的 `data-original` → `data-actualsrc` → `src` 优先级；重复的选中属性及竞争性的 `srcset`、`data-src` 或 lazy-image 候选均关闭失败。可播放/player/iframe/object/picture/source/audio/SVG 标记、多图片节点及畸形+有效混合均不验收。Canonical 回答权限拒绝 query/fragment 分隔符。初始图片 locator 必须是 `zhimg.com` 或严格 LDH 子域上的有界 HTTPS URL，使用非根 `.jpg/.jpeg/.png/.webp` 路径，不含 userinfo/fragment/反斜杠/控制字符/空白、空 query 分隔符或非默认端口，且只有非空瞬态 query 可留在内存。

Scheduled creator 安装接收精确 manifest/Subscription `max_items`，并且只替换锁定的全回答循环。每次 API 调用最多请求剩余数量；响应 page/data/paging 类型、空或短非终止页、重复 ID、响应基数与 extractor 基数均校验。真实 scheduled-child 证据把 `max_items=23` 映射为页面大小 `20 + 3` 的两次 API 请求与两次 callback 调用，callback 精确处理 23 行，页间执行一次节奏 sleep；达到上限后没有第三次请求或额外 sleep。因此 `Platform.ZHIHU` 已从 `FULL_HISTORY_PLATFORMS` 移除：与仍然无界的已审计路径不同，知乎订阅可保持 `allow_full_history=false`。这是上游工作量边界，不是导入 watchdog 或下游截断声明。

归一化保持 `ContentKind.ARTICLE`，并物化精确一个 position 0、remote ID 为 `<content_id>:image:0` 的 IMAGE；版本化私有字段递归移除，持久 raw/SQLite source hint 只保留无 query/userinfo/fragment 的身份。惰性刷新沿精确 `AssetRefreshSource → Subscription → Account → Content` 链，并只从持久 canonical 回答 URL 派生允许的非密钥 detail 权限。Refresh context、父 request 与 child loader 独立复核该权限；归一化 detail 必须返回唯一匹配的 ARTICLE/IMAGE/source hint。当前图片 URL 在返回无凭据 `MediaRequestProfile.DEFAULT` 前重新校验。知乎 IMAGE 自动启用有界静态结构门：合格 JPEG/PNG/WebP 通过，GIF/APNG/animated WebP/AVIF 在 normal、recovery 与 takeover 路径失败。该门是结构/容器资格校验，不是完整像素解码。SQLite → fake detail → mock 公网 DNS/HTTP → SHA-256 归档 → Emby 组合、query 零工作重放及保留 SQLite/runtime/archive/export/WAL/SHM 审计通过。最终专项门通过 505 项，完整套件通过 1543 项且仅跳过一项 Windows 不适用用例，全部质量门通过，全新 461 项复核未发现 P0/P1/P2。实现 `2edb9d7` 已推送；当前没有真实脱敏夹具，全部真人行保持 `NOT_RUN`。多图、文章与 zvideo 延期；在执行 0019 的历史边界，贴吧仍没有已验收媒体切片。

执行 0020 在计划提交 `df7a38a` 后以实现提交 `8a0e935` 增加一条源码绑定的贴吧首楼图片分支，且不新增 migration 或修改上游。锁定的 `page_pc` 响应把结构化 `first_floor.content` 交给 `TieBaExtractor.extract_note_detail_from_api`，但 extractor 只保留文本，之后无媒体字段的 `TiebaNote` 进入 JSONL。校验 checkout 导入后，集成自有 shim 包装精确 extractor、`update_tieba_note` 与 JSONL `store_content` 对象。捕获绑定到精确返回模型，通过该对象跨越 gather-child → parent-store，并只在嵌套存储期间进入任务局部 `ContextVar`。模块来源、版本、完整/部分安装、对象/行身份及递归私有字段冲突均关闭失败。Scheduled child 还把锁定 creator 循环替换为精确成功的 Subscription-`max_items` 边界：23 形成 `20 + 3` 详情/callback 行，只执行一次页间 sleep，且无第三页或达到上限后的 sleep。

在执行 0020 边界，冻结媒体门只接受规范正整数主题 ID、精确 `https://tieba.baidu.com/p/<id>` 权限、普通整数 type-0 文本兄弟项及精确一个当前十键整数 type-3 图片对象。它只选择精确 `tiebapic.baidu.com` 上的签名 HTTPS `origin_src`，要求规范 `/forum/pic/item/<40 位小写十六进制>.<jpg|jpeg|png|webp>` 及一个有界 `tbpicau`；持久状态只保留 scheme/authority/path。归一化保持 ARTICLE 并创建唯一 `<note_id>:image:0` IMAGE。惰性刷新从 SQLite canonical 主题 URL 派生权限，把 numeric ID 发送给锁定详情入口，并要求唯一精确 ARTICLE/IMAGE/无 query hint 匹配，之后以无凭据 DEFAULT profile 返回新校验的签名 URL。贴吧 IMAGE 在 normal、recovery 与 takeover 路径使用有界静态结构门：合格 JPEG/PNG/WebP 通过，GIF/APNG/animated WebP/AVIF 失败。确定性 SQLite → fake detail → mock DNS/HTTP → SHA-256 归档 → Emby poster/backdrop/gallery/body/NFO/source 组合及 query 零工作重放通过，且不保留私有字段或 `tbpicau`。在该历史边界，首楼 gallery 仍延期；真人登录/作者/detail/CDN 与 Emby/Jellyfin 服务器行保持 `NOT_RUN`，更大的目标继续推进。

执行 0021 在计划 `5095ed6` 后以实现 `e0fb8d5` 增加独立的 `__media_sync_tieba_first_floor_images_v2` 声明，用于精确两个有序 type-3 对象，同时保留 v1 单图声明与安装 marker。Shim 校验两个完整十键对象，派生互异无 query 身份，保持来源顺序，并拒绝双重私有声明、重复身份、三张及以上图片及全部未冻结内容形状。精确对象附着与任务局部嵌套 store 上下文继续跨越锁定 gather-child → parent-store 丢失边界，且不序列化私有列表。归一化保持 ARTICLE，产生 position 0/1 与 remote ID `<note_id>:image:0/1`；两个私有字段均递归移除。

在执行 0021 边界，贴吧惰性数据库加载器把完整单图或双图兄弟身份元组冻结进刷新上下文。双图任一 position 的请求都必须复现同一个 canonical ARTICLE、相同的两个有序无 query 身份及精确 position/remote-ID 映射；缺图、重排、替换、重复与双重声明均在返回 URL 前失败。当前选中签名 URL 会重新校验，并使用无凭据 DEFAULT profile。确定性双图组合证明 JPEG 加 PNG 静态资格、两次下载、两个不可变 SHA-256 归档、Emby poster/backdrop/两项 gallery/body/NFO/source 输出及 query 零工作重放。该精确双图切片当时尚未提供通用 gallery 语义；混合/富内容/回复媒体、同身份字节替换及全部真人登录/平台/CDN/Emby/Jellyfin 行继续延期或保持 `NOT_RUN`。

执行 0022 在计划 `fbcb7cf` 后以实现 `b6d03aa` 增加 `__media_sync_tieba_first_floor_gallery_v3`，用于精确 3–64 个有序、互异的当前 type-3 对象。64 图上限由捕获、归一化、刷新上下文与惰性数据库加载器共享；v1 继续代表精确单图，v2 继续代表精确双图，同一行只能声明一个版本。捕获校验每个完整十键对象，保持来源顺序、精确对象绑定与并发隔离；65 张图片、畸形对象、重复无 query 身份、多版本字段与未冻结内容类型均关闭失败。归一化产生 ARTICLE 加 `<note_id>:image:0..N-1`，递归移除三个私有字段，并只持久化有序无 query hint。

贴吧每个刷新 position 现携带完整 1–64 项兄弟身份元组。当前 canonical 详情必须复现相同数量、顺序、无 query 身份、position 与 remote ID；缺失、新增、重排、替换、重复或多版本结果均在返回 URL 前失败。选中当前签名 URL 会重新校验并使用无凭据 DEFAULT profile。确定性三图 SQLite → fake detail → mock DNS/HTTP → 静态门 → SHA-256 归档 → Emby 组合证明 JPEG/PNG/WebP 字节、三次下载/归档、poster/backdrop/三项 gallery/body/NFO/source、整树瞬态值不存在及 query-only 零工作重放。专项 `433 passed in 48.91s`、完整 `1688 passed, 1 skipped in 321.22s` 与全部质量/构建/文档/上游/审计门通过。超过 64 张的 gallery、混合/富内容/回复媒体、替换语义与全部真人行继续延期或保持 `NOT_RUN`；这是有界静态 gallery 支持，不是完整贴吧媒体支持。

执行 0023 在计划 `bd45478` 后以实现 `24fd41c` 增加源码校验的 Bilibili 捕获边界，且不新增 migration 或修改上游。锁定 checkout 与精确 store 对象通过校验后，集成会包装 `update_bilibili_video` 与嵌套 JSONL `store_content`。任务局部 `ContextVar` 把精确返回投稿的 `View.pages` 作为 `__media_sync_bili_pages_v1` 跨越 gather-child → parent-store 丢失边界。解析器只接受 1–64 个规范连续 page 编号与互异正 CID；page 列表缺失/为空时可把已校验顶层 CID 作为首 P。错误 aid、畸形容器、不连续 page、重复 CID、私有字段碰撞、部分安装与 65 分 P 均关闭失败。

归一化保留执行 0013 的精确单 P 身份 `<aid>:video:0`；只有合格 2–64 分 P 投稿会产生有序、仅 locator 的 `<aid>:video:cid:<cid>` VIDEO Asset。详情请求 schema v4 增加可选且经过校验的 `bili_video_cid`。Child 绑定请求 aid，重新取得完整当前分 P 元组，只为目标 CID 调用锁定 play API，并接受精确一个 progressive `durl`；内存详情 JSONL 以 `__media_sync_bili_pages_v1` 携带完整元组，并以 `__media_sync_bili_progressive_page_v2` 携带目标 CID/URL。两个私有字段及 legacy/私有播放 URL 字段都会在形成持久 Content/Asset raw 元数据前递归移除。

惰性数据库加载器为每个 Bilibili 目标冻结完整持久 VIDEO 兄弟元组。多分 P 刷新要求当前数量、page 顺序、CID、position 与 remote ID 完全一致，才以 `MediaRequestProfile.BILIBILI_MEDIA` 返回目标的新校验签名 URL；缺失、新增、重排、替换、重复或畸形分 P 都会在字节传输前失败。确定性三分 P SQLite → 定向 fake detail → mock 公网 DNS/HTTP → 受控 probe → SHA-256 归档 → Emby 组合证明三份不同字节流/归档、一个主媒体加两个 part 文件、NFO/source 输出、整树瞬态值不存在及 query-only 零工作重放。专项 `436 passed in 53.96s`、完整 `1739 passed, 1 skipped in 321.25s` 与全部质量/构建/文档/上游/审计门通过。DASH 音视频合并、多 `durl` 分段、FLV 转封装、字幕、弹幕、备用地址故障切换、超过 64 个分 P、番剧/付费/直播媒体及全部真人登录/API/CDN/Emby/Jellyfin 行继续延期或保持 `NOT_RUN`；这是有界多分 P progressive 支持，不是完整 Bilibili 媒体支持。

## 安全媒体获取

资产发现与下载器分别拥有不同字段。发现阶段可更新去 query 的来源提示与 locator，但不能覆盖已验证 MIME、字节数、SHA-256、归档路径或生命周期。同一远端身份与语义指纹的重放保留 generation 和已验证文件；远端 ID、origin/path 或稳定媒体提示变化时，以 fenced CAS 增加 generation 并清空下载字段；仅签名 query 轮换不会重置。

Locator schema v1 是封闭且规范的：

- `direct` 只存储无 query、无 fragment、无凭据的 HTTP(S) URL。
- `adapter_refresh` 只存储适配器名称和稳定的非机密资产键。其解析器可以返回不可序列化的内存态签名 URL；不支持的刷新以 `locator_refresh_unsupported` 失败。
- MediaCrawler 发现始终持久化 `adapter_refresh`，而确定性 Fake 路径可以持久化合格的 `direct` URL。

`ResolvedLocator` 还可选择一个封闭且不持久化的 request-profile 枚举。Bilibili media profile 只在 HTTP 层增加固定浏览器型 User-Agent、`Referer: https://www.bilibili.com/` 及匹配 Origin；禁止 Cookie、Authorization 与任意调用方 header，只有下载器拥有的 Range/If-Range 续传状态可以加入。重定向与续传会保留当前 profile；仅 adapter 使用的一次 401/403 路径会把新解析 URL 与其解析所得 profile 一并携带，而持久 locator 保持不变。

密钥分类会归一化 snake_case、kebab-case 与 camelCase 边界。`api_key`、`access_key`、带提供商前缀的变体、`private_key` 及 `signing_key` 等明确组合名称会被脱敏，`key`、`public_key`、`key_id` 等普通名称则保留。带凭据标记的路径段或赋值，例如 `/token/<value>/video.mp4` 或 `/download;session=<value>/video.mp4`，会通过有界百分号解码识别，包括已编码及双重编码的分隔符。通用 URL 落点会替换该凭据路径；`direct` 解析和资产 source-hint 派生会拒绝它，从而强制持久稳定的 `adapter_refresh`。`0003` legacy 回填复用同一规则：将不安全的 `source_url` 置空，且只用稳定 asset key 生成替换 locator；它不会追溯改写无关的 legacy raw envelope。

每个 HTTP hop 都独立解析；全部 DNS 答案必须为公网地址，连接固定到已验证地址并保留源站 Host header 与 TLS SNI。重定向由应用手动处理，禁用环境代理，跨源重定向不得继承 Range validator。续传元数据绑定资产 UUID、generation、规范 locator 指纹、validator、预期总长度与当前字节数。发布前必须通过严格的 `200`/`206`/`416` 语义、有界重启/字节/时长/header 限制、magic/MIME 校验、音视频强制且有界的 `ffprobe` 结构验证，以及最终 SHA-256 门禁。

已验证文件是位于 `archive/sha256/<first-two>/<sha256>.<verified-extension>` 的不可变、单链接普通 blob。应用在任何数据库变更前获取同一 `work_root` 下的逐资产 OS 锁，并持有至收尾。持久 Job 只保存规范 work/archive 根的 SHA-256 身份；不同 I/O scope 与本地锁竞争会在 reclaim、attempt 或资产变更前拒绝。应用用一个短事务领取并启动 job/资产，DNS、网络和文件系统工作期间不持有数据库事务，再用一个短事务原子验证资产并完成仍由当前 worker 拥有的 job。

归档所有权 guard 在临时复制、fsync、重哈希之后及 no-clobber link/rename 前，续期精确且未被 reclaim 的 token，并复核 generation/job 所有权；复用既有 blob 也经过同一 guard。由于文件系统提交与 SQLite 收尾不能组成同一事务，绑定 generation 的 `.part` metadata 会保留到数据库成功之后。精确的已提交结果可在不访问网络、不增加 attempt 的情况下恢复，包括最后一次 attempt 仅因租约到期而 terminalize 的情况。best-effort 清理发生在验证之后，不能反转成功。already-verified 行会复核规范 blob；损坏字节被隔离，缺失/无效持久归档状态通过 CAS 重置。这些保证以配置的运行根目录及全部祖先都是专用、由操作员控制的目录为前提。0.x 的路径式实现会拒绝操作时已存在的不安全对象及可检测的叶节点替换；同权限恶意进程并发替换父目录不在当前威胁模型内。

## Emby 目录映射

```text
library/
  xhs-creator-creator-id-<identity-hash>/
    .media-sync-managed-v1.json
    source.json
    tvshow.nfo
    Season 2026/
      S2026E<stable-number>-xhs-note-item-id-<identity-hash>.mp4
      S2026E<stable-number>-xhs-note-item-id-<identity-hash>.nfo
      S2026E<stable-number>-xhs-note-item-id-<identity-hash>-poster.jpg
      S2026E<stable-number>-xhs-note-item-id-<identity-hash>.assets/
        body.txt
        gallery-001-image-id-<identity-hash>.jpg
        source.json
```

文件系统身份不依赖可变显示名或标题。Season 使用 UTC 发布时间年份，缺失时回退首次发现年份；episode number 由 `(platform, remote_type, remote_id)` 稳定散列为正 32 位整数，同一 season 内发生碰撞时确定性失败，不静默改号。稳定远端 ID 写入带平台命名空间的 `<uniqueid>`。作者使用 `tvshow.nfo`，可播放内容使用 `episodedetails`；幻灯片渲染仍未实现/已延期，图库、正文、附件、字幕、封面和头像仍会完整保留。

渲染会先生成字节完整的 job-ID staging tree。所有权权威来自数据库：每个 succeeded `export.emby` Job result 保存不披露路径的 publication scope、output path、source fingerprint、tree SHA-256、manifest SHA-256、受管文件数量及精确 `predecessor_job_id`。这些 Job 必须组成唯一链；其 head，而非时间戳或仅从磁盘发现的 manifest，才是可信 predecessor。natural identity 包含 desired source 和精确 predecessor，因此允许 `A → B → A` 来源循环，同时拒绝分叉、Job 图成环和断裂祖先链。不同 export root 具有不同的 publication scope 哈希，因此形成独立链。

文件系统发布前，服务用精确 intent 续期所拥有的 Job 租约；intent 包含渲染后的 source/tree/manifest 身份、受管文件数量及相关 ExportRecord 身份。发布阶段持有作者级进程锁与 OS 锁，在任何变更前写 journal，并逐文件执行 no-clobber 操作；导出树不遗留硬链接或符号链接。当前 manifest 身份及每个 predecessor 受管字节都必须匹配数据库锚点。首次发布会拒绝意外 managed manifest，自洽伪造 manifest 不能认领用户文件。唯一 roll-forward 例外是同一 intent 已在数据库收尾前精确提交 desired tree。

安装后，每个 desired 受管文件及 manifest 都会在作者锁、journal 与回滚证据仍保留时完成身份/哈希复核，随后才能返回成功。中断事务的 roll-forward 会解析已安装的 desired manifest，并在清理前执行同样的完整树检查；不匹配时保留 journal 与 `RECOVERY_REQUIRED` 标记。用户修改及非受管路径会保留并返回分类冲突；无法无歧义回滚时保留事务证据，而不递归删除未知路径。若文件系统发布成功但数据库收尾失败，后续调用可在活跃租约结束后验证精确 intent，并原子完成 records 与 Job。空快照没有 ExportRecord，但仍创建 Job 锚点，且只能删除未改变的 predecessor 受管内容。同一 predecessor 的并发子发布只留下一个持久胜者；旧 sibling 以可重试错误失败，随后从新 head 重建。

`source.json` 采用白名单，不含 raw envelope、locator、请求 header 或来源 URL。经过脱敏的非机密 raw envelope 按设计保存在 SQLite 供重新归一化，但绝不进入导出树。layout v1 是首个实际实现的导出器，因此无需迁移旧媒体库。

执行 0054-A 新增对该受管树的只读检查，但不会把文件系统变成新的权威。服务先通过数据库 publication scope 与唯一成功 `export.emby` 前驱链 head 解析作者 UUID，再绑定严格 managed manifest。existing-only 作者锁、进程级 single-flight、逐页文件/字节/截止时间预算，以及绑定 publication Job 与 manifest SHA-256 的不透明 cursor，共同阻止修复副作用、路径披露及跨发布版本混页。响应只返回 manifest 受管逻辑相对节点，以及白名单身份、新鲜度、完整性和用户修改保护事实；宿主路径、非受管名称、原始 Job payload、locator、来源 URL 与文件字节继续保持私有。

执行 0054 阶段 B 将该本地权威扩展为从 publication 派生的 lookup target。解析器只接受作者 UUID，重新加载唯一成功的 publication-chain head，完成严格 manifest 检查，并仅在内存中派生 provider key `media-sync-{platform}-creator`、已存作者远端 ID，以及由已配置服务器 Library path 与确定性作者目录拼接而成的路径。刷新 dispatch 前会再次校验同一 publication 权威。Emby 使用一次有界、带 `Path` 及可无损表达时的 `AnyProviderIdEquals` 过滤条件的 `GET /Items`，并仍在本地校验每一返回行。Jellyfin 不发送这两个不受支持的过滤条件，而是在稳定 total/index 与聚合预算下完整分页遍历已配置 Library。两种 provider 都要求 provider value 与服务器 path 精确相等，且完整遍历必须证明零项或唯一一项；歧义或未完整遍历绝不能被当作不存在。

## 安全边界

- 执行 0055 的后端检查点把执行 0040 的匿名 REST 边界改为关闭失败的单操作者鉴权。`serve` 会在绑定前解析必需的类型化浏览器凭据及可选独立 Bearer 凭据。最外层 ASGI middleware 首先校验精确原始 Host，只开放固定 health/readiness/login/bootstrap/静态白名单，并在 handler 工作前鉴权其余全部当前或未来路由。
- 浏览器权限由唯一轮换的进程内 HttpOnly、`SameSite=Strict` Cookie 与仅存内存的 CSRF 值组成。登录与 Cookie 鉴权不安全请求要求精确配置的 Origin；CORS 与 forwarding-header 权限继续关闭。重启、退出、过期或凭据替换都会使 session 失效。Console v2 与 `/legacy` 尚未接入该 login/CSRF 契约，因此后端已受保护，但 Web 管理面当前不可操作。
- 默认进程仍绑定回环。镜像只在容器内部绑定 wildcard；示例 Compose 从仓库外挂载操作者凭据、只发布宿主机回环，并显式允许该回环 HTTP 浏览器 origin。任何非回环浏览器 origin 都必须是精确 HTTPS，位于另行审查且保留允许 Host 的代理之后。
- 凭据值优先保存在 OS keyring；无头环境可使用环境变量/文件 provider，数据库行只保存 provider/key。
- 日志构造时先脱敏，并在 sink 边界再次脱敏。
- 下载器解析并验证每次重定向，默认拒绝 loopback/私网/link-local 目标，并把路径限制在配置根目录内。
- 用户提供的作者名绝不直接成为路径；清理后的显示名会附加稳定 ID。
- 下载与导出 Job payload 保存不披露路径的 scope 哈希，而不是原始文件系统根目录。
- 携带凭据的值在进入 SQLite 与运维 sink 前被移除或脱敏；经过脱敏的非机密 raw envelope 只作为数据库重新归一化来源，绝不进入 Emby 输出。
- 0.x 将运行文件系统根目录及其祖先视为操作员控制的可信边界；不支持同权限恶意进程修改父目录的部署模型。
- 执行 0054-A 只接受一个不可变、由环境变量托管的 Emby/Jellyfin 配置。API 只暴露手工构建的安全摘要。API key 值只在最终 connector 边界解析；该值与完整 secret reference 都绝不进入 API 响应、Operation payload、SQLite 或保留日志。
- 媒体服务器流量被限制在已配置的规范 origin 与显式 IP/CIDR 策略内。每个 DNS 答案都必须被允许；实际连接会固定，同时保留原始 Host/TLS SNI；环境代理被禁用，重定向被拒绝，请求正文也不能覆盖服务器、library、路径、凭据或网络策略。
- Probe 与定向刷新是默认关闭、共用一个配置互斥域的持久 Operation。transport gate 是应用层 dispatch 线性化边界：在 gate 前胜出的取消或截止时间会阻止 POST；gate 后的超时、断连、取消或传输歧义统一成为不可重试的 `media_server_scan_acceptance_unknown`。旧有 `{}` 扫描仍只证明接受。阶段 B 的作者观察要求完整的“不存在”基线、一次已接受 POST，以及在两次有间隔的完整 lookup 中出现同一唯一精确项目。其 `accepted` 与 `observed` 运行中 checkpoint 以 lease/revision fencing 写入既有 `result_summary` 并复用 `operation_phase_changed`；后续完成状态不明时仍保留接受证据。accepted 不等于 observed，observed 也不等于 provider task completion 或 playback evidence。

## 部署与演进

执行 0006 的有界本地 scheduler/worker CLI 继续保留在单机 SQLite 控制面上。执行 0012 另行交付显式前台 `scheduler supervise` 进程；每个公平 cycle 依次执行已过期登录协调、有界调度物化、有界订阅工作和有界 `pipeline.subscription` 工作。第一次停止请求会阻止之后的 tick/claim，取消并 join 进行中的订阅工作，并在 heartbeat 下精确等待一项已经 active 的线程型 pipeline 尝试。重复 task cancellation 不得遗留任一 join；重复 OS 信号会明确强制退出，由持久租约/fencing 负责恢复。多个本地进程仍可通过 writer 串行化、精确租约和持久 lane 安全竞争。

执行 0012 的仅登录协议使用相互独立的有界请求/结果长度 frame，并持续保留 START/CANCEL/EOF 父进程控制。父侧收容在 START 前附加，child 自持收容与控制 watcher 在导入上游前建立。结果发布后，guardian 会继续持有后代所有权及继承账户锁，直到父进程开始完整树关停；因此父进程被硬杀时，会先关闭所属 Windows Job 或 POSIX 进程组，另一次登录才可能获取该账户锁。持久恢复使用独立的截止时间权威：只有精确过期的 `pending|waiting_user` 二维码会话，在 Account 仍为 `qr/authenticating`、持有同一账户锁且通过仓储 CAS 时，才能原子切换为 `expired` 与 `qr/required`。PID 与仅凭锁可获取都不是恢复权威。

监督器仍是本地前台进程，Docker 打包（执行 0041）通过可选 compose profile 运行它而非安装为服务。执行 0054-B 目前只有 Operation checkpoint/cancel/final 行锁竞态的真实 PostgreSQL 证据；分布式 HA、完整 schema 的 PostgreSQL 支持与生产部署、公网部署及 Web login/CSRF 集成仍属后续工作。执行 0055 后端鉴权检查点不能替代操作者侧的真人部署门（执行 0047）。原生平台适配器可逐步替换受限桥接；经过脱敏的 raw envelope 允许在上游或模型升级后重新归一化。

执行 0054 阶段 B 将资格 schema 升级到 v2，同时继续把本地自动化证据、实现状态和真人资格保持为相互独立的事实。`connection_probe`、`library_discovery`、`targeted_scan_acceptance`、`item_lookup` 与 `post_refresh_item_observation` 为 `IMPLEMENTED`，但在获授权真实服务器上执行前，真人状态仍为 `NOT_RUN`；mock 或本地证据不能授予真人 PASS。`provider_task_completion` 为 `NOT_IMPLEMENTED`，reason 是 `provider_api_unsupported`；`playback_evidence` 与 `automatic_post_export_scan` 也继续为 `NOT_IMPLEMENTED`。阶段 B 复用既有 author target、author/Job subject、`result_summary` 与 `operation_phase_changed` 词汇，因此没有新增 migration，Alembic 仍停留在 `0007_media_server_operations`。后端访问边界现已实现；其 Web 客户端集成、经鉴权播放证据写入、浏览器可写设置、多配置及保留/破坏性维护继续属于执行 0055；导出后自动扫描尚无已冻结的后续归属。
