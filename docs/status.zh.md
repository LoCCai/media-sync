[English](status.md) | **中文**

# 项目统一状态（单一事实来源）

## 最新：部署登录修复（2026-09-05）

操作者已手工成功进入部署后台。B 站、抖音和小红书的现有账户显示登录会话失败，共观察到六次历史登录操作失败；这是失败证据，不是真人验收通过。冻结计划 `204655d` 下已在本地修复共享浏览器缓存环境、五平台 Chrome 通道及有头预检不匹配，容器也会先确认 Xvfb 可连接再迁移。真实 Windows 空白有头 Chromium 启动通过（`151.0.7922.34`）。最终回归/发布证据和待办见[登录运行环境验证](executions/0055-operator-auth-playback-evidence/login-runtime/verification.zh.md)。修复后的 Linux 镜像、扫码、会话复用、采集和 Emby/Jellyfin 金丝雀仍待验证，七平台总体目标保持开放。下文旧检查点结果除该记录明确更新外均为历史证据。

已推送的执行 0055 后端鉴权实现为提交 `f19bfaa`（冻结规划基线为 `4564b2a`）。它会在绑定端口前解析必需的类型化操作者凭据，支持可选且不同的 Bearer 凭据，强制精确 Host/Origin 策略，轮换进程内 HttpOnly `SameSite=Strict` session Cookie，对 Cookie 鉴权的不安全方法强制 CSRF，以精确匿名白名单配合默认拒绝的 ASGI 保护，只接受严格有界的登录 JSON，并把凭据/origin 契约接入 Docker Compose。其 190 项 auth/API 专项与完整离线回归（`2811 passed, 14 skipped, 1 warning in 561.43s`）通过，69 项 Web 测试及本机可用的静态/构建/docs/打包门也通过。3 项跳过为 Windows/POSIX 差异；本工作站无法运行 11 项真实 PostgreSQL 竞态与 Docker 验证，因此不作通过声明。

确认后端已发布为 `13de3b7`。已发布 `2e1949f` 的[投影检查点](executions/0055-operator-auth-playback-evidence/evidence-projection/progress.zh.md)增加有界作者证据读取与资格 schema v3。先在 publication/profile 权威稳定时完成一次新 lookup，再打开短读取事务；当前证据独立查询，历史默认 20 行、最多 50 行，总物化账本行不超过 `limit + 2`。历史页截断不否定独立当前行；远端 lookup 截断则不能 PASS。远端不确定使历史未知，完整不存在使其过期；只有精确持久确认可授予作者范围 PASS。无作者则 scope 为 `not_requested`，不查询证据或远端。Web login/session/CSRF 现已实现且本地合成浏览器门禁已通过；确认 UI 仍待实现。仓库真人资格继续为 `NOT_RUN`，provider completion 与自动扫描仍为 `NOT_IMPLEMENTED`。历史证据见[投影验证](executions/0055-operator-auth-playback-evidence/evidence-projection/verification.zh.md)，执行 0047 继续作为操作者门。

当前 `714c849` 冻结计划下的安全控制台与启动预检已实现，本地离线与合成浏览器门禁已通过；准确结果见[当前检查点](executions/0055-operator-auth-playback-evidence/secure-console/verification.zh.md)。本地合成浏览器门通过后优先验证当前 Linux 镜像并推进 Bilibili／小红书获授权金丝雀；P1 确认 UI 不阻塞既有 CLI 真人流程。

## 里程碑状态

| 里程碑 | 状态 |
| --- | --- |
| 离线功能开发 | 平台形状冻结于 0039，外加 0040/0044 运维面与 0050 Console v2 控制面基础；0043（弹幕/字幕）仍延期 |
| REST API + Web 控制台 | Console v2 会话门、内存 CSRF、退出／过期／401 与 QR／SSE 已实现，本地合成浏览器门禁已通过；8 个精确 HTML 深链接未登录时 303 到根登录，API／未知路由仍拒绝。Legacy 是受保护迁移提示 |
| 操作者鉴权 + 播放证据 | 后端鉴权、不可变身份／账本、仅浏览器确认、有界 current/stale/unknown 投影及资格 v3 已实现。无精确当前证据时 playback 为 IMPLEMENTED/NOT_RUN；PASS 只适用于选定作者。Web 会话集成已实现且本地合成浏览器门禁已通过；确认 UI 仍待实现，真人播放为 NOT_RUN |
| Docker 打包 | 0041、0048–0050 历史候选镜像与 Console v2 多阶段构建已交付，当时修复版镜像通过 doctor、深度预检与 Chromium 启动；当前 0055 鉴权版镜像尚未执行，不能复用历史 PASS |
| 运维文档 / 安全审查 / 发布清单 | 已交付（0045、0046） |
| 真人验收（最终门） | 开启中——执行 0047，操作者在 Linux 协助执行 |

## 验证矩阵

| 维度 | 状态 | 证据 / 阻塞 |
| --- | --- | --- |
| 实现（离线形状） | 七平台 15+ 冻结形状 | 执行 0013–0039 记录 |
| 离线完整套件 | 当前 P0 Python 为 3155 项通过、22 项跳过、1 个既有 warning（670.16 秒），其他结果统一见[验证](executions/0055-operator-auth-playback-evidence/secure-console/verification.zh.md)；`2e1949f` 的 2999 项投影门为历史证据，PostgreSQL skip 不构成执行证据 | 执行 0055 安全控制台 |
| API/控制台测试 | 本地合成浏览器 session／CSRF、账户创建、QR、归档图像／视频加载、Jobs SSE、跨标签退出、自然过期与稍后浏览门已通过；Web 9 文件／114 项、Svelte 零 error/warning 与 build 通过。视频只加载／解码，未点击播放；准确证据见[验证](executions/0055-operator-auth-playback-evidence/secure-console/verification.zh.md) | 执行 0055 安全控制台 |
| 静态与制品门 | 当前 Ruff/format、mypy、compileall、Web、docs／上游与包检查结果统一见[验证](executions/0055-operator-auth-playback-evidence/secure-console/verification.zh.md) | 执行 0055 安全控制台 |
| Docker 镜像构建 | 0050/0047 镜像预检仍是历史 `PASS`；当前 0055 鉴权版 Compose 接线已代码审查，但本工作站没有 Docker CLI，故为 `NOT_RUN` | 执行 0050/0047 与 0055-A 验证 |
| 容器就绪 / 重启持久性 / 备份恢复演练 | 旧镜像深度预检为历史 `PASS`；当前镜像就绪、重启持久性与备份恢复 `NOT_RUN` | 执行 0047；docs/operations.zh.md 流程就绪 |
| 真人登录（任一平台） | 已观察 B 站/抖音/小红书历史失败会话；修复版本尚未真人验证，无平台 PASS | [失败证据](executions/0055-operator-auth-playback-evidence/secure-console/login-runtime-triage.zh.md)；执行 0047 仍为金丝雀门槛 |
| 真人抓取 / 下载 / 增量性 | `NOT_RUN`——操作者（阶段 C–E） | 执行 0047 |
| 真实 Emby/Jellyfin 连接、Library 发现与定向刷新接受 | `NOT_RUN`——0054-A 已实现，但未使用获授权真实服务器 | 执行 0054 与 0047 |
| Provider/path 项目查找与刷新后项目观察 | `IMPLEMENTED / NOT_RUN`——本地/mock 门禁通过，但未使用获授权真实 Emby/Jellyfin 服务器 | 执行 0054-B 验证 |
| Provider task completion | `NOT_IMPLEMENTED`——Emby/Jellyfin 共同刷新 API 不提供持久任务身份；阶段 B 不声明该能力 | 执行 0054-B 真实性边界 |
| 操作者访问控制 | 后端鉴权已发布；当前共享 `serve --check-config` 验证、含 `-- serve` 的迁移前入口检查及 Web 会话／CSRF 已实现且本地合成浏览器门禁已通过。预检不做 DNS／绑定，也不代表实际 Linux UID 或端口可用 | [当前验证](executions/0055-operator-auth-playback-evidence/secure-console/verification.zh.md) |
| 播放身份／持久化／确认后端 | 已在 `13de3b7` 实现并离线验证；读取／资格检查点现已消费账本。本工作站真实 PostgreSQL 竞态继续为 NOT_RUN | 执行 0055 |
| 证据投影与资格／自动扫描 | 作者证据与 schema v3 已 IMPLEMENTED；未选作者或无精确当前证据为 NOT_RUN，远端不完整／不确定权威不能授予 PASS。导出后自动扫描继续为 NOT_IMPLEMENTED | [投影计划](executions/0055-operator-auth-playback-evidence/evidence-projection/plan.zh.md) |
| 外部安全审计 | `NOT_RUN`——可选 | docs/security-review.md 残余风险 |

## 发布阻塞项（v0.1.0-rc1）

安全后台／迁移前预检实现及本地合成浏览器检查已完成，见[当前验证](executions/0055-operator-auth-playback-evidence/secure-console/verification.zh.md)。P1 证据展示／确认 UI 仍待实现，但不阻塞既有 CLI 金丝雀。

1. P0：当前精确提交／镜像的 Linux 基线未完成（运行用户 secret 可读性、迁移边界、完整套件、宿主机端口、启动／重启持久性、备份恢复与进程基线）——阶段 B；旧镜像通过不能替代。
2. 真人行零记录——阶段 C 金丝雀（Bilibili + 小红书）先行，随后其余平台。

0.1 最低发布条件：至少两个金丝雀平台达到 **Supported**（登录、同步、下载、真实增量、Emby 重扫 + 抽样播放），其余平台如实分级（Experimental / Metadata-only / Blocked External / Unsupported），且项目自我表述为“七平台适配框架；实际资格状态见状态矩阵”，而非“支持七个平台”。
