[English](progress.md) | **中文**

# 执行 0041 推进结果

- 状态：打包交付；构建与真人清单由操作者在 Linux 执行
- 日期：2026-09-03

## 已完成

- `Dockerfile`（python:3.12-slim-bookworm 基底；`uv sync --locked --no-dev` 应用 venv；MediaCrawler 按锁定提交 `d6f7c5b…` 克隆并配置独立 venv、requirements 与 `playwright install --with-deps chromium`；ffmpeg/Xvfb/xauth/中文字体；非 root `mediasync` 用户；curl 健康检查；`MEDIACRAWLER_COMMIT` 构建参数）。
- `docker/entrypoint.sh`（Xvfb `:99`、`media-sync db init`、exec CMD）与 `.dockerignore`。
- `docker-compose.yml`：仅回环发布端口、`media-sync-data` 卷、Chromium 所需 1 GB `/dev/shm`、健康检查、可选 `supervisor` profile（`scheduler supervise --enable-mediacrawler --accept-mediacrawler-license --idle-interval-seconds 30`）。
- 双语 `docs/deployment.md` / `docs/deployment.zh.md` 附操作者验收清单。

## 偏差与决策

- 按操作者指示，未在 Windows 工作站尝试镜像构建；Docker 构建与全部真人在 Linux 主机执行并记录（本记录有意将这些行保持 `NOT_RUN`）。
- 镜像级设置 `DISPLAY=:99`；登录子进程环境白名单本就包含它，桥接代码无需为显示做任何改动。

## 待完成

- 操作者：`docker compose build` / `up -d`，在容器内或旁边运行完整测试套件，执行控制台扫码登录 + 订阅 + 同步 + pipeline + Emby 检查，并如实记录结果。
