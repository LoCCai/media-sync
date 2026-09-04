[English](status.md) | **中文**

# 项目统一状态（单一事实来源）

边界：执行 0053 已基于 `be26cc7` 基线与 `66e18ff` 计划完成交付和冻结验证；执行 0054 是下一产品切片。执行 0047 仍是开启中的 P0 操作者门，Linux 持久性/恢复/进程检查以及全部真人登录/抓取/CDN 和真实 Emby/Jellyfin 行继续保持 `NOT_RUN`。本表是权威状态视图；逐执行细节见 [`executions/`](README.zh.md)，证据见各验证记录。每次收尾时更新本页。

## 里程碑状态

| 里程碑 | 状态 |
| --- | --- |
| 离线功能开发 | 平台形状冻结于 0039，外加 0040/0044 运维面与 0050 Console v2 控制面基础；0043（弹幕/字幕）仍延期 |
| REST API + Web 控制台 | SvelteKit 5 Console v2 基础（0050）、能力驱动账户/订阅工作台（0051）、0052 持久 Operation/Event 任务中心及 0053 安全内容/资产浏览器和归档预览均已交付；下一步为 0054 媒体服务器树/控制 |
| Docker 打包 | 候选镜像、可复现加固及最终镜像不含 Node 的 Console v2 多阶段构建已交付（0041、0048–0050）；操作者修复版镜像已构建/启动，doctor、深度预检与 Chromium 启动全绿 |
| 运维文档 / 安全审查 / 发布清单 | 已交付（0045、0046） |
| 真人验收（最终门） | 开启中——执行 0047，操作者在 Linux 协助执行 |

## 验证矩阵

| 维度 | 状态 | 证据 / 阻塞 |
| --- | --- | --- |
| 实现（离线形状） | 七平台 15+ 冻结形状 | 执行 0013–0039 记录 |
| 离线完整套件 | Execution 0053 冻结套件：`2456 passed, 3 skipped, 1 warning in 479.63s`；skip 是三个 Windows 不适用的 POSIX venv/权限用例，warning 是既有 Starlette/httpx 弃用。Linux 阶段 B 仍为权威 | 执行 0053 验证 |
| API/控制台测试 | Execution 0053 explorer/归档/API 聚焦回归 `228 passed`；50 项 Web 单测、格式、Svelte check、生产构建及本地 query/弹窗浏览器 smoke 通过。聚焦选择存在重叠；真实平台/媒体服务器资格仍是外部门 | Execution 0053 验证 |
| 静态门（ruff/format/mypy/compileall/docs/前端检查与构建） | Execution 0053 全仓 Ruff、199 个 Python 文件格式、96 个源码 strict mypy、compileall、sdist/wheel、文档、Web format/check/test/build、两个锁定上游、tracked-output 审计及 `git diff --check` 全部通过 | Execution 0053 验证 |
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
