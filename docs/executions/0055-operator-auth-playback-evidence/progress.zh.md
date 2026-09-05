[English](progress.md) | **中文**

# 执行 0055 阶段 A 进展

- 状态：后端鉴权已发布；播放观察身份/持久账本检查点已在本地实现；Python、Web、代码质量与 distribution 门通过
- 日期：2026-09-05
- 规划基线：`d0a8cc2`；鉴权实现基线：`4564b2a`
- 已发布鉴权提交：`f19bfaa`
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

## 播放证据实现前澄清

1. 自然重放只比较不可变身份字段：schema version、author/job 身份、四个 context digest 与 observation fingerprint。新请求的 `observed_at`/`confirmed_at` 不要求等于胜出行；重放始终返回首个持久行及其时间戳。
2. 本阶段的 “append-only” 由 application、API 与 repository 强制，不宣称数据库 role/trigger 级不可变。
3. Item fingerprint 证明的是 resolved profile/publication/selector 上下文中的一个规范远端 item 身份；它不证明媒体字节完整、持续播放，亦不证明远端 item 此后仍 current。
4. Qualification schema v3 实现前必须冻结 author 聚合范围、行数/deadline 上限、current authority 来源以及 lookup 失败/截断语义。PostgreSQL 证据仅覆盖 Author/Job/PlaybackEvidence 元数据与 repository 竞态，不宣称完整应用已支持 PostgreSQL 部署。

## 仍待实现

- 打包的 Svelte 控制台与 `/legacy` 尚无登录壳、内存 CSRF store、集中 401 reset 或 logout/expiry 生命周期。因此后端边界已经实现，但当前 Web 控制面尚不能完成经鉴权写操作。
- 持久化原语尚未接入经鉴权的 confirmation service 或 API。Resolve → unique lookup → resolve 的 TOCTOU 边界、qualification schema v3 与只允许 matched 的 Web 确认交互仍未实现。
- 尚未运行任何获授权真人操作者凭据、平台账户或真实 Emby/Jellyfin 播放流程。端到端播放证据能力仍为 `NOT_IMPLEMENTED`，真人播放仍为 `NOT_RUN`。

## 下一检查点

完成已审查 observation identity/持久账本提交的最终 Git 发布门；随后实现带必需双重 resolve 与失败零写入的经鉴权 confirmation service/API。当前 docs、锁定上游、质量、distribution、生成物、敏感数据、冻结计划与分叉检查均已在本地通过。Qualification schema v3 与 Web 登录/确认生命周期作为后续独立检查点推进。具备 Linux/Docker/PostgreSQL 的主机仍须执行已记录的 Compose 启动、8 项 PlaybackEvidence PostgreSQL 竞态门，以及此前跳过的 PostgreSQL 覆盖。

既有 `.mimosa/` 目录保持未跟踪并排除。
