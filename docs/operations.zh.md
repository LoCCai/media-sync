[English](operations.md) | **中文**

# 运维：备份、恢复与升级

适用于 [`deployment.zh.md`](deployment.zh.md) 的 Docker compose 部署。全部持久状态位于挂载在 `/data` 的 `media-sync-data` 卷：

| 路径 | 内容 | 备份价值 |
| --- | --- | --- |
| `/data/state/media-sync.sqlite3` | 数据库：账户、订阅、内容、资产、任务、导出记录 | 关键（含凭据*引用*，绝无原始机密） |
| `/data/archive/` | 不可变 SHA-256 媒体 blob | 关键（丢失只能全量重新下载） |
| `/data/library/` | Emby/Jellyfin 目录（NFO、海报、剧集） | 可再生成（由数据库 + 归档重新导出） |
| `/data/jobs/`、`/data/mediacrawler/` | 工作根、manifest、浏览器 profile | 可丢弃；profile 丢失意味着需要重新登录 |

## 备份

离线（先停服务，最简单且始终一致）：

```bash
docker compose stop
docker run --rm -v media-sync_media-sync-data:/data -v "$PWD/backup:/backup" alpine \
  tar czf /backup/media-sync-data-$(date +%F).tgz -C /data .
docker compose start
```

> 卷名为 `<项目名>_media-sync-data`；若你的克隆目录名不同，先用 `docker volume ls | grep media-sync` 确认。

在线（服务运行中使用容器内 SQLite 标准库 backup API，保证一致性）：

```bash
docker compose exec media-sync /app/.venv/bin/python -c \
  "import sqlite3; src=sqlite3.connect('/data/state/media-sync.sqlite3'); dst=sqlite3.connect('/data/state/backup.sqlite3'); src.backup(dst); dst.close()"
# 然后按上述方式把 /data/state/backup.sqlite3 与 archive/ 一并拷出
```

## 恢复

1. 停止服务：`docker compose stop`。
2. 把归档恢复进新卷（或覆盖现有卷）：

```bash
docker volume create media-sync_media-sync-data
docker run --rm -v media-sync_media-sync-data:/data -v "$PWD/backup:/backup" alpine \
  sh -c "tar xzf /backup/media-sync-data-日期.tgz -C /data"
```

3. 重新启动：`docker compose up -d`。入口脚本会执行 `media-sync db init`，幂等地应用未完成的迁移；恢复到较旧 revision 的数据库会自动升级。
4. 验证：`curl -fsS http://127.0.0.1:8632/api/v1/ready`，控制台能看到账户/订阅；需要深度确认时抽查一个归档文件的 SHA-256。

如果只丢了数据库（归档完好），仅恢复 `state/` 即可；资产会对照既有 blob 重新验证，不需要重新下载。如果 `mediacrawler/` 下的浏览器 profile 丢失，账户记录仍是 `saved_session`，但上游会话需要逐账户重新扫码建立。

## 升级

```bash
cd /www/wwwroot/docker/media-sync     # 你的克隆
git pull
cp -f docker-compose.example.yml docker-compose.yml   # 仅当模板有变且你本地无自定义修改时
docker compose build
docker compose up -d
```

schema 迁移在容器启动时运行（`db init` 幂等）。`uv.lock` 保证与发布时测试相同的依赖组合。本地 `docker-compose.yml` 被 git 忽略，上游更新不会与你的部署配置冲突。版本回退：`git checkout <旧 tag 或 SHA>` 后重新构建——数据库 downgrade 不会自动执行，降级前先看发布说明。
