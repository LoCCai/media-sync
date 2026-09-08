[English](plan.md) | **中文**

# 计划

状态：**已冻结，等待实现**。本计划只授权本地实现与验证；部署、平台流量、Subscription 执行及 supervisor 控制均不在本执行范围。

## 1. 冻结追加式证据契约

- 为 `build_manifest` 增加 `source_revision: string | null` 与 `source_revision_status: pass | fail | not_run`，保留既有 `status`、`present` 和白名单工具链 `facts` 字段。
- 为 deep readiness 增加 `continuations.bili_delay_seconds` 与 `continuations.xhs_delay_seconds`。数据库对象中既有当前/预期 revision 继续作为 migration 唯一事实来源。
- 所有变化保持追加式，使旧保存响应或没有源码 revision 的旧清单显示为 unavailable，而不是页面崩溃。

## 2. 在镜像中传递源码 revision

- 增加 Docker 构建参数 `MEDIA_SYNC_SOURCE_REVISION=unavailable`，只接受该哨兵或 40 字符完整小写 SHA。
- 把值写入 `/opt/BUILD-MANIFEST.txt` 的 `source_revision:` 行及 `org.opencontainers.image.revision`；继续由 `.dockerignore` 排除 `.git`。
- 在 Compose 中传入该构建参数，并写明合格构建前的简明命令：`export MEDIA_SYNC_SOURCE_REVISION=$(git rev-parse HEAD)`。

## 3. 安全解析与发布

- 仅为测试注入临时清单而做最小 build-manifest 读取重构。
- 完整小写 SHA 为 `pass`，精确哨兵或缺少行是 `not_run`，任何其他已记录值是 `fail`；绝不回显畸形文本。
- 在深度报告增加安全续跑整数。缺少来源身份不阻塞普通运行 readiness，因为它影响证据质量，不是爬虫运行前置条件。

## 4. 显示操作员证据

- 更新共用 TypeScript 类型与诊断页，显示完整源码 revision、清楚的缺失/无效状态、数据库当前与预期 migration，以及两项续跑间隔。
- 复用既有 panel 和紧凑键值行；不嵌套卡片，不暴露路径或秘密。

## 5. 验证与收尾

1. 构建清单解析、报告形状及 API 投影的 Python 专项测试。
2. 新诊断状态的 Web 专项测试，再运行完整 Web、Svelte 检查和生产构建。
3. Dockerfile/Compose 契约测试，断言构建参数、校验、清单行、OCI label 及 `.dockerignore` 边界。
4. 完整 Python、Ruff、strict mypy、compileall、锁文件/上游、制品、文档链接及 `git diff --check`。
5. 编写双语 progress/verification 和部署交接；实现与文档分别使用双语说明提交，只允许快进推送。

收尾时真人部署与 XHS 金丝雀仍保持 `NOT_RUN`。下一操作员动作是拉取已发布 SHA，以该精确 revision 构建，备份 `/data`，重建服务，并在 supervisor 继续停止时重新运行深度 readiness。
