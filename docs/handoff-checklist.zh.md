[English](handoff-checklist.md) | **中文**

# 操作者速查清单：重建、证明身份、跑一次 XHS 金丝雀

从[部署交接文档](executions/0077-deployment-provenance-preflight/deployment-handoff.zh.md)浓缩的可勾选工作清单。交接文档仍为权威；有疑问以它为准。在 Linux 主机执行。所有无关订阅保持暂停。

## 0）准备

- [ ] 对 SQLite 数据库、托管凭据和整个 `/data` 做应用一致性备份（见[运维指南](operations.zh.md)）；私有 Compose 文件与操作者机密单独保存。
- [ ] 已阅读并确认 MediaCrawler 非商业学习许可证。
- [ ] 反向代理与精确 HTTPS origin 不变。
- [ ] 停止 supervisor：`docker compose --profile supervisor stop supervisor`。

## 1）拉取并绑定精确源码

```bash
git fetch origin && git checkout main && git pull --ff-only origin main
test -z "$(git status --porcelain)"
export MEDIA_SYNC_SOURCE_REVISION="$(git rev-parse HEAD)"
sh scripts/fetch_mediacrawler.sh
python3 scripts/check_upstreams.py
```

- [ ] 私有 `docker-compose.yml` 的 `services.media-sync.build.args` 含 `MEDIA_SYNC_SOURCE_REVISION: ${MEDIA_SYNC_SOURCE_REVISION:-unavailable}`。
- [ ] `MEDIA_SYNC_XHS_SCAN_CONTINUATION_DELAY_SECONDS`（及 B 站续跑延迟）在 `media-sync` 与 `supervisor` 中同值；两个服务的 state/archive/library/jobs/mediacrawler 挂载一致。

## 2）构建并证明镜像身份

```bash
docker compose config >/dev/null
docker compose build --no-cache media-sync
test "$(docker image inspect media-sync:local --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}')" = "$MEDIA_SYNC_SOURCE_REVISION"
docker compose run --rm --no-deps --entrypoint /app/.venv/bin/media-sync media-sync serve --check-config
docker compose up -d --no-deps --force-recreate media-sync
docker compose ps media-sync && docker compose logs --tail=100 media-sync
```

- [ ] OCI revision 标签等于 `$MEDIA_SYNC_SOURCE_REVISION`（上面的 `test` 不等即非零退出——这是停止条件）。
- [ ] 启动已应用迁移 `0015_xhs_creator_notes`（正因如此备份必须先于重建）。
- [ ] 许可证环境变量变更用 `--force-recreate` 生效；普通 `restart` 不会替换环境。

## 3）比对 API 与 supervisor 预检

- [ ] 控制台 → Diagnostics → 刷新：完整 media-sync SHA、当前/期望迁移、B 站/XHS 续跑延迟、锁定上游 SHA、固定检查状态。
- [ ] 两种服务定义识别同一 SHA 与 `0015`：

```bash
docker compose run --rm --no-deps --entrypoint /app/.venv/bin/media-sync media-sync \
  doctor --deep --accept-mediacrawler-license --json
docker compose --profile supervisor run --rm --no-deps --entrypoint /app/.venv/bin/media-sync supervisor \
  doctor --deep --accept-mediacrawler-license --json
```

- [ ] `live_qualification: NOT_RUN` 是预期值；任何 CLI 非零退出都是停止条件。

## 4）一次有界 XHS 金丝雀

1. [ ] supervisor 保持停止；经鉴权的 `/crawler/` → 一次授权的 XHS 原生登录；等进程空闲。
2. [ ] 账户页 → 把保存的 profile 显式认领到一个匹配的 XHS Account。
3. [ ] 用精确受保护创作者 URL 建一个暂停的低量订阅；只恢复它；调用一次精确手动投递。
4. [ ] 确认一个来源页单元、保留的页尾状态、精确 Job/Run/pipeline 归属、固定的 partial/blocked 错误码、日志中无机密值。
5. [ ] 通过宿主挂载检查真实下载字节、SHA-256 归档、XHS 目录/NFO 输出（无需媒体服务器 API）。
6. [ ] 跑一次有界续跑 → 无重复发布；重启 API 一次 → 同一耐久状态恢复。
7. [ ] 以上全部通过后才启动 supervisor 并观察一次调度续跑；有任何含糊立即停止。

## 5）停止条件

源码/迁移/配置不匹配、checkout 失败、认证含糊、创作者不匹配、意外扫描范围、token/cursor 泄露、访问受限、目录权限错误、无法解释的 Job/Run 分歧。不要自动重试受限账户；不要恢复无关订阅。

## 6）记录

建立双语资格记录：部署的完整 SHA、时间戳、脱敏身份、安全 CLI/UI 证据、有界目录树事实、明确的 `PASS`/`FAIL`/`NOT_RUN` 行。绝不凭预期修改已入库的真人矩阵。

## 排查速查表（操作者体验）

| 症状 | 可能原因 | 处置 |
| --- | --- | --- |
| `/crawler/api/crawler/qrcode` 一直 404 | 平台登录弹窗未弹 / 二维码选择器失败（抖音已知脆弱，上游自身建议用 Cookie） | 看 `/crawler/` 页日志区找 `login qrcode not found`；抖音改走 Cookie 粘贴（账户页，0065 流程） |
| 二维码出现后又 404 | 180 秒时效过期 | 重新发起登录并立即打开二维码；保持页面轮询 |
| `docker compose logs` 里"没有日志" | crawler 子进程输出被接管进 `/crawler/` 页的内存日志面板，不进 Docker 日志 | 运行期间读 `/crawler/` 日志区；media-sync 自身子进程诊断在控制台 → 日志 |
| 下载到哪了 | 三层：`/data/mediacrawler/webui-output`（爬虫原始转储）、`/data/archive`（校验过的 SHA-256 正本）、`/data/library`（Emby/Jellyfin 树） | `docker compose exec media-sync ls /data/archive /data/library` |

## 后续工作

XHS 金丝雀通过（或记录了阻塞原因）之后：追踪锁定抖音创作者作品源码并冻结独立投递契约。此前不授权任何抖音实现。
