[English](status.md) | **中文**

# 项目统一状态（单一事实来源）

已交付实现边界：执行 0054（包括[阶段 B](executions/0054-media-library-server-integration/phase-b/plan.zh.md)）已通过实现/验证提交 `b4af46d`、`ff5da07`、`88f5ed0`、`22bd9ef`、`48ecbe9` 与 `d8bbdf7` 交付。它在保留 legacy 只确认接受刷新的同时，新增有界精确 provider/path 查找与如实的 absent-to-unique-match 刷新后观察，并以真实 PostgreSQL 服务验证 Operation 竞态。规划边界现已包含基于 `d0a8cc2` 冻结的[执行 0055 阶段 A](executions/0055-operator-auth-playback-evidence/goal.zh.md)：先交付关闭失败的单操作者鉴权，再交付 append-only、经鉴权的播放证据；实现与实现验证均尚未开始。当前 51 条 API 路由仍为匿名，播放证据仍为 `NOT_IMPLEMENTED`，真人播放仍为 `NOT_RUN`。共同 API 不支持 provider task completion，因此它既不是阶段 B，也不是 0055-A 的声明。执行 0047 仍是开启中的 P0 操作者门，Linux 持久性/恢复/进程检查以及全部已实现真人登录/抓取/CDN/媒体服务器行继续保持 `NOT_RUN`。缺失能力是 `NOT_IMPLEMENTED`，不是尚未执行的真人行。本表是权威状态视图；逐执行细节见 [`executions/`](README.zh.md)，证据见各验证记录。每次收尾时更新本页。

## 里程碑状态

| 里程碑 | 状态 |
| --- | --- |
| 离线功能开发 | 平台形状冻结于 0039，外加 0040/0044 运维面与 0050 Console v2 控制面基础；0043（弹幕/字幕）仍延期 |
| REST API + Web 控制台 | 已交付 0050–0053 基础及执行 0054 的安全受管树分页、脱敏媒体服务器姿态、持久只确认接受/作者观察 Operation、精确项目查找、资格 schema v2，以及如实的 Library/Settings/Jobs 证据；0055-A 鉴权目前仅冻结规划，当前 API 仍为匿名 |
| 操作者鉴权 + 播放证据 | 0055-A 中英双语 goal/plan/progress/verification 已在规划边界冻结；实现尚未开始，revision `0008_playback_evidence` 不存在，播放证据为 `NOT_IMPLEMENTED`，真人播放为 `NOT_RUN` |
| Docker 打包 | 候选镜像、可复现加固及最终镜像不含 Node 的 Console v2 多阶段构建已交付（0041、0048–0050）；操作者修复版镜像已构建/启动，doctor、深度预检与 Chromium 启动全绿 |
| 运维文档 / 安全审查 / 发布清单 | 已交付（0045、0046） |
| 真人验收（最终门） | 开启中——执行 0047，操作者在 Linux 协助执行 |

## 验证矩阵

| 维度 | 状态 | 证据 / 阻塞 |
| --- | --- | --- |
| 实现（离线形状） | 七平台 15+ 冻结形状 | 执行 0013–0039 记录 |
| 离线完整套件 | 启用真实 PostgreSQL 的执行 0054 阶段 B 收尾套件：`2763 passed, 3 skipped, 1 warning in 544.08s`；skip 是三个 Windows 不适用的 POSIX venv/mode 用例，warning 是既有 Starlette/httpx 弃用 | 执行 0054 阶段 B 验证 |
| API/控制台测试 | 阶段 B 后端联合专项 350 项通过；qualification/Library/API 专项 70 项通过；Library application 专项 12 项通过；7 个文件中的 69 项 Web 测试及格式、Svelte check、生产构建通过。聚焦选择存在重叠；不声明阶段 B 浏览器 smoke 或真实媒体服务器资格 | 执行 0054 阶段 B 验证 |
| 静态门（ruff/format/mypy/compileall/docs/前端检查与构建） | 执行 0054 全仓 Ruff/format、strict mypy、compileall、sdist/wheel、双语文档、Web format/test/check/build、两个锁定上游、tracked-output/机密性/宿主路径审计及 `git diff --check` 通过 | 执行 0054 阶段 B 验证 |
| Docker 镜像构建 | 构建/运行时预检 `PASS`：修复版镜像已启动；doctor 与深度预检均为 `ready`；运行时 Chromium `151.0.7922.34` 与构建清单一致 | 执行 0050 与 0047 验证 |
| 容器就绪 / 重启持久性 / 备份恢复演练 | 深度预检 `PASS`；重启持久性与备份恢复 `NOT_RUN` | 执行 0047；docs/operations.zh.md 流程就绪 |
| 真人登录（任一平台） | `NOT_RUN`——操作者（阶段 C 金丝雀：Bilibili + 小红书） | 执行 0047 |
| 真人抓取 / 下载 / 增量性 | `NOT_RUN`——操作者（阶段 C–E） | 执行 0047 |
| 真实 Emby/Jellyfin 连接、Library 发现与定向刷新接受 | `NOT_RUN`——0054-A 已实现，但未使用获授权真实服务器 | 执行 0054 与 0047 |
| Provider/path 项目查找与刷新后项目观察 | `IMPLEMENTED / NOT_RUN`——本地/mock 门禁通过，但未使用获授权真实 Emby/Jellyfin 服务器 | 执行 0054-B 验证 |
| Provider task completion | `NOT_IMPLEMENTED`——Emby/Jellyfin 共同刷新 API 不提供持久任务身份；阶段 B 不声明该能力 | 执行 0054-B 真实性边界 |
| 操作者访问控制 | `NOT_IMPLEMENTED`——基线 FastAPI 应用仍有 51 条匿名路由；0055-A 已冻结“绑定前关闭失败的单操作者 session/CSRF + 可选独立 Bearer 鉴权”，但尚未运行实现测试 | 执行 0055-A [目标](executions/0055-operator-auth-playback-evidence/goal.zh.md)与[验证](executions/0055-operator-auth-playback-evidence/verification.zh.md) |
| 播放证据写入 / 导出后自动扫描 | `NOT_IMPLEMENTED`——0055-A 播放证据计划已冻结，但尚无代码或 revision `0008_playback_evidence`；自动联动不属于阶段 A，且尚无冻结归属 | 执行 0055-A [计划](executions/0055-operator-auth-playback-evidence/plan.zh.md)与执行 0054 资格边界 |
| 外部安全审计 | `NOT_RUN`——可选 | docs/security-review.md 残余风险 |

## 发布阻塞项（v0.1.0-rc1）

1. Linux 主机基线未完成（完整套件、宿主机端口复核、重启持久性、备份恢复与进程基线）——阶段 B。
2. 真人行零记录——阶段 C 金丝雀（Bilibili + 小红书）先行，随后其余平台。

0.1 最低发布条件：至少两个金丝雀平台达到 **Supported**（登录、同步、下载、真实增量、Emby 重扫 + 抽样播放），其余平台如实分级（Experimental / Metadata-only / Blocked External / Unsupported），且项目自我表述为“七平台适配框架；实际资格状态见状态矩阵”，而非“支持七个平台”。
