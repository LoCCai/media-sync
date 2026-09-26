[English](deployment-2026-09-12.md) | **中文**

# 部署记录：精确身份重建达到深度就绪（2026-09-12）

## 状态

**部署身份完成；XHS 金丝雀仍为 NOT_RUN。** Linux 服务器按[部署交接](deployment-handoff.zh.md)执行，supervisor 全程未启动。一个 API 容器在精确发布的源码上完成重建与重建实例。未发生平台登录、采集、下载、Subscription 变更或 supervisor 启动。

## 已执行动作

| 步骤 | 结果 |
| --- | --- |
| 重建前备份 | 应用一致的 SQLite 备份（638,976 字节）、`/data` 全量卷快照（114 MiB）、私有 Compose 文件、`.env` 与操作员密钥目录，已复制到 `/root/media-sync-backups/2026-09-12-pre0077-rebuild` |
| 源码绑定 | fast-forward 拉取到 `3c31dce81f7240ea0c63a6309c04970c1b0741b4`；`git status --porcelain` 为空；SHA 导出为 `MEDIA_SYNC_SOURCE_REVISION` |
| 上游校验 | `scripts/fetch_mediacrawler.sh`：预取检出已处于 `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`；`scripts/check_upstreams.py`：`Upstreams OK (2 locked checkouts verified)` |
| 私有 Compose 合并 | 在 `services.media-sync.build.args` 下审慎新增一个字段：`MEDIA_SYNC_SOURCE_REVISION: ${MEDIA_SYNC_SOURCE_REVISION:-unavailable}`；未改动其他部署字段 |
| 镜像构建 | `docker-compose build --no-cache media-sync`，约 23.5 分钟后以退出码 `0` 完成，镜像 `sha256:993669809891…f27e05928` 标记为 `media-sync:local` |
| 身份证明 | OCI 标签 `org.opencontainers.image.revision` 等于导出 SHA；`/opt/BUILD-MANIFEST.txt` 记录相同 `source_revision` |
| 预检配置 | 通过 API 服务定义运行 `media-sync serve --check-config`：`{"service":"media-sync-api","configuration":"valid"}`，退出码 `0` |
| 容器重建 | `docker-compose up -d --no-deps --force-recreate media-sync`；容器于 `2026-09-12T08:39:48Z` 启动，Docker 健康 `healthy`；带公网代理 Host 的回环 `GET /api/v1/health` 返回 `200 {"status":"ok"}` |
| 数据库迁移 | 启动时应用 schema 升级；深度报告显示 `revision = expected = 0015_xhs_creator_notes`、`revision_current: true`、25/25 必需表 |

## 深度报告对比（双服务定义）

`media-sync doctor --deep --accept-mediacrawler-license --json` 分别在 `media-sync` API 定义与 `supervisor` profile 定义下各运行一次，均未启动任何常驻进程。两次均退出 `0` 且 `ok: true, code: ready`；所有对比字段一致：

| 字段 | API | Supervisor |
| --- | --- | --- |
| `build_manifest.source_revision` | `3c31dce81f7240ea0c63a6309c04970c1b0741b4`（`pass`） | 相同 |
| 数据库 revision / 预期 | `0015_xhs_creator_notes` / `0015_xhs_creator_notes` | 相同 |
| `continuations.bili_delay_seconds` | `300` | `300` |
| `continuations.xhs_delay_seconds` | `300` | `300` |
| `mediacrawler.upstream_sha` | `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` | 相同 |
| MediaCrawler 检查 | 全部 10 项 `pass`（许可证、锁、路径、仓库根、必需文件、许可证摘要、revision、tracked 文件、干净工作树、runtime） | 相同 |
| 浏览器 | Chromium `151.0.7922.34`，`pass` | 相同 |
| 工具 / 路径 | git、ffmpeg、ffprobe、Xvfb `pass`；state、archive、export、jobs、mediacrawler runtime `pass` | 相同 |
| 安全 | `warn` `api_not_loopback`（`0.0.0.0:8632`，需操作员复核）——HTTPS 反向代理后的既有已知状态 | 相同 |
| `live_qualification` | `NOT_RUN` | `NOT_RUN` |

## 明确结果行

| 检查 | 结果 |
| --- | --- |
| 重建前数据库、`/data`、Compose 与密钥备份 | PASS |
| 精确发布 SHA 的干净工作树与 revision 导出 | PASS |
| 钉定上游 checkout/runtime 校验 | PASS |
| 带 SHA 构建参数的无缓存重建 | PASS |
| OCI revision 标签与 `/opt/BUILD-MANIFEST.txt` 一致 | PASS |
| `serve --check-config` | PASS |
| 容器健康与回环 API 探活 | PASS |
| 数据库 migration 时效性（`0015_xhs_creator_notes`） | PASS |
| B 站/XHS 续跑间隔跨定义一致 | PASS |
| API 与 supervisor 深度报告对比 | PASS |
| 网络边界复核（`api_not_loopback`） | WARN（已知且未变化；反向代理部署） |
| 有界 XHS 金丝雀（登录、认领、投递、CDN、NFO、重启） | NOT_RUN——操作员门槛 |
| 常驻 supervisor 周期 | NOT_RUN——有意未启动 |
| 浏览器 Diagnostics 复查 | NOT_RUN——CLI 深度报告与 Diagnostics 页面共享同一安全证据集；未开启浏览器会话 |

## 有界宿主事实

`/data` 顶层目录仍为 `archive`、`jobs`、`library`、`mediacrawler`、`state`，位于同一个持久命名卷；路径布局未变化。旧镜像 `f4a1241c2f26…`（revision 标签 `unavailable`）仍保留在宿主机上作为未标记的回滚镜像。

## 决策

按交接文档，当前部署已证明其精确应用身份、当前 migration、跨定义一致的续跑值与健康的钉定 checkout/runtime，因此解锁有界 XHS 金丝雀。该金丝雀仍属操作员工作：通过 `/crawler/` 完成一次授权的原生 XHS 登录、显式 Account 认领、一个暂停的低量创作者 Subscription、一次精确手动投递，随后进行重启/supervisor 观察。未开始任何抖音投递工作。
