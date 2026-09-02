[English](progress.md) | **中文**

# 执行 0009 推进结果

- 状态：功能优先 MVP 已在本地实现
- 开始时间：2026-08-30 20:38 +08:00
- 暂停时间：2026-08-31 00:06 +08:00
- 恢复时间：2026-08-31 00:39 +08:00
- 实现：MVP 完成，强化后置
- 验证：离线专项门禁通过
- 前置执行：Execution 0008 implementation commit `3889539`

## 计划基线

- 执行 0008 只关闭离线取消/安全证据；签名 locator refresh、成功/恢复终态清理与真实 CDN 流量仍不在其实现内。
- 只读数据流复核证明稳定 `adapter_refresh.asset_key` 单向不可逆，Asset/Content 也没有 Subscription/Account provenance；同一作者可有多个账户订阅，因此选择第一个账户不安全。
- 冻结设计新增多对多 `asset_refresh_sources`；资格使用 semantic/locator fingerprint，generation 只作为下载 fence，避免本地归档 reset 破坏有效来源。
- 设计审计发现 locator-only 替换此前停留在同一 generation，与不可变 Job 来源绑定冲突；冻结修复要求持久 semantic 或 locator 任一替换都推进 generation，而单纯归档 reset 后匹配 provenance 继续 eligible。
- XHS refresh authority 必须来自精确 Subscription 的 creator secret，严格验证作者/token/source，并受 4 x 30/120 秒边界约束；私有结果通道使用与 stdout/stderr 不同的专用 OS pipe/handle，后两者在 import 上游前即重定向。
- 只读 handler 复核发现四个成功后缺口：fresh success 保留根、recovered success 丢失来源路径、already-succeeded restart 在清理前返回，且真实提交后的 result/readback 错误仍可能把 succeeded Run 改成失败；恢复 metadata 与并发清理还需要更强身份/竞态检查。
- 锁定上游复核确认各平台在 store/JSONL 前都有内存 detail 入口；当前已归一化 Asset 只包含 XHS image/video、抖音 image/video/audio/cover、快手 video/cover 与 Bilibili cover；微博/贴吧/知乎没有 Asset。
- 在计划基线时尚未运行实现；之后本地工作树只落盘了两个部分切片，仍未运行 helper 进程、浏览器、平台账户、CDN 请求、媒体服务器操作或执行 0010。

## 暂停检查点

用户要求在执行 0009 验收前暂停。以下代码将作为未完成工作保存在一个本地 WIP 提交中，不代表能力已交付；手工签名 locator 路径仍不可用，CLI 仍返回 `locator_refresh_unsupported`。

### 已落盘的部分代码

- 新增 `AssetRefreshSource` ORM 关系、复合身份、约束与索引，以及包含保守唯一 legacy 来源回填和 downgrade 的 `0005_asset_refresh_sources` migration。
- 新增 observation upsert、单调 `(created_at, id)` run 审计顺序及 eligible 来源查询；semantic 或持久 locator 替换会推进 generation 并重置下载状态，单纯 generation archive reset 不改写来源。
- 新增精确 recovered `source_paths`；fresh、recovered 与 already-succeeded 路径现会尝试终态清理。封闭 metadata 校验以确定性 `uuid5` 绑定 attempt/execution/run 身份，并保护成功提交后的数据库事实不被矛盾失败变更覆盖；`UNRESOLVED` 继续作为硬 fence。

### 待实现

- 精确 0/1/N 与既有 Job 绑定来源选择；`run_id = NULL` 的不可变 Job 来源。
- 共用账户锁、文件系统 block 二次检查及密钥解析/claim/spawn 前的 TOCTOU barrier。
- 私有 refresh 协议、专用 pipe/handle、detail child 与 runner；四个平台 selector；微博/贴吧/知乎固定不 spawn 路径。
- 有上下文 refresh 与精确一次 401/403 重解析；CLI 启用、许可证及订阅参数接线。
- 功能性 refresh/download CLI、平台 detail 选择及自动工作流集成。
- 完整强化矩阵、授权真人行与留存哨兵明确后置到功能路径完成之后；执行 0010 自动 DAG 仍未开始。

## 恢复后的实现批次

- 将 `0005_asset_refresh_sources` 提升为 CLI/包当前 head，并新增 schema 约束、外键、索引及保守 0/1/N legacy 回填的往返覆盖。
- 在 checkpoint 发布前把精确 Asset/Subscription observation 接入同一导入事务；错误 run/关系回滚整批，并覆盖重放顺序、多账户替换及 archive reset 资格。
- 收口 fresh、recovered 与 already-succeeded 清理行为，保留已提交成功事实，并让精确根的并发消失安全收敛。
- 合并验证：Ruff 通过、65 个源码文件严格 mypy 通过，migration/ingestion/handler/supervision 专项共 `87 passed, 1 skipped`。
- adapter-refresh HTTP 401/403 后自动重新解析一次；第二次认证失败返回固定可重试 `locator_refresh_auth_expired`，direct locator 绝不触发 refresh。

## 功能优先交付已完成

### 已实现

- 新增 detail runner：校验锁定 checkout 与显式 Python，复用精确账户 profile，有界运行 detail 模式，内存返回 content JSONL，并只删除 UUID attempt 根。
- 新增刷新上下文与 refresher：重算稳定 Asset 身份、复用正常导入 normalizer，并按 content/type/id、kind、position 与无 query 来源提示精确选一。
- 新增惰性 refresher：仅在下载器确需 locator 时选择精确当前来源、Subscription 与 Account；Cookie 密钥保持瞬态。
- 接通资产下载显式开关与可选订阅选择；小红书另支持详情链接密钥引用；缺少 runtime/许可证/XHS 详情权限时在下载编排前拦截。
- 新增来源缺失、歧义、不匹配及凭据不可用固定错误；可由操作员修正的来源错误保持可重试。
- 离线 fake child、normalizer 选择、清理与下载器续签回归通过；未运行真人平台、CDN、凭据或媒体服务器流量。

### 待实现

- 执行 0010 的自动协调器与 worker。
- 自动从小红书作者 feed 获取新的 note 专用 `xsec` 详情链接；MVP 使用操作员一次性密钥引用。
- 真人 Cookie/保存会话/QR、真实 CDN 下载与真实 Emby/Jellyfin 扫描验收。
- 完整强化、留存哨兵、全套测试、构建/wheel 与公网部署矩阵。

## 必须关闭的入口缺口

| 缺口 | 计划关闭方式 | 状态 |
| --- | --- | --- |
| 无精确刷新来源 | 新表、保守 backfill 与同事务 observation | schema、回填、repository 与导入已接通 |
| 无上下文 refresh port | 冻结上下文及 stable-key/fingerprint 复核 | `PASS (offline focused)` |
| 无私有 detail 协议 | 受监督 detail-only child 与单条有界不转发帧 | `PASS (offline fake child)` |
| 短效认证 URL | adapter 专用一次重解析及只持久 locator 的 partial 身份 | resolver 与 CLI 已接通 |
| 成功后事实与根 | 精确三路径清理；result/readback/cleanup/cancel 错误下保留已提交事实；竞态安全四状态 | handler 与并发清理回归通过 |
| 签名数据落点风险 | 注入/transport 证明与 fail-closed 多落点扫描 | `NOT_RUN` |
| 配置与 block 竞态 | 共用账户锁；SQLite 外二次检查 block 后再解析密钥/claim/spawn；事务复核 DB 身份；block writer 共用 fence | `NOT_RUN` |

## 计划实现顺序

1. 终态清理红测与最小竞态/身份修复。
2. Migration、ORM/repository 来源及保守 backfill。
3. 同事务导入 observation 与精确 selector/Job 绑定。
4. 有上下文 refresh port、受监督私有 child 及固定错误。
5. 四个平台 fake 形状、三个固定不 spawn 路径及下载器重解析。
6. CLI 连接、对抗安全门禁、完整套件、构建/打包及一次性留存证据。

## 当前验收状态

| 范围 | 状态 | 真实性说明 |
| --- | --- | --- |
| 刷新来源/migration | `PASS (focused)` | migration/repository/ingestion 专项通过 |
| 私有刷新 child | `PASS (offline fake child)` | detail helper 已对 fake 锁定 checkout 运行并清理精确 attempt 根 |
| 手工签名 locator 下载 | `PASS (offline wiring)` | 显式 CLI 开关已构造惰性精确来源 refresher；真实流量未验收 |
| 成功/恢复终态清理 | `PASS (focused)` | handler 53 项通过；supervision 14 项通过、1 项跳过 |
| 自动 DAG | 未实现 | 执行 0010 |
| 真人登录、作者流量、刷新、CDN 与 Emby/Jellyfin | `NOT_RUN` | 未提供授权环境 |

## 如实延期

- 本计划不实现 QR challenge 展示与手机号登录。
- Bilibili 可播放视频/DASH/多 P/字幕/弹幕及微博/贴吧/知乎 Asset discovery 继续不可用。
- 有意排除可能携带凭据的 CDN header 与 child 内下载；需要这些能力的真实 URL 继续未验收。
- Unresolved 账户清理 block 没有自动清除/绕过路径。
- REST、常驻监督、Docker、公网部署及 HA/PostgreSQL 仍属于后续工作。
