[English](status.md) | **中文**

# 项目统一状态（单一事实来源）

已推送的执行 0055 后端鉴权实现为提交 `f19bfaa`（冻结规划基线为 `4564b2a`）。它会在绑定端口前解析必需的类型化操作者凭据，支持可选且不同的 Bearer 凭据，强制精确 Host/Origin 策略，轮换进程内 HttpOnly `SameSite=Strict` session Cookie，对 Cookie 鉴权的不安全方法强制 CSRF，以精确匿名白名单配合默认拒绝的 ASGI 保护，只接受严格有界的登录 JSON，并把凭据/origin 契约接入 Docker Compose。其 190 项 auth/API 专项与完整离线回归（`2811 passed, 14 skipped, 1 warning in 561.43s`）通过，69 项 Web 测试及本机可用的静态/构建/docs/打包门也通过。3 项跳过为 Windows/POSIX 差异；本工作站无法运行 11 项真实 PostgreSQL 竞态与 Docker 验证，因此不作通过声明。

确认后端已发布为 `13de3b7`。当前[投影检查点](executions/0055-operator-auth-playback-evidence/evidence-projection/progress.zh.md)增加有界作者证据读取与资格 schema v3。先在 publication/profile 权威稳定时完成一次新 lookup，再打开短读取事务；当前证据独立查询，历史默认 20 行、最多 50 行，总物化账本行不超过 `limit + 2`。历史页截断不否定独立当前行；远端 lookup 截断则不能 PASS。远端不确定使历史未知，完整不存在使其过期；只有精确持久确认可授予作者范围 PASS。无作者则 scope 为 `not_requested`，不查询证据或远端。Web login/session/CSRF 与确认 UI 仍待实现。仓库真人资格继续为 `NOT_RUN`，provider completion 与自动扫描仍为 `NOT_IMPLEMENTED`。见[当前验证](executions/0055-operator-auth-playback-evidence/evidence-projection/verification.zh.md)，执行 0047 继续作为操作者门。

后续按[交付优先级补充计划](executions/0055-operator-auth-playback-evidence/delivery-priorities.zh.md)先完成安全 Web login/session/CSRF 与凭据／迁移前预检，再验证当前 Linux 镜像并推进 Bilibili／小红书获授权金丝雀；最小证据 UI 不阻塞既有 CLI 真人流程。

## 里程碑状态

| 里程碑 | 状态 |
| --- | --- |
| 离线功能开发 | 平台形状冻结于 0039，外加 0040/0044 运维面与 0050 Console v2 控制面基础；0043（弹幕/字幕）仍延期 |
| REST API + Web 控制台 | 经鉴权作者证据读取与资格 v3 已加入既有媒体库、观察及任务流程。Console v2 与 `/legacy` 仍需 login/session/CSRF 和确认 UI，才能成为可用管理客户端 |
| 操作者鉴权 + 播放证据 | 后端鉴权、不可变身份／账本、仅浏览器确认、有界 current/stale/unknown 投影及资格 v3 已实现。无精确当前证据时 playback 为 IMPLEMENTED/NOT_RUN；PASS 只适用于选定作者。Web 集成仍待完成，真人播放为 NOT_RUN |
| Docker 打包 | 0041、0048–0050 历史候选镜像与 Console v2 多阶段构建已交付，当时修复版镜像通过 doctor、深度预检与 Chromium 启动；当前 0055 鉴权版镜像尚未执行，不能复用历史 PASS |
| 运维文档 / 安全审查 / 发布清单 | 已交付（0045、0046） |
| 真人验收（最终门） | 开启中——执行 0047，操作者在 Linux 协助执行 |

## 验证矩阵

| 维度 | 状态 | 证据 / 阻塞 |
| --- | --- | --- |
| 实现（离线形状） | 七平台 15+ 冻结形状 | 执行 0013–0039 记录 |
| 离线完整套件 | 当前投影为 2999 项通过、22 项跳过、1 个 warning（613.66 秒）；专项 220 项通过、1 个 warning（51.09 秒）。准确结果见[验证](executions/0055-operator-auth-playback-evidence/evidence-projection/verification.zh.md)；PostgreSQL skip 不构成执行证据 | 执行 0055 投影记录 |
| API/控制台测试 | 当前投影／确认／API／鉴权／资格／SQLite 并集通过 220 项，覆盖有界安全作者读取与 59 路由清单。Web 69 项及 format/check/build 通过，但不声明尚缺的登录／CSRF、确认 UI 或真实前后端浏览器 smoke | 执行 0055 投影验证 |
| 静态与制品门 | 当前 Ruff/format、mypy、compileall、Web、docs／上游及 wheel/sdist 结果与数量统一见[验证](executions/0055-operator-auth-playback-evidence/evidence-projection/verification.zh.md) | 执行 0055 投影记录 |
| Docker 镜像构建 | 0050/0047 镜像预检仍是历史 `PASS`；当前 0055 鉴权版 Compose 接线已代码审查，但本工作站没有 Docker CLI，故为 `NOT_RUN` | 执行 0050/0047 与 0055-A 验证 |
| 容器就绪 / 重启持久性 / 备份恢复演练 | 旧镜像深度预检为历史 `PASS`；当前镜像就绪、重启持久性与备份恢复 `NOT_RUN` | 执行 0047；docs/operations.zh.md 流程就绪 |
| 真人登录（任一平台） | `NOT_RUN`——操作者（阶段 C 金丝雀：Bilibili + 小红书） | 执行 0047 |
| 真人抓取 / 下载 / 增量性 | `NOT_RUN`——操作者（阶段 C–E） | 执行 0047 |
| 真实 Emby/Jellyfin 连接、Library 发现与定向刷新接受 | `NOT_RUN`——0054-A 已实现，但未使用获授权真实服务器 | 执行 0054 与 0047 |
| Provider/path 项目查找与刷新后项目观察 | `IMPLEMENTED / NOT_RUN`——本地/mock 门禁通过，但未使用获授权真实 Emby/Jellyfin 服务器 | 执行 0054-B 验证 |
| Provider task completion | `NOT_IMPLEMENTED`——Emby/Jellyfin 共同刷新 API 不提供持久任务身份；阶段 B 不声明该能力 | 执行 0054-B 真实性边界 |
| 操作者访问控制 | `IMPLEMENTED / offline verification PASS`——后端在缺少必需类型化凭据时会在绑定端口前失败，强制精确 Host/Origin 与默认拒绝的路由保护，并支持轮换式 HttpOnly session、CSRF 及可选且不同的 Bearer 凭据；190 项专项与本机可用的完整套件均通过。Web login/session/CSRF 集成仍待实现，因此不声明可操作的已鉴权控制台或任何真人资格 | 执行 0055-A [目标](executions/0055-operator-auth-playback-evidence/goal.zh.md)与[验证](executions/0055-operator-auth-playback-evidence/verification.zh.md)；实现提交 `f19bfaa` |
| 播放身份／持久化／确认后端 | 已在 `13de3b7` 实现并离线验证；读取／资格检查点现已消费账本。本工作站真实 PostgreSQL 竞态继续为 NOT_RUN | 执行 0055 |
| 证据投影与资格／自动扫描 | 作者证据与 schema v3 已 IMPLEMENTED；未选作者或无精确当前证据为 NOT_RUN，远端不完整／不确定权威不能授予 PASS。导出后自动扫描继续为 NOT_IMPLEMENTED | [投影计划](executions/0055-operator-auth-playback-evidence/evidence-projection/plan.zh.md) |
| 外部安全审计 | `NOT_RUN`——可选 | docs/security-review.md 残余风险 |

## 发布阻塞项（v0.1.0-rc1）

1. P0：安全 Web login/session/CSRF 与凭据／迁移前预检尚未完成。最小证据展示／确认 UI 属于后续已承诺工作，但不阻塞既有 CLI 真人金丝雀；按[交付优先级](executions/0055-operator-auth-playback-evidence/delivery-priorities.zh.md)执行。
2. P0：当前精确提交／镜像的 Linux 基线未完成（运行用户 secret 可读性、迁移边界、完整套件、宿主机端口、启动／重启持久性、备份恢复与进程基线）——阶段 B；旧镜像通过不能替代。
3. 真人行零记录——阶段 C 金丝雀（Bilibili + 小红书）先行，随后其余平台。

0.1 最低发布条件：至少两个金丝雀平台达到 **Supported**（登录、同步、下载、真实增量、Emby 重扫 + 抽样播放），其余平台如实分级（Experimental / Metadata-only / Blocked External / Unsupported），且项目自我表述为“七平台适配框架；实际资格状态见状态矩阵”，而非“支持七个平台”。
