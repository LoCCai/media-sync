[English](progress.md) | **中文**

# 执行 0055 阶段 A 进展

- 状态：后端鉴权、观察身份／持久账本及仅浏览器确认均已发布；有界作者证据投影与资格 v3 已实现并完成完整回归，正在收尾发布
- 日期：2026-09-05
- 规划基线：`d0a8cc2`；鉴权实现基线：`4564b2a`
- 已发布鉴权提交：`f19bfaa`
- 已发布持久化提交：`1d5b448`
- 已发布确认提交：`13de3b7`；投影冻结规划提交：`9fd74de`
- 当前 revision：`0008_playback_evidence`

## 已完成检查点

1. 中英双语规划基线已提交为 `4564b2a`；实现收尾前再次 fetch `origin/main`。原始产品目标保持不变：七平台登录/订阅/抓取及 Emby/Jellyfin 兼容输出。
2. 已增加有界操作者设置：一个必需的类型化浏览器凭据引用、一个可选且独立的 Bearer 引用、精确浏览器 origin，以及 60 秒至八小时 session TTL。解析失败只返回固定启动码，不暴露 secret 值或 locator。
3. 已增加线程安全的进程内权威：常量时间比较、单个轮转不透明 session、仅内存 CSRF、确定性全局有界失败限流、固定审计码以及 logout/expiry/restart 语义；凭据轮转完成后，旧凭据并发登录不能留下有效 session。
4. 已安装最外层纯 ASGI 边界：最先检查精确 Host，只放行精确匿名 method/path 表与实际存在的普通 immutable 文件，按浏览器优先/Bearer 次之鉴权，对使用 cookie 的不安全请求要求精确 Origin + CSRF，对仅浏览器路由拒绝 Bearer，并清空所有 downstream HEAD body frame。
5. 已增加严格 login/session/logout endpoint。Login 只接受一个有界 UTF-8 JSON 对象，拒绝重复成员、非有限值、多余字段、深层递归输入、重复/非法 header 与超大 body；OpenAPI 输入契约保持显式且为 write-only。HEAD 路由使用独立、无重复 operation ID 的 schema 安全 handler。
6. `media-sync serve` 现会在 app/数据库构造或 socket bind 前解析并验证完整边界，关闭 proxy-header 信任与 access log。容器 wildcard bind 可显式发布 loopback HTTP 浏览器 origin；所有非 loopback HTTP origin 继续被拒，因此非回环浏览器访问必须使用 HTTPS。
7. Compose 样例现通过 Compose secret 挂载专用操作者凭据并声明精确宿主回环 origin；镜像 health endpoint 继续匿名。`.env` 样例已记录必需凭据引用、可选独立 Bearer 引用、origin 规则与 TTL。
8. 七个既有 API 模块已全部迁移到真实 login/session 流程。共享客户端只为不安全方法注入 Origin/CSRF，因此 QR、archive GET/HEAD/Range 与 SSE 覆盖走的是浏览器实际可用的同源 cookie 路径，不再夹带无法设置的自定义 header。
9. 已关闭凭据轮转线性化、容器回环 origin、递归 JSON、原始 ASGI HEAD body/长度、login OpenAPI 输入缺失、重复 operation ID 及 cookie-only 测试假阳性等审查问题。当前 auth/config/七个 API 联合专项为 190 项通过，只有一个既有 Starlette/httpx 弃用 warning。
10. 已完成本机可用的全部后端切片门：完整 Python 套件通过 2811 项、跳过 14 项并有一个既有 warning；Web 通过 69 项及 format/check/build；全仓 Ruff/format、104 个源文件 strict mypy、compileall、498 份文档链接、两个锁定上游及 wheel/sdist 构建/内容检查均通过。3 项 Python skip 为 Windows/POSIX 差异；另 11 项真实 PostgreSQL 竞态与 Docker/Compose 执行在本工作站不可用，因此不作通过声明。
11. 关闭失败的单操作者后端边界已提交并推送为 `f19bfaa`。上述 2811 项完整 Python 结果及配套质量/打包证据继续作为该鉴权提交的历史发布门；它们不替代下方单独记录的当前工作树结果。
12. 已增加只为 matched 结果生成且带域分隔的 observation fingerprint。完整 `not_found` 结果不携带 item 或 observation fingerprint；唯一 `matched` 结果把规范 author ID 与 profile、publication、selector、item digest 绑定，且不保留远端原始 item ID。Web `MediaServerAuthorLookup` discriminated type 也已同步该契约：`matched` 必须带 `observation_fingerprint`，`not_found` 则禁止；这只是类型层准备，不代表 confirmation 交互已经实现。
13. 已增加 `PlaybackEvidence` 模型与 revision `0008_playback_evidence`。Append-only 账本强制 schema version 1、规范 UUID、小写 SHA-256 digest、有序的 aware timestamp、唯一 observation identity、author/time 查询索引，以及指向 Author 与 publication Job 的 `RESTRICT` 引用。Downgrade 拒绝 offline SQL 生成，也拒绝丢弃任何含证据行的表；只有经审计确认的空表可被移除。
14. 已增加专用 create-or-replay repository。自然重放比较不可变 evidence identity，但返回首个持久行及其时间戳；同一 observation fingerprint 若搭配不同不可变身份，则以固定冲突码失败。SQLite 在自然键读取前通过 `BEGIN IMMEDIATE` 预留 writer，使用 savepoint 且不接管调用方 commit，并拒绝不安全的既有 deferred transaction。PostgreSQL 依赖 unique constraint，在竞争者失败后只回滚 savepoint，并按 `READ COMMITTED` 语义重新读取胜出行。
15. 当前 commit-3 专项并集为 129 项通过、8 项跳过、1 个既有 warning；其中 migration/repository 子集为 42 项通过、8 项跳过。完整 Python 回归在 558.19 秒（`0:09:18`）内通过 2868 项、跳过 22 项，并有 1 个既有 Starlette/httpx warning：3 项 skip 为 Windows/POSIX 差异，11 项为既有 Operation PostgreSQL 用例，8 项为新增 PlaybackEvidence PostgreSQL 竞态。两组 PostgreSQL 用例均因未设置 `MEDIA_SYNC_TEST_POSTGRESQL_URL` 而跳过，因此真实 PostgreSQL 明确仍为 `NOT_RUN`。
16. 当前 Web format、7 个文件/69 项测试、Svelte check（0 error/0 warning）与 production build 均通过。全仓 Ruff check 通过；修正 1 个纯格式差异后，Ruff format 对 727 个文件通过；strict mypy 对 105 个源文件通过；compileall 通过。这些 Web 门只验证当前 discriminated response type 与既有控制台，不声明尚缺的 Web 登录或 confirmation 交互已经实现。
17. 在系统临时目录隔离运行 `uv build`，精确生成 1 个 wheel 与 1 个 sdist。Wheel 共 123 项，sdist 共 837 项；两者均包含 `playback_evidence_repository.py` 与 `0008_playback_evidence.py`，也均不包含 `.env` 或 SQLite 输出。
18. Observation identity/持久账本检查点经审查后已提交并推送为 `1d5b448`。最终 fetch 确认 `HEAD...origin/main` 分叉为 `0 0`；全部 tracked 变更均已发布，只剩既有未跟踪 `.mimosa/` 继续排除。
19. 已实现 `PlaybackEvidenceService.confirm`，严格校验规范 UUID/摘要，并使用一个最长 120 秒的绝对 deadline。有界 authority lock 覆盖 target resolve A、一次完整唯一 lookup、target resolve B、精确 target 比较、不可变 profile 重读，以及 lookup/request observation 身份的常量时间比较。所有外部检查及 deadline fence 完成后先释放该锁，才打开短 create-or-replay 数据库事务。
20. 已新增只允许浏览器 session 的 `POST /api/v1/media-server/playback-evidence`。必须同时具备精确 Cookie session、Origin 与 CSRF；Bearer-only 及 Cookie 搭配任意 Authorization header 都由最外层 middleware 在 handler/读取 body 前拒绝。端点只接受唯一 `application/json` header 与不超过 1 KiB、精确包含规范 `author_id` 和小写 `observation_fingerprint` 的 JSON；重复 member、非有限值、非法 UTF-8、额外字段与任何 `Idempotency-Key` 均被拒绝。Create/replay 都返回 201，且只含 schema version、evidence ID、author ID、observed/confirmed 时间与 replay 状态。
21. 成功审计只在数据库 context 提交后发送。身份冲突、存储、确认及输入失败都收敛为固定且不反射输入的错误码；响应绝不返回 observation fingerprint、publication Job、context digest、raw selector、远端 item ID 或路径。路由清单从 57 增至 58，匿名 allowlist 没有扩大。
22. 专项证据全部通过：18 项 service 单元测试、2 项 SQLite 组合测试、51 项 endpoint 测试、108 项 service/API/auth 并集、47 项 media-server API 回归，以及覆盖 API/auth/observation/persistence 的 289 项并集（8 项 PostgreSQL 预期跳过）。Service/transaction 与 API/auth 只读审查均未发现 P0/P1/P2；后续最终发布审查发现并关闭了下文单独记录的默认运行时审计可见性 P2。
23. 当前 Web format、7 文件/69 项回归、Svelte check 与 production build 通过；Ruff/format 覆盖 731 个文件，strict mypy 覆盖 106 个源文件，compileall 通过，498 份文档链接及两个干净锁定上游通过。严格 package 扫描发现 Hatch 会把未跟踪的本地 `.mimosa/` 历史收入 sdist，因此该目录现已在 Git 与 Docker context 中显式忽略；重建的 124 项 wheel 与 810 项 sdist 均包含新 service/repository/revision，且没有运行时/工具历史根目录。Docker 不可用且未设置 `MEDIA_SYNC_TEST_POSTGRESQL_URL`，所以对应可执行门继续为 `NOT_RUN`。
24. 首轮完整套件发现了一个进程顺序相关的日志副作用：Alembic 的 INI 日志配置会禁用已创建的应用审计 logger，而已提交 service 结果本身仍正确。第一版缓解已通过完整套件，但独立复审发现仍会改变 root level，因此后续运行在约 7% 处主动中止，并把实现收紧为只在 standalone Alembic CLI 执行时应用 INI logging。Subprocess“migration 后审计”回归现会保留调用方 root handler 与继承 INFO logging；该发布候选完整套件在 588.32 秒（`0:09:48`）内通过 2940 项、跳过 22 项，并保留 1 个既有 warning。本检查点有意拆分冻结 commit boundary 4，以缩小确认写入路径的安全审查面；规划中的 projection 与 qualification 范围不变。
25. 最终发布审查发现默认 `serve` 日志仍会让 `media_sync.*` INFO 审计低于 root 的有效阈值。`serve` 现会深复制 Uvicorn 配置，按已校验日志级别增加一个不向上传播的应用 stderr handler，保留 Uvicorn 默认配置并继续关闭 access log。无 socket subprocess 证明固定 playback 与 operator-auth 审计均可见，且不反射私有 sentinel。修复后的最终完整套件在 594.72 秒（`0:09:54`）内通过 2941 项、按预期跳过 22 项，并保留 1 个既有 warning。该结果是 `13de3b7` 的历史发布证据；当时确认写入审查范围内没有遗留 P0/P1/P2，不代表后续交付核查中的 Web、凭据可读性或迁移前预检问题已经解决。

26. 当前投影检查点已按冻结规划 `9fd74de` 增加 `GET /api/v1/media-server/playback-evidence/by-author/{author_id}` 与可选显式作者范围的资格 schema v3。GET 接受既有 Cookie/Bearer 读取鉴权，严格校验规范作者 UUID 及唯一允许的 query；默认历史 20 行、最多 50 行，精确当前行独立查询，总物化账本行不超过 `limit + 2`，不 COUNT、不写入。
27. 新读取 service 在一个最长 120 秒的绝对 deadline 内完成 resolve A → profile A → 一次完整 lookup → resolve B → profile B；target/profile 必须稳定且重新计算身份一致。全部远端／文件系统工作及 authority lock 结束后才打开短读取事务。远端不确定时当前 unavailable、历史 unknown；完整不存在时历史 stale。远端 lookup 截断不能 PASS；历史页截断独立报告，不否定已独立重验的精确当前持久行。
28. 资格 v3 未指定作者时为 `not_requested`，不查询账本或远端；指定作者时只有完整稳定权威与不可变字段精确匹配的持久确认可产生该作者范围 PASS。安全投影只暴露 ID、作者、时间与状态，不暴露 digest、Job、路径、provider 值或远端 item ID；路由清单现为 59。Provider completion 与自动扫描继续未实现，全部仓库真人行仍为 NOT_RUN。
29. 当前投影专项并集通过 220 项、1 个既有 warning（51.09 秒）；完整 Python 套件通过 2999 项、跳过 22 项、1 个既有 warning（613.66 秒）。Web 7 文件／69 项及 format/check/build、107 个源文件 strict mypy 与 743 文件 format 通过。详细命令及最终文档／包／Git 门见[投影验证](evidence-projection/verification.zh.md)；不能用这些离线结果替代当前镜像或真人执行。
30. 按用户交付核查补充[优先级计划](delivery-priorities.zh.md)：本增量收尾后，先完成安全 login/session/CSRF 与凭据／迁移前预检，再验证当前 Linux 镜像并推进 Bilibili／小红书获授权真人金丝雀。最小证据 UI 属于后续已承诺工作，但不阻塞可通过既有 CLI 开始的获授权真人流程。

## 播放证据实现前澄清

1. 自然重放只比较不可变身份字段：schema version、author/job 身份、四个 context digest 与 observation fingerprint。新请求的 `observed_at`/`confirmed_at` 不要求等于胜出行；重放始终返回首个持久行及其时间戳。
2. 本阶段的 “append-only” 由 application、API 与 repository 强制，不宣称数据库 role/trigger 级不可变。
3. Item fingerprint 证明的是 resolved profile/publication/selector 上下文中的一个规范远端 item 身份；它不证明媒体字节完整、持续播放，亦不证明远端 item 此后仍 current。
4. Qualification schema v3 的单作者范围、行数／deadline 上限、current authority 来源及失败／截断语义已在[投影计划](evidence-projection/plan.zh.md)中冻结并实现。远端 lookup 截断阻止权威成立及 PASS；历史页截断不否定独立验证的精确当前行。PostgreSQL 证据仅覆盖 Author/Job/PlaybackEvidence 元数据与 repository 竞态，不宣称完整应用已支持 PostgreSQL 部署。

## 仍待实现

- 打包的 Svelte 控制台与 `/legacy` 尚无登录壳、内存 CSRF store、集中 401 reset 或 logout/expiry 生命周期。因此后端边界已经实现，但当前 Web 控制面尚不能完成经鉴权写操作。
- 仍须完成最小当前／历史证据展示与 matched-only 确认交互。投影与资格 v3 后端已实现，无指定作者或无精确当前证据时为 `IMPLEMENTED/NOT_RUN`；这不代表真人资格已经通过。
- 尚未运行任何获授权真人操作者凭据、平台账户或真实 Emby/Jellyfin 播放流程。本地账本行、mock connector 或 endpoint 测试都不能授予真人 PASS；真人播放仍为 `NOT_RUN`。

## 下一检查点

按[交付优先级补充计划](delivery-priorities.zh.md)，先收尾发布已验证投影，再实现安全可用的 Web login/session/CSRF、401／过期重置、登出与凭据／迁移前预检，随后验证当前 Linux 镜像并推进获授权 Bilibili／小红书金丝雀。最小证据 UI 不阻塞既有 CLI 真人运行。具备 Linux/Docker/PostgreSQL 的主机仍须执行当前 Compose 启动、8 项 PlaybackEvidence PostgreSQL 竞态及此前跳过的 PostgreSQL 覆盖；旧镜像 PASS 不替代当前版本。

既有 `.mimosa/` 目录保持未跟踪，现已显式忽略，并同时从 Git、distribution 与 Docker build context 排除。
