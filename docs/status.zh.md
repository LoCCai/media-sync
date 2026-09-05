[English](status.md) | **中文**

# 项目统一状态（单一事实来源）

已推送的执行 0055 后端鉴权实现为提交 `f19bfaa`（冻结规划基线为 `4564b2a`）。它会在绑定端口前解析必需的类型化操作者凭据，支持可选且不同的 Bearer 凭据，强制精确 Host/Origin 策略，轮换进程内 HttpOnly `SameSite=Strict` session Cookie，对 Cookie 鉴权的不安全方法强制 CSRF，以精确匿名白名单配合默认拒绝的 ASGI 保护，只接受严格有界的登录 JSON，并把凭据/origin 契约接入 Docker Compose。其 190 项 auth/API 专项与完整离线回归（`2811 passed, 14 skipped, 1 warning in 561.43s`）通过，69 项 Web 测试及本机可用的静态/构建/docs/打包门也通过。3 项跳过为 Windows/POSIX 差异；本工作站无法运行 11 项真实 PostgreSQL 竞态与 Docker 验证，因此不作通过声明。

当前工作变更只推进播放证据基础：完整且唯一 `matched` 的媒体服务器 lookup 现在会派生绑定上下文的 `observation_fingerprint`；`not_found` 不派生也不暴露该值，Web lookup response 类型已同步这一只读契约。Revision `0008_playback_evidence` 新增 append-only 账本，约束规范身份、安全摘要、时间戳、`RESTRICT` 作者/publication Job 父项及唯一 observation 身份；仓储提供“首个写入者创建或精确重放”、显式身份冲突、SQLite 写者预留及 PostgreSQL unique-conflict 路径。当前完整套件通过 `2868 passed, 22 skipped, 1 warning in 558.19s`；跳过项分别为 3 项 Windows/POSIX、11 项既有 Operation PostgreSQL，以及因未配置测试 URL 而跳过的 8 项新增 PlaybackEvidence PostgreSQL。Web 69 项及 format/check/build、727 文件 Ruff/format、105 个源文件 strict mypy 与 compileall 均通过；真实 PostgreSQL 与 Docker 均未运行。这还不是经鉴权的播放确认：确认 service/API/UI 与资格 schema v3 均不存在。隔离 Author/Job/PlaybackEvidence PostgreSQL harness 不能证明完整 schema 或生产 PostgreSQL 支持。Console v2 与 `/legacy` 也尚未集成 login/session/CSRF，因此 Web 控制台当前不是可操作的管理界面。由此，`playback_evidence` 继续为 `NOT_IMPLEMENTED`，真人播放继续为 `NOT_RUN`，执行 0047 的全部真人资格行也继续为 `NOT_RUN`。共同 API 仍不支持 provider task completion，因此它既不是 0054-B，也不是 0055-A 的声明。执行 0047 仍是开启中的 P0 操作者门；缺失能力是 `NOT_IMPLEMENTED`，不是尚未执行的真人行。本表是权威状态视图；逐执行细节见 [`executions/`](README.zh.md)，证据见各验证记录。每次收尾时更新本页。

## 里程碑状态

| 里程碑 | 状态 |
| --- | --- |
| 离线功能开发 | 平台形状冻结于 0039，外加 0040/0044 运维面与 0050 Console v2 控制面基础；0043（弹幕/字幕）仍延期 |
| REST API + Web 控制台 | 已交付 0050–0053 基础及执行 0054 的安全受管树分页、脱敏媒体服务器姿态、持久只确认接受/作者观察 Operation、精确项目查找、资格 schema v2，以及如实的 Library/Settings/Jobs 证据；提交 `f19bfaa` 已实现 0055-A 后端鉴权边界。Web lookup 类型现可接收仅 matched 的 observation fingerprint，但 Web login/session/CSRF 集成与任何确认 UI 仍待实现，控制台当前不是可操作的管理界面 |
| 操作者鉴权 + 播放证据 | 提交 `f19bfaa` 已实现后端单操作者边界，并通过本机可用的完整离线门。当前工作变更新增仅 matched 身份、revision `0008` 账本及仓储 replay/竞态原语，但 Web 鉴权集成、经鉴权确认 service/API/UI 与资格 schema v3 仍待实现。播放证据仍为 `NOT_IMPLEMENTED`，真人播放为 `NOT_RUN` |
| Docker 打包 | 候选镜像、可复现加固及最终镜像不含 Node 的 Console v2 多阶段构建已交付（0041、0048–0050）；操作者修复版镜像已构建/启动，doctor、深度预检与 Chromium 启动全绿 |
| 运维文档 / 安全审查 / 发布清单 | 已交付（0045、0046） |
| 真人验收（最终门） | 开启中——执行 0047，操作者在 Linux 协助执行 |

## 验证矩阵

| 维度 | 状态 | 证据 / 阻塞 |
| --- | --- | --- |
| 实现（离线形状） | 七平台 15+ 冻结形状 | 执行 0013–0039 记录 |
| 离线完整套件 | 当前工作树：`2868 passed, 22 skipped, 1 warning in 558.19s`；3 项跳过为 Windows/POSIX 差异，11 项为既有 Operation PostgreSQL 竞态，8 项为未配置 URL 的新增 PlaybackEvidence PostgreSQL 竞态，warning 是既有 Starlette/httpx 弃用 | 当前执行 0055 验证；执行 0054 仍是最近一次真实 PostgreSQL 对照 |
| API/控制台测试 | 已提交的 0055 auth/config/七个 API 专项通过 `190 passed, 1 warning in 41.99s`；当前 Web 套件通过 69 项及 format/check/build。当前 Web 变更只同步 lookup response 类型；不声明 Web login/session/CSRF、确认 UI 或已鉴权浏览器 smoke 已实现 | 执行 0055-A 验证与当前持久化增量 |
| 静态门（ruff/format/mypy/compileall/docs/前端检查与构建） | 当前工作树通过全仓 727 文件 Ruff/format、105 个源文件 strict mypy、compileall、498 份文档检查、两个锁定上游检查、Web format/check/build，以及隔离 wheel/sdist 构建与内容检查 | 执行 0055-A 验证与当前持久化增量 |
| Docker 镜像构建 | 0050/0047 镜像预检仍是历史 `PASS`；当前 0055 鉴权版 Compose 接线已代码审查，但本工作站没有 Docker CLI，故为 `NOT_RUN` | 执行 0050/0047 与 0055-A 验证 |
| 容器就绪 / 重启持久性 / 备份恢复演练 | 深度预检 `PASS`；重启持久性与备份恢复 `NOT_RUN` | 执行 0047；docs/operations.zh.md 流程就绪 |
| 真人登录（任一平台） | `NOT_RUN`——操作者（阶段 C 金丝雀：Bilibili + 小红书） | 执行 0047 |
| 真人抓取 / 下载 / 增量性 | `NOT_RUN`——操作者（阶段 C–E） | 执行 0047 |
| 真实 Emby/Jellyfin 连接、Library 发现与定向刷新接受 | `NOT_RUN`——0054-A 已实现，但未使用获授权真实服务器 | 执行 0054 与 0047 |
| Provider/path 项目查找与刷新后项目观察 | `IMPLEMENTED / NOT_RUN`——本地/mock 门禁通过，但未使用获授权真实 Emby/Jellyfin 服务器 | 执行 0054-B 验证 |
| Provider task completion | `NOT_IMPLEMENTED`——Emby/Jellyfin 共同刷新 API 不提供持久任务身份；阶段 B 不声明该能力 | 执行 0054-B 真实性边界 |
| 操作者访问控制 | `IMPLEMENTED / offline verification PASS`——后端在缺少必需类型化凭据时会在绑定端口前失败，强制精确 Host/Origin 与默认拒绝的路由保护，并支持轮换式 HttpOnly session、CSRF 及可选且不同的 Bearer 凭据；190 项专项与本机可用的完整套件均通过。Web login/session/CSRF 集成仍待实现，因此不声明可操作的已鉴权控制台或任何真人资格 | 执行 0055-A [目标](executions/0055-operator-auth-playback-evidence/goal.zh.md)与[验证](executions/0055-operator-auth-playback-evidence/verification.zh.md)；实现提交 `f19bfaa` |
| 播放证据身份 / 持久化基础 | `当前工作变更已实现 / 不是用户能力`——仅 matched observation 身份、revision `0008` append-only schema 与精确 create-or-replay 仓储原语已经存在。SQLite 会在自然键读取前预留写者；PostgreSQL 语义由隔离三表竞态套件表达，但这些真实用例本机为 `NOT_RUN`，不能证明完整 PostgreSQL 支持 | 当前执行 0055 持久化增量 |
| 经鉴权播放确认 / 导出后自动扫描 | `NOT_IMPLEMENTED`——确认 service/API/UI 与资格 schema v3 尚不存在，因此一张账本表与只读 fingerprint 不会使 `playback_evidence` 成为已实现。自动联动不属于阶段 A，且尚无冻结归属 | 执行 0055-A [计划](executions/0055-operator-auth-playback-evidence/plan.zh.md)与执行 0054 资格边界 |
| 外部安全审计 | `NOT_RUN`——可选 | docs/security-review.md 残余风险 |

## 发布阻塞项（v0.1.0-rc1）

1. 执行 0055 尚未完成：Web login/session/CSRF 集成、经鉴权播放确认 service/API/UI、资格 schema v3 及其收尾验证仍待完成。
2. Linux 主机基线未完成（完整套件、宿主机端口复核、重启持久性、备份恢复与进程基线）——阶段 B。
3. 真人行零记录——阶段 C 金丝雀（Bilibili + 小红书）先行，随后其余平台。

0.1 最低发布条件：至少两个金丝雀平台达到 **Supported**（登录、同步、下载、真实增量、Emby 重扫 + 抽样播放），其余平台如实分级（Experimental / Metadata-only / Blocked External / Unsupported），且项目自我表述为“七平台适配框架；实际资格状态见状态矩阵”，而非“支持七个平台”。
