[English](progress.md) | **中文**

# 进展：部署来源身份与 XHS 金丝雀预检

状态：本地实现已在 `d6db86a` 完成。本次没有执行 Docker/Linux 部署、数据库修改、平台请求、Subscription 执行或 supervisor 重启。

## 结果

部署现在可以识别镜像中构建的精确 media-sync 源码 revision，并把该身份与数据库当前/预期 migration、B 站/XHS 实际续跑间隔一并展示。同一份无秘密 deep-readiness 报告同时提供给经认证的 Web/API 和 `media-sync doctor --deep`，因此可在恢复任何工作负载前分别检查 API 与 supervisor 服务定义。

缺少来源身份始终是显式 `not_run`；畸形或重复来源身份是 `fail`，且绝不回显原值。这些证据状态既不阻塞普通服务启动，也不授予真人资格。

## 已实现

1. **镜像身份。** Docker 接收 `MEDIA_SYNC_SOURCE_REVISION`，只允许一个完整 40 字符小写 Git SHA 或 `unavailable`，写入 `/opt/BUILD-MANIFEST.txt`，并发布为 OCI `org.opencontainers.image.revision` 标签。项目自身 `.git` 继续位于构建上下文之外。
2. **封闭清单解析。** Deep readiness 公开经过验证的 `source_revision` 与 `source_revision_status`。缺少清单为 `not_run`；缺少该行或精确 `unavailable` 哨兵时来源状态为 `not_run`；畸形及重复值为 `fail`，且不反射输入。
3. **Migration 事实。** 封闭 `0001..0015` 集合中的单个已打包 migration 即使过旧也可见；未知、缺失或多 revision 会被隐藏。只有精确匹配 `0015_xhs_creator_notes` 才是 current。
4. **实际节奏。** 报告只增加运行进程中经过配置校验的 B 站与 XHS 整数续跑间隔。它们用于比较 API/supervisor 配置，不会请求调度工作。
5. **操作员界面。** 诊断页在既有紧凑事实面板中显示应用 SHA、migration 一致性及两个续跑间隔。前端对旧响应缺失字段或畸形后端值安全关闭。`doctor --deep --accept-mediacrawler-license --json` 输出同一报告，并在 readiness 阻塞时返回非零状态。
6. **Compose 交接。** 跟踪的示例以 `unavailable` 为默认值透传源码 revision，并记录如何取得精确 checkout SHA；旧镜像或私有构建不会仅因缺少来源身份而无法运行。

## 收尾修正

- 最终复核发现第一版只通过 API/Web 暴露共享报告，但冻结计划要求可独立检查 supervisor。最终完整套件前已补显式 deep `doctor` 路径，以及通过/阻塞 CLI 测试。
- 数据库投影保持白名单：已知旧 migration 是有用证据，但任意数据库文本不得显示。
- 来源、migration 与续跑值在显示前分别校验；异常后端字符串不会变成操作员可见诊断内容。

## 待完成

- 当前 Windows 工作站没有 Docker。Dockerfile 实际执行、镜像标签读取、最终 runtime UID/挂载行为及 API/supervisor 容器比较仍为 `NOT_RUN`。
- 当前服务器尚未从本 revision 重建。必须按[部署交接](deployment-handoff.zh.md)检查精确镜像身份、migration `0015`、钉定 checkout、续跑配置一致性、重启行为和持久挂载。
- 真人 XHS 登录/profile 认领、作者 API、CDN 下载、宿主 archive/library/NFO 字节、重放、重启续跑及一次驻留 supervisor 周期仍为 `NOT_RUN`。
- 真实 PostgreSQL 与可选 Emby/Jellyfin 读取仍为 `NOT_RUN`。生成兼容本地目录无需媒体服务器 API 连接。
- XHS 金丝雀形成独立证据记录或明确阻塞前，不开始抖音交付。原始七平台目标继续有效。
