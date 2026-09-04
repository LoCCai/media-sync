[English](status.md) | **中文**

# 项目统一状态（单一事实来源）

边界：执行 0052 已在本地交付并完成冻结验证；包含本记录的提交是其发布边界，提交后立即与 GitHub 核对且不嵌入自身 SHA。执行 0047 仍是开启中的 P0 操作者门，Linux 持久性/恢复/进程检查以及全部真人登录/抓取/CDN 和真实 Emby/Jellyfin 行继续保持 `NOT_RUN`。本表是权威状态视图；逐执行细节见 [`executions/`](README.zh.md)，证据见各验证记录。每次收尾时更新本页。

## 里程碑状态

| 里程碑 | 状态 |
| --- | --- |
| 离线功能开发 | 平台形状冻结于 0039，外加 0040/0044 运维面与 0050 Console v2 控制面基础；0043（弹幕/字幕）仍延期 |
| REST API + Web 控制台 | SvelteKit 5 Console v2 基础（0050）、能力驱动账户/订阅工作台（0051），以及 0052 面向五类 API 工作流的持久 Operation/Event/subject、提交有序 SSE、跨 coordinator 两阶段取消、非阻塞单飞协调、任务中心与窄化 JSON 支持响应均已交付 |
| Docker 打包 | 候选镜像、可复现加固及最终镜像不含 Node 的 Console v2 多阶段构建已交付（0041、0048–0050）；操作者修复版镜像已构建/启动，doctor、深度预检与 Chromium 启动全绿 |
| 运维文档 / 安全审查 / 发布清单 | 已交付（0045、0046） |
| 真人验收（最终门） | 开启中——执行 0047，操作者在 Linux 协助执行 |

## 验证矩阵

| 维度 | 状态 | 证据 / 阻塞 |
| --- | --- | --- |
| 实现（离线形状） | 七平台 15+ 冻结形状 | 执行 0013–0039 记录 |
| 离线完整套件 | Execution 0052 冻结套件：`2315 passed, 3 skipped, 1 warning in 555.05s`；skip 是三个 Windows 不适用的 POSIX venv/权限用例，warning 是既有 Starlette/httpx 弃用。Linux 阶段 B 仍为权威 | 执行 0052 验证 |
| API/控制台测试 | Execution 0052 聚焦 Operation/API 集成 `241 passed`；支持包 service/HTTP `30 passed`；Web `17 passed`、Svelte check 0 error/0 warning、生产构建通过。聚焦选择存在重叠；真实 Jobs 路由浏览器交互仍是后续质量债 | Execution 0052 验证 |
| 静态门（ruff/format/mypy/compileall/docs/前端检查与构建） | 0052 全仓 Ruff、662 文件格式、94 个源码 strict mypy、compileall、sdist/wheel、466 份文档、Web format/check/test/build、两个锁定上游、733 个 tracked 文件产物审计及 `git diff --check` 全部通过 | Execution 0052 验证 |
| Docker 镜像构建 | 构建/运行时预检 `PASS`：修复版镜像已启动；doctor 与深度预检均为 `ready`；运行时 Chromium `151.0.7922.34` 与构建清单一致 | 执行 0050 与 0047 验证 |
| 容器就绪 / 重启持久性 / 备份恢复演练 | 深度预检 `PASS`；重启持久性与备份恢复 `NOT_RUN` | 执行 0047；docs/operations.zh.md 流程就绪 |
| 真人登录（任一平台） | `NOT_RUN`——操作者（阶段 C 金丝雀：Bilibili + 小红书） | 执行 0047 |
| 真人抓取 / 下载 / 增量性 | `NOT_RUN`——操作者（阶段 C–E） | 执行 0047 |
| 真实 Emby/Jellyfin 重扫 + 播放 | `NOT_RUN`——Supported 等级的强制项（阶段 E/F） | 执行 0047 验收规则 |
| 外部安全审计 | `NOT_RUN`——可选 | docs/security-review.md 残余风险 |

## 发布阻塞项（v0.1.0-rc1）

1. Linux 主机基线未完成（完整套件、宿主机端口复核、重启持久性、备份恢复与进程基线）——阶段 B。
2. 真人行零记录——阶段 C 金丝雀（Bilibili + 小红书）先行，随后其余平台。

0.1 最低发布条件：至少两个金丝雀平台达到 **Supported**（登录、同步、下载、真实增量、Emby 重扫 + 抽样播放），其余平台如实分级（Experimental / Metadata-only / Blocked External / Unsupported），且项目自我表述为“七平台适配框架；实际资格状态见状态矩阵”，而非“支持七个平台”。
