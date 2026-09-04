[English](status.md) | **中文**

# 项目统一状态（单一事实来源）

边界：执行 0050（Web Console v2 基础）。本表是权威状态视图；逐执行细节见 [`executions/`](README.zh.md)，证据见各验证记录。每次收尾时更新本页。

## 里程碑状态

| 里程碑 | 状态 |
| --- | --- |
| 离线功能开发 | 平台形状冻结于 0039，外加 0040/0044 运维面与 0050 Console v2 控制面基础；0043（弹幕/字幕）仍延期 |
| REST API + Web 控制台 | 已实现 SvelteKit 5 Console v2 基础（0050）：九个路由页面、真实既有操作、内容/媒体库投影、一次性确认与 `/legacy` 回退；持久化/SSE/日志仍待后续 |
| Docker 打包 | 候选镜像、可复现加固及最终镜像不含 Node 的 Console v2 多阶段构建已交付（0041、0048–0050）；0050 镜像待操作者主机首次真实构建/运行 |
| 运维文档 / 安全审查 / 发布清单 | 已交付（0045、0046） |
| 真人验收（最终门） | 开启中——执行 0047，操作者在 Linux 协助执行 |

## 验证矩阵

| 维度 | 状态 | 证据 / 阻塞 |
| --- | --- | --- |
| 实现（离线形状） | 七平台 15+ 冻结形状 | 执行 0013–0039 记录 |
| 离线完整套件 | 执行 0050 编写工作站在 uv + ffmpeg/ffprobe 可用时运行：`2038 passed, 33 failed, 1 skipped`；33 项全部属于既有 Windows completion-receipt/进程非确定族（0048：33/35 项失败；0049：一次全绿）。Windows 保持 Experimental，Linux 阶段 B 仍为权威 | 执行 0050 验证与脱敏 junit 分组；原始 XML 继续在 `artifacts/` 下被 Git 忽略 |
| API/控制台测试 | API `9 passed`；checkout/许可证专项 `16 passed`；Svelte 单元 `2 passed`；九路由浏览器冒烟与一次性确认交互通过，控制台零错误 | 执行 0050 验证 |
| 静态门（ruff/format/mypy/compileall/docs/前端检查与构建） | 0050 变更范围全绿 | 执行 0050 验证 |
| Docker 镜像构建 | 编写机 `NOT_RUN`（无 Docker）；操作者在 Linux 构建 0050 Dockerfile，再以静态包清单事实、容器内 doctor 预检及 `mediasync` Chromium 启动为门 | 阶段 B，第一发布阻塞项 |
| 容器健康 / 重启持久性 / 备份恢复演练 | `NOT_RUN`——操作者（阶段 B） | docs/operations.md 流程就绪 |
| 真人登录（任一平台） | `NOT_RUN`——操作者（阶段 C 金丝雀：Bilibili + 小红书） | 执行 0047 |
| 真人抓取 / 下载 / 增量性 | `NOT_RUN`——操作者（阶段 C–E） | 执行 0047 |
| 真实 Emby/Jellyfin 重扫 + 播放 | `NOT_RUN`——Supported 等级的强制项（阶段 E/F） | 执行 0047 验收规则 |
| 外部安全审计 | `NOT_RUN`——可选 | docs/security-review.md 残余风险 |

## 发布阻塞项（v0.1.0-rc1）

1. Linux 主机基线未完成（镜像构建、健康、重启持久性、备份恢复演练）——阶段 B。
2. 真人行零记录——阶段 C 金丝雀（Bilibili + 小红书）先行，随后其余平台。

0.1 最低发布条件：至少两个金丝雀平台达到 **Supported**（登录、同步、下载、真实增量、Emby 重扫 + 抽样播放），其余平台如实分级（Experimental / Metadata-only / Blocked External / Unsupported），且项目自我表述为“七平台适配框架；实际资格状态见状态矩阵”，而非“支持七个平台”。
