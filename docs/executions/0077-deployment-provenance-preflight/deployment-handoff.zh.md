[English](deployment-handoff.md) | **中文**

# 部署交接：先识别镜像，再执行一个 XHS 金丝雀

## 状态

**仅计划由操作者执行。** 本交接不授权本地收尾修改服务器、启动 supervisor、登录、采集或下载。等 GitHub 推送可见后，再在 Linux 宿主执行；保持全部无关 Subscription 暂停。

## 前置条件

- 保存应用一致的 SQLite 数据库、托管凭据及全部持久化 `/data` 备份；私有 Compose 文件与外部操作者秘密另行保存。遵循仓库[运维指南](../../operations.zh.md)。
- 设置 API 或 supervisor 的许可证确认前，先核对精确锁定版 MediaCrawler 非商业学习许可证。
- 保留部署已使用的反向代理和精确 HTTPS origin。不要整体覆盖私有 Compose 文件，应有意识地合并新增跟踪字段。
- 重建或检查第一次金丝雀前停止 supervisor：

```bash
docker compose --profile supervisor stop supervisor
```

## 拉取并绑定精确源码

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
test -z "$(git status --porcelain)"
export MEDIA_SYNC_SOURCE_REVISION="$(git rev-parse HEAD)"
printf 'media-sync source: %s\n' "$MEDIA_SYNC_SOURCE_REVISION"
sh scripts/fetch_mediacrawler.sh
python3 scripts/check_upstreams.py
```

私有 Compose 必须在 `services.media-sync.build.args` 下包含：

```yaml
MEDIA_SYNC_SOURCE_REVISION: ${MEDIA_SYNC_SOURCE_REVISION:-unavailable}
```

`media-sync` 与 `supervisor` 的 `MEDIA_SYNC_XHS_SCAN_CONTINUATION_DELAY_SECONDS` 必须一致；B 站续跑间隔同样处理。两个服务中的 `/data/state`、`/data/archive`、`/data/library`、`/data/jobs` 与 `/data/mediacrawler` 必须来自同一持久挂载。

## 构建并证明镜像身份

```bash
docker compose config >/dev/null
docker compose build --no-cache media-sync
test "$(docker image inspect media-sync:local --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}')" = "$MEDIA_SYNC_SOURCE_REVISION"
docker compose run --rm --no-deps --entrypoint /app/.venv/bin/media-sync media-sync serve --check-config
docker compose up -d --no-deps --force-recreate media-sync
docker compose ps media-sync
docker compose logs --tail=100 media-sync
```

普通启动可能应用 migration `0015_xhs_creator_notes`，因此备份必须早于重建。健康检查或 `serve --check-config` 成功都不能证明应用身份、数据库当前、爬虫 checkout 或真人登录。

## 比较 API 与 supervisor 预检

登录主控制台，打开诊断页强制刷新，只记录安全字段：完整 media-sync SHA、当前/预期 migration、B 站/XHS 续跑间隔、钉定上游 SHA 与固定检查状态。随后在不启动两个驻留进程的前提下，分别使用两个服务定义运行同一报告：

```bash
docker compose run --rm --no-deps --entrypoint /app/.venv/bin/media-sync media-sync \
  doctor --deep --accept-mediacrawler-license --json
docker compose --profile supervisor run --rm --no-deps --entrypoint /app/.venv/bin/media-sync supervisor \
  doctor --deep --accept-mediacrawler-license --json
```

只有两份报告都识别 `$MEDIA_SYNC_SOURCE_REVISION`、当前/预期均为 `0015_xhs_creator_notes`、显示预期且相等的续跑值，并且钉定 checkout/runtime/browser 合格，才能继续。`live_qualification: NOT_RUN` 是预期值。CLI 非零退出是停止条件，不是绕过检查的许可。

## 一个有界 XHS 金丝雀

1. supervisor 继续停止时，在经认证的 `/crawler/` 为一个获授权 XHS 账户完成原生登录，并等待其进程空闲。
2. 把保存 profile 显式认领给一个匹配的 XHS Account。证据文档绝不粘贴 Cookie、token、profile 路径或不透明 cursor。
3. 使用精确受保护作者 URL 创建一个已暂停、低流量作者 Subscription。只恢复该订阅，并执行一次精确手动交付。
4. 确认一个来源页面单元、页尾保留状态、精确 Job/Run/pipeline 所有权、固定 partial/blocked 代码，且 API 与滚动日志中没有秘密值。
5. 通过宿主挂载检查真实下载字节、SHA-256 归档，以及已配置 XHS 目录/NFO/sidecar。无需 Emby/Jellyfin API 连接。
6. 执行一次有界续跑，确认没有重复发布；重启一次 API，并证明从同一耐久状态恢复。
7. 仅在上述检查通过后启动 supervisor，观察一次调度续跑。任何证据含糊时再次停止。

## 停止与记录

遇到源码/migration/配置不一致、checkout 失败、认证含糊、作者不匹配、意外扫描范围、token/cursor 泄露、访问限制、目录权限错误或无法解释的 Job/Run 分叉时停止。不要自动重试受限账户，也不要恢复无关订阅。

新建一份双语资格记录，包含部署完整 SHA、时间戳、脱敏身份、安全 CLI/UI 证据、有界目录树事实，以及明确 `PASS`/`FAIL`/`NOT_RUN` 行。不得根据预期修改仓库中的真人矩阵。

## 后续工作

XHS 金丝雀通过或形成明确阻塞原因后，先追踪钉定抖音作者作品源码，并为分页、`has_more`/cursor、aweme 身份、详情/媒体权限、页尾保留及风控行为冻结独立交付契约。不得复制 B 站页码或 XHS token 语义。本交接不授权任何抖音实现。
