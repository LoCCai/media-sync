[English](plan.md) | **中文**

# 执行 0007 计划

- 状态：已计划 — 实现前冻结
- 计划日期：2026-08-30
- 前置执行：Execution 0006 implementation commit `674e510`
- 网络策略：仅离线夹具与本地辅助进程

## 2026-08-30 修订

下方冻结设计继续保留为原始计划记录。安全复核把失败 attempt 清理细化为四种显式结果：`ABSENT`、`REMOVED`、`QUARANTINED` 与 `UNRESOLVED`。`QUARANTINED` 表示精确 attempt 已原子移动到忽略的 `.quarantine` 下，但无法完成清理；它是固定的终态安全结果，不是“整树清理成功”。`UNRESOLVED` 表示既不能证明删除，也不能证明隔离；后续解析密钥、关联 run、准备 bridge 或启动进程前，必须先写入持久脱敏 account block 并执行硬 fencing。最终整树零匹配门禁只能覆盖安全产物，并必须显式排除 quarantine-retention 与 unresolved-retention 负向测试。本修订不降低任何进程、数据库或运维输出安全要求，也不授权暴露留存路径。

## 冻结设计

### 信任与授权

- scheduler worker/父进程独占数据库 URL、worker 身份、lease token 与续租权限。MediaCrawler 子进程不得获得这些信息，也不能续租或收尾 Job；它只能接收受限 manifest、既有有界私有输入通道及单向 liveness/cancel 控制。
- 许可证确认是显式且默认关闭的运维授权。全历史确认、headless 行为与爬取延迟属于显式订阅策略，不得从平台、账户状态或以往交互运行中推断。

### 策略与产物协议

- 冻结 MediaCrawler 订阅策略 v1：封闭字段为 `schema_version`、可选 `creator_input.secret_ref`、`allow_full_history`、有界正数 `request_delay_seconds` 与 `headless`。只有不透明 secret reference 可以持久化；原始 Cookie 与签名作者输入只存在于内存。
- Manifest v3 分离持久 scheduler Job 身份与 attempt-scoped execution 身份，并绑定 schedule revision、attempt、SyncRun、checkpoint、forward 模式、上游/许可证身份、登录与作者指纹、条数/watchdog 策略及延迟。完成回执 v2 会认证对应 v3 身份与精确输出快照。
- 既有已密封 manifest-v2/receipt-v1 证据保持严格双读与字节精确，绝不重写，也不会被提升为 scheduler 所有权；新的定时 attempt 只写 v3/v2。

### Attempt 身份与产物生命周期

- 每次 scheduler 重试都使用由 scheduler Job 与 attempt/execution 身份派生的唯一受限根目录；重试绝不复用或递归覆盖前序根目录。
- 失败、未密封、已取消及租约丢失的 attempt-owned 产物会在进程树停止后安全清理。恢复只在验证所有权及精确 manifest/receipt 身份后使用已密封产物，绝不跟随链接或删除后继根目录。
- 私有账户 browser profile 有意持久存在且可能携带凭据；它与 attempt 清理隔离，不纳入虚假的整树零密钥声明，也不会出现在 scheduler 运维输出中。

### 进程监督

- 桥接准备、checkout/runtime 探测、secret-provider 读取、子进程等待、回执验证与归一化全部移出事件循环。scheduler heartbeat 仍由父进程拥有，并使用独立短数据库事务。
- 取消使用同步 runner 可识别的显式信号。handler 会 shield 并 join runner 收尾，只有确认子/孙进程终止、attempt 清理及账户锁释放后才返回。
- 父进程死亡处理使用单向 liveness/control channel，并保证子进程树仍使用 profile 时账户锁不会提前结束。POSIX orphan 与 Windows 启动到 Job/control handshake 均属于实现验收边界，而非生产假设。
- 子进程绝不获得 scheduler lease。父进程 heartbeat 丢失时，由可信父进程/control 边界取消子进程；不可信 child 不能维持 lease。

### 应用与数据库 fencing

- 把 MediaCrawler 校验、不可变快照归一化、SyncRun 生命周期及导入编排从 CLI 提取为可复用应用服务；手工 v2 导入委托同一校验核心，但不会获得 scheduler 所有权。
- 每次 SyncRun 创建/attach/状态变更及每个内容/checkpoint 批次前，同一数据库 session 都会取得 SQLite writer slot，并校验精确 Job、worker、token、running 状态与未过期 lease；该事务内不存在外部等待。
- cancel/reclaim 会以固定代码终态化或解除当前关联的非终态 SyncRun。旧 owner 可以保留所有权丢失前已提交的批次，但之后不得再提交批次、receipt publication 或 Job 结果。
- 定时执行仅支持 forward。既有 checkpoint 恢复可以从较旧密封爬取补齐缺失记录，但不能发布 continuation，也不能回退更新的 cursor/watermark。

### 状态、延迟与运维契约

- 冻结 `goal.md` 中的进程到 scheduler 映射。认证与真人交互结果在显式 resume 前停留于 `waiting_auth`/`waiting_user`；原始进程输出与异常文本绝不用于选择持久代码。
- 忠实 pinned-shape 夹具覆盖上游 `parse_cmd()` 与配置顺序。`request_delay_seconds` 只映射到 `config.CRAWLER_MAX_SLEEP_SEC`，同时设置 `MAX_CONCURRENCY_NUM=1`；这不是逐请求 limiter，也不保证七平台分页有界。
- scheduler CLI 接入必须显式启用且默认关闭；账户/订阅/Job 投影继续省略策略 payload、secret reference、租约材料、locator 与文件系统根目录。

### 迁移与兼容性决定

- 初始计划不新增数据库 schema 迁移。既有 `Subscription.policy`、`SyncRun.attempt`、`SyncRun.manifest`、`Job.run_id` 及 schedule payload revision 已能表达所需状态；实现只新增 exact-owner 仓储操作，并把既有 schedule revision 暴露给 handler context。
- 不创建空 Alembic revision。若实现证明无法安全表达关系型 attempt lineage，必须先停止并修订本冻结计划，再新增真实迁移及 current/source/wheel upgrade 与 downgrade 保留测试。
- 产物协议迁移是必需项：新增 v3/v2 writer，同时保留严格 v2/v1 reader；旧文件因回执哈希绑定精确字节而绝不修改。

## 实现顺序

1. 新增封闭 policy v1、manifest-v3/receipt-v2 类型、精确边界、legacy 双读及畸形/未知字段测试。
2. 新增忠实锁定上游形状夹具，在不调用真实爬虫的前提下证明七平台配置、Cookie 不泄漏、延迟绑定及二进制下载关闭。
3. 引入 attempt-scoped 路径与安全受管产物清理；保留密封 legacy 证据并阻止跨 attempt 删除。
4. 把 runner 重构为可取消监督边界，确认整树终止、父死亡 liveness、账户锁生命周期及 Windows 启动 fencing。
5. 提取 MediaCrawler 应用编排，并为 SyncRun 及每个导入/checkpoint 事务加入同 session ownership guard。
6. 新增 MediaCrawler scheduler handler、保守状态映射、显式等待恢复及 registry/CLI 启用。
7. 新增七平台离线、重试/重启、崩溃恢复、取消/ABA 与密钥落点验收，不加入自动下载/导出规划。
8. 关闭全部 P0/P1，运行准确最终门禁，更新四份执行文档并创建一个中英双语本地实现提交；绝不推送。

## 必需离线测试

- 策略/manifest/receipt 边界、未知字段、身份不匹配、v2/v1 不可变恢复及 v3/v2 严格写入。
- 同一 scheduler Job 的 attempt 1/2、不同根目录、旧根 fencing、密封输出恢复及不删除后继。
- 长 fake child heartbeat，并由独立 SQLite writer 证明进程等待不持有数据库事务。
- spawn 前、运行中、child 退出后/seal 前、seal 后/导入前及导入批次间取消。
- lease 丢失、独立 cancel、ABA reclaim 与 heartbeat 失败，证明整树 join 及所有权丢失后零写入。
- 在支持的 POSIX 与 Windows 路径硬杀 helper process，覆盖子/孙进程退出、profile lock 排他及有界恢复。
- 已知密钥回显、非零退出、timeout、各输出上限、畸形回执及不安全树清理，并对返回 attempt 根与 SQLite/运维落点执行字节扫描。
- 七平台标识只使用假进程结果与版本化 JSONL 夹具；不启动浏览器、不访问平台端点、不使用真实凭据/CDN/Emby 服务器。
- 全量分支感知套件、协议/监督/ownership/重启/哨兵专项、构建、随包资源、文档、锁定上游、补丁及忽略运行根检查。

## 回退与安全

- 自动测试只允许启动仓库自有且不执行网络/浏览器工作的辅助进程；硬杀测试只针对精确临时 helper PID/进程树，并在终止前校验目标。
- 测试不解析真实 secret reference；生成的哨兵只存在于临时忽略根，并且不得出现在保留的安全产物中。
- 不修改或内嵌上游源码；精确锁定 checkout 只读检查，许可证边界保持不变。
- 本计划不授权 Git push、真人平台请求、CDN 获取或 Emby/Jellyfin 操作。

## 明确延期

- 定时 backfill、自动 sync → download → export 规划、签名 locator refresh 与真实二进制获取。
- 安全 `waiting_user` 之外的二维码/challenge 展示 UX，以及真人登录与作者扫描验收。
- 逐请求 HTTP 节流、代理池、验证码/平台保护绕过及修改上游源码。
- REST、常驻生产守护、Docker/生产打包、公网部署及分布式 HA/PostgreSQL。
