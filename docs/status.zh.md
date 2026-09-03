[English](status.md) | **中文**

# 项目统一状态（单一事实来源）

边界：执行 0048（发布候选校准）。本表是权威状态视图；逐执行细节见 [`executions/`](README.zh.md)，证据见各验证记录。每次收尾时更新本页。

## 里程碑状态

| 里程碑 | 状态 |
| --- | --- |
| 离线功能开发 | 冻结于 0039 边界（多实况 gallery），外加 0040（API/控制台）与 0044 最小运维端点；0043（弹幕/字幕）延期至 0.2 |
| REST API + Web 控制台 | 已实现（0040、0044 最小集）；运维 UI 强化延期至 0.2 |
| Docker 打包 | 候选文件 + 可复现加固已交付（0041、0048）；镜像构建/运行仅在操作者主机验证 |
| 运维文档 / 安全审查 / 发布清单 | 已交付（0045、0046） |
| 真人验收（最终门） | 开启中——执行 0047，操作者在 Linux 协助执行 |

## 验证矩阵

| 维度 | 状态 | 证据 / 阻塞 |
| --- | --- | --- |
| 实现（离线形状） | 七平台 15+ 冻结形状 | 执行 0013–0039 记录 |
| 离线完整套件 | 编写工作站 ``33 failed, 2031 passed, 1 skipped` (authoring workstation, execution 0048)`；Python 3.11/3.12/3.13 矩阵 `: sync green and suites run on 3.11.16/3.12.14/3.13.15; all 33 divergences are child-process tests failing identically on a clean checkout of that workstation` | 执行 0048 验证；按阶段 B，RC 前必须在 Linux 主机复跑 |
| API/控制台测试 | 已并入完整套件 | 执行 0048 验证 |
| 静态门（ruff/format/mypy/compileall/docs） | 0048 全绿 | 执行 0048 验证 |
| Docker 镜像构建 | 编写机 `NOT_RUN`（无 Docker）；操作者在 Linux 构建 | 阶段 B，第一发布阻塞项 |
| 容器健康 / 重启持久性 / 备份恢复演练 | `NOT_RUN`——操作者（阶段 B） | docs/operations.md 流程就绪 |
| 真人登录（任一平台） | `NOT_RUN`——操作者（阶段 C 金丝雀：Bilibili + 小红书） | 执行 0047 |
| 真人抓取 / 下载 / 增量性 | `NOT_RUN`——操作者（阶段 C–E） | 执行 0047 |
| 真实 Emby/Jellyfin 重扫 + 播放 | `NOT_RUN`——Supported 等级的强制项（阶段 E/F） | 执行 0047 验收规则 |
| 外部安全审计 | `NOT_RUN`——可选 | docs/security-review.md 残余风险 |

## 发布阻塞项（v0.1.0-rc1）

1. Linux 主机基线未完成（镜像构建、健康、重启持久性、备份恢复演练）——阶段 B。
2. 真人行零记录——阶段 C 金丝雀（Bilibili + 小红书）先行，随后其余平台。

0.1 最低发布条件：至少两个金丝雀平台达到 **Supported**（登录、同步、下载、真实增量、Emby 重扫 + 抽样播放），其余平台如实分级（Experimental / Metadata-only / Blocked External / Unsupported），且项目自我表述为“七平台适配框架；实际资格状态见状态矩阵”，而非“支持七个平台”。
