[English](operations.md) | **中文**

# 运维：备份、恢复与升级

适用于 [`deployment.zh.md`](deployment.zh.md) 的 Docker compose 部署。全部由应用管理的持久状态位于挂载在 `/data` 的 `media-sync-data` 卷：

| 路径 | 内容 | 备份价值 |
| --- | --- | --- |
| `/data/state/media-sync.sqlite3` | 数据库：账户、订阅、内容、资产、任务、导出记录、持久 Operation/Event，以及 revision `0008` 播放证据账本 | 关键（含平台账户凭据*引用*，以及任何由 UUID/摘要/时间戳表达的显式播放确认关联；绝无原始机密、远端 item ID、操作者凭据/session 或媒体服务器 key/reference） |
| `/data/archive/` | 不可变 SHA-256 媒体 blob | 关键（丢失只能全量重新下载） |
| `/data/library/` | Emby/Jellyfin 目录（NFO、海报、剧集） | 可再生成（由数据库 + 归档重新导出） |
| `/data/jobs/`、`/data/mediacrawler/` | 工作根、manifest、浏览器 profile | 可丢弃；profile 丢失意味着需要重新登录 |

操作者鉴权配置与执行 0054-A 的媒体服务器配置都属于部署配置，不是该卷内的应用数据。必须通过操作者配置与机密管理流程另行保存 `MEDIA_SYNC_OPERATOR_CREDENTIAL_FILE` 指向的宿主机绝对路径、凭据文件本身、非机密环境选择器及外部 `env:` / `file:` / `keyring:` 材料。不得把原始操作者凭据、Bearer token、媒体服务器 API key 或完整私有 secret reference 加入数据库/归档备份、支持包、shell 记录或 Git。浏览器 session 与 CSRF 值只存在于进程内存，按设计既不备份也不恢复。

## 备份

离线（先停服务，最简单且始终一致）：

```bash
docker compose stop
docker run --rm -v media-sync_media-sync-data:/data -v "$PWD/backup:/backup" alpine \
  tar czf /backup/media-sync-data-$(date +%F).tgz -C /data .
docker compose start
```

API 启动后是一个没有浏览器 session 的新进程。此前签发的操作者 Cookie 全部失效；Web 登录客户端交付后，操作者每次重启都需重新鉴权。

> 卷名为 `<项目名>_media-sync-data`；若你的克隆目录名不同，先用 `docker volume ls | grep media-sync` 确认。

在线（服务运行中使用容器内 SQLite 标准库 backup API，保证一致性）：

```bash
docker compose exec media-sync /app/.venv/bin/python -c \
  "import sqlite3; src=sqlite3.connect('/data/state/media-sync.sqlite3'); dst=sqlite3.connect('/data/state/backup.sqlite3'); src.backup(dst); dst.close()"
# 然后按上述方式把 /data/state/backup.sqlite3 与 archive/ 一并拷出
```

SQLite 备份会包含持久 `media-server-probe` / `media-server-scan` 审计行及其白名单证据，包括阶段 B 的作者 target、关联 publication Job 与 accepted/observed checkpoint。在 revision `0008`，它也会包含由仅浏览器确认后端创建或重放的 append-only 播放证据行；这些行只保存规范作者/publication Job 身份、绑定上下文的摘要与服务端时间戳，不保存原始服务器 item ID 或路径。API 响应省略 observation fingerprint 及全部内部上下文摘要。备份中的行记录操作者显式确认，不是远端遥测；qualification 仍为 schema v2 且缺少 current/stale 投影时，它不能授予真人 PASS。备份不包含环境托管的媒体服务器配置、操作者凭据、可选 Bearer token、session Cookie 或 CSRF 值。只通过上述独立机密管理流程备份必要部署输入。

## 恢复

1. 停止服务：`docker compose stop`。
2. 把归档恢复进新卷（或覆盖现有卷）：

```bash
docker volume create media-sync_media-sync-data
docker run --rm -v media-sync_media-sync-data:/data -v "$PWD/backup:/backup" alpine \
  sh -c "tar xzf /backup/media-sync-data-日期.tgz -C /data"
```

3. 恢复或重建被 Git 忽略的部署配置及外部 secret-provider 材料。Compose 启动前，把 `MEDIA_SYNC_OPERATOR_CREDENTIAL_FILE` 导出为示例 secret mount 所需、权限为 `0600` 的凭据文件绝对路径。在核对恢复后的安全摘要、origin、TLS 姿态、网络规则数量和 Library 摘要前，保持 `MEDIA_SYNC_MEDIA_SERVER_OPERATIONS_ENABLED=false`。
4. 重新启动：`docker compose up -d`。入口脚本会执行 `media-sync db init`，幂等地应用未完成的迁移；恢复到较旧 revision 的数据库会自动升级。
5. 用 `curl -fsS http://127.0.0.1:8632/api/v1/ready` 验证有意公开的探针，并确认匿名业务请求得到固定鉴权拒绝；需要深度确认时抽查一个归档文件的 SHA-256。当前 Web bundle 没有登录/CSRF 客户端，因此不能用控制台渲染作为恢复验收，也不能经 Web UI 打开媒体服务器 Operation 门。

如果只丢了数据库（归档完好），仅恢复 `state/` 即可；资产会对照既有 blob 重新验证，不需要重新下载。如果 `mediacrawler/` 下的浏览器 profile 丢失，账户记录仍是 `saved_session`，但上游会话需要逐账户重新扫码建立。

## 升级

```bash
cd /www/wwwroot/docker/media-sync     # 你的克隆
git pull
cp -f docker-compose.example.yml docker-compose.yml   # 仅当模板有变且你本地无自定义修改时
export MEDIA_SYNC_OPERATOR_CREDENTIAL_FILE=/绝对/私有路径/operator-credential.txt
docker compose build
docker compose up -d
```

schema 迁移在容器启动时运行（`db init` 幂等）。`uv.lock` 保证与发布时测试相同的依赖组合。本地 `docker-compose.yml` 被 git 忽略，上游更新不会与你的部署配置冲突。提交 `f19bfaa` 的后端鉴权边界已启用，但 Web login/session bootstrap 与 CSRF 传播仍待实现；在前端检查点收尾前使用 CLI/supervisor 工作流。

数据库一旦包含任一 `media-server-probe` 或 `media-server-scan` 行，revision `0007_media_server_operations` 就是 forward-only。其 downgrade 会有意关闭失败而不是删除持久审计证据，旧应用也不得针对该数据库运行。没有新 kind 行的数据库可以使用经过测试的 downgrade 路径，但 down-migration 从不自动执行。签出旧 tag/SHA 前必须检查发布说明与数据库状态；若已有新 kind 行，应恢复兼容的升级前备份，或继续使用理解 revision `0007` 的应用版本。

执行 0054-B 在历史上没有新增迁移，并结束于 `0007`。执行 0055 把 Alembic 推进到 `0008_playback_evidence`；仅浏览器确认 service 现可通过应用拥有的事务写入该账本。新表在升级时为空，并以 `RESTRICT` 关联作者与 publication Job；应用仓储只暴露 create-or-exact-replay，不暴露 update/delete。只有表为空时，在线 downgrade 才能回到 `0007`。只要存在任一证据行，downgrade 就会以 `playback_evidence_rows_prevent_downgrade` 关闭失败；离线 SQL downgrade 也会被拒绝，因为它无法审计表内容。不得为了回滚而删除证据行；应恢复兼容的 `0008` 前备份，或继续使用理解 `0008` 的二进制。

SQLite 继续是受支持的生产存储。`0008` migration 可生成 SQLite/PostgreSQL DDL，仓储也实现 PostgreSQL 专用 unique-conflict/savepoint 语义及可选隔离三表竞态套件，但该真实 PostgreSQL 套件尚未在本工作站运行；其 Author/Job/PlaybackEvidence fixture 不能证明完整应用 schema、容器部署或生产 PostgreSQL 支持。

跨越历史 `0007` 边界回滚应用版本前，必须等待所有作者观察 scan 进入终态，或部署具备兼容收敛逻辑的版本；不得通过删除 Operation 行或 accepted/observed checkpoint 强行制造兼容。

即使鉴权本身没有新增数据库 revision，它仍是应用回滚边界。不得为了恢复控制台访问而运行旧的匿名 `serve` 二进制；应保持流量停止并部署兼容鉴权的构建。应用不会隐式信任外部代理，任何外置鉴权方案都需要单独审查。
