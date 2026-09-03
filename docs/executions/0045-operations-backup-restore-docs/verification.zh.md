[English](verification.md) | **中文**

# 执行 0045 验证

- 状态：文档范围通过全部适用门禁；恢复/升级演练属于部署主机
- 日期：2026-09-03

## 已实现证据

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 文档链接 | `uv run python scripts/check_docs.py` | 0 | 新增运维页与执行记录链接检查通过 |
| 命令存在性审计 | 文档命令逐条对照 `src/media_sync/interfaces/cli.py` + `Dockerfile` | 0 | `db init`/`db status` 存在；无虚构 CLI；在线备份使用镜像内自带的 `sqlite3` 标准库 |
| 卷命名 | `docker-compose.example.yml` 卷键对照文档 `<项目名>_media-sync-data` | 0 | 一致，并附“用 `docker volume ls` 确认”的显式提示 |
| 源码未动 | 暂存集 | 0 | 仅 `docs/**` |

## 操作者行（部署主机）

| 验收行 | 结果 |
| --- | --- |
| 真实数据上的一次备份 → 恢复演练 | 本机 `NOT_RUN`；首次执行在 Linux |
| 一次升级演练（pull → build → up） | 本机 `NOT_RUN`；首次执行在 Linux |
