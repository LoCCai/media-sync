[English](verification.md) | **中文**

# 执行 0041 验证

- 状态：打包编排完成并通过静态校验；Docker 构建与全部真人在操作者的 Linux 主机执行
- 日期：2026-09-03

## 已实现证据

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 打包文件齐备且一致 | `Dockerfile`、`docker/entrypoint.sh`、`docker-compose.yml`、`.dockerignore`、`docs/deployment.md`、`docs/deployment.zh.md` | 0 | 入口脚本可执行位已提交；compose 只引用存在的命令（`serve`、`scheduler supervise --idle-interval-seconds`） |
| 上游提交钉与锁一致 | `grep MEDIACRAWLER_COMMIT Dockerfile` 对照 `upstreams.lock.json` | 0 | 均为 `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` |
| 文档链接 | `uv run python scripts/check_docs.py` | 0 | `342 Markdown files checked`（含两份部署文档） |
| 静态门（与 0039/0040 共享） | mypy strict、ruff check/format、compileall | 0 | 本工作站全部通过 |

## Linux 操作者清单（执行后回填）

| 验收行 | 命令 | 结果 |
| --- | --- | --- |
| 镜像构建 | `docker compose build` | 本工作站 `NOT_RUN` |
| 服务启动与健康 | `docker compose up -d` → `curl http://127.0.0.1:8632/api/v1/health` | 本工作站 `NOT_RUN` |
| 完整套件（部署前） | `uv sync --all-groups --locked && uv run pytest -q` | 本工作站 `NOT_RUN` |
| 控制台真人扫码登录 | 控制台弹窗 + `login-status` | 执行前保持 `NOT_RUN` |
| 真人创作者抓取 | 带双门禁的 scheduler run | 执行前保持 `NOT_RUN` |
| 真实媒体下载 + Emby 目录 | pipeline run + `/data/library` 列表 | 执行前保持 `NOT_RUN` |

本执行只声明打包与文档；所有真人行在操作者记录实际证据前保持 `NOT_RUN`。
