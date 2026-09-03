[English](goal.md) | **中文**

# 执行 0041 目标

- 状态：打包交付；构建与真人验收在操作者的 Linux 主机执行
- 日期：2026-09-03
- 前置：执行 0040 实现（同一工作会话）
- 范围：单一 Docker 镜像与 compose 布局，运行 media-sync、Web 控制台与锁定 MediaCrawler 运行时，支撑操作者驱动的扫码登录与订阅下载验证

## 目标结果

1. `Dockerfile` 构建两层：应用 venv（`/app/.venv`）与按 `upstreams.lock.json` 记录 SHA 锁定的 MediaCrawler checkout（`/opt/mediacrawler` + 独立 venv + Playwright Chromium，位于 `/opt/mediacrawler-venv`），并内置 `ffmpeg`、`Xvfb`、中文字体与 curl 健康检查。
2. `docker/entrypoint.sh` 在 `:99` 启动 Xvfb（子进程环境白名单本就含 `DISPLAY`/`XAUTHORITY`），幂等执行 `db init`，然后 exec 目标命令。
3. `docker-compose.example.yml` 以模板形式交付：操作者复制为被 git 忽略的 `docker-compose.yml` 后自由修改，上游更新绝不与本地部署配置冲突。它仅发布 `127.0.0.1:8632:8632`，全部状态位于 `media-sync-data` 卷（`/data`），并提供可选 `supervisor` profile 运行带双重 MediaCrawler 门禁的 `scheduler supervise`。
4. 双语部署文档（`docs/deployment.md` / `.zh.md`）覆盖 构建 → 控制台扫码登录 → 订阅 → 同步/pipeline → Emby 媒体库，并附如实验收清单。

## 验收边界

- 不发布、不再分发镜像：上游非商业许可证禁止；镜像由操作者本地构建。
- 控制台/API 保持无鉴权；compose 默认绝不把端口暴露到宿主机回环之外。
- 全部真人行（扫码登录、抓取、下载、媒体服务器）由操作者在 Linux 执行并记录；本仓库只记录打包与说明。

## 明确延期

CI 流水线、多架构构建、HTTPS/反向代理指南与任何远程鉴权形式仍为后续工作。
