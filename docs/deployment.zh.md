[English](deployment.md) | **中文**

# Docker 部署与 Web 后台验证

本指南把 media-sync 作为自托管容器部署（内含锁定版本 MediaCrawler 运行时），并全程通过 Web 控制台验证扫码登录与订阅下载。由执行 0040/0041 引入，需要装有 Docker（compose v2）的 Linux 主机。

## 1. 构建

```bash
git clone <你的仓库> media-sync && cd media-sync
cp docker-compose.example.yml docker-compose.yml   # 本地副本已被 git 忽略
docker compose build          # 如需改端口/路径，先编辑你的本地副本
```

镜像包含两层：

| 层 | 位置 | 用途 |
| --- | --- | --- |
| media-sync 应用 venv | `/app/.venv` | 服务本体、CLI、REST API 与内置控制台 |
| 锁定 MediaCrawler checkout | `/opt/mediacrawler`（含独立 venv、Playwright 与 Chromium，位于 `/opt/mediacrawler-venv`） | 按锁文件精确 SHA 运行的许可证门禁登录/抓取子进程 |

`ffmpeg/ffprobe`、`Xvfb`、中文字体与健康检查均已内置。构建时会按锁定 SHA 克隆 MediaCrawler 供你自己非商业使用；不得发布或再分发该镜像。

## 2. 启动服务

```bash
docker compose up -d
```

- Web 控制台：<http://127.0.0.1:8632/>（默认只发布到宿主机回环）。
- REST 文档：<http://127.0.0.1:8632/api/docs>。
- SQLite 状态库、归档、Emby 目录与 MediaCrawler 运行时都在 `media-sync-data` 卷的 `/data` 下。

控制台与 API **没有鉴权** —— 只发布到可信网络。要在内网开放，请编辑你自己的本地 `docker-compose.yml`（从 example 复制而来），把 `127.0.0.1:8632:8632` 改成 `192.168.x.x:8632:8632`，风险自负；example 模板本身保持原样，`git pull` 更新时不会与你的部署配置冲突。

## 3. 控制台扫码登录

1. 打开 <http://127.0.0.1:8632/>，顶栏应显示 `MediaCrawler 已配置` 且两个健康 pill 为绿。
2. 在「平台账户」添加账户：选择平台（如 `bili`）、显示名，登录方式选 `扫码 QR`。
3. 勾选 **启用 MediaCrawler** 与 **我已确认其非商业学习许可证**（即为本部署接受锁定上游许可证）。
4. 点击该账户行的「扫码登录」。弹窗会轮询显示由容器内 Xvfb 有头登录子进程中继出来的二维码图片，180 秒内用平台 App 扫码。
5. 弹窗显示登录结果；账户行应变为 `authenticated`。

若约 20 秒后二维码仍未出现，查看 `docker compose logs media-sync` —— 常见原因是 checkout SHA 不匹配（构建参数）或挑战已过期（重试登录即可）。

## 4. 订阅与下载

1. 在「创作者订阅」选择账户，填写稳定的创作者 ID（B 站为数字 UID）、显示名与较小的单次上限（如 5）。
2. 点击「添加订阅」，再点「立即运行」使其到期。
3. 点击「运行同步 worker」（保持两个 MediaCrawler 开关勾选）—— 运行创作者抓取子进程并导入内容/资产。
4. 点击「运行下载/导出 pipeline」—— 通过签名 locator 刷新下载媒体、按 SHA-256 归档并发布 Emby/Jellyfin 目录。
5. 在「调度任务」与「后台操作记录」观察结果；「媒体资产」列出已下载/已验证资产；媒体库落在卷内 `/data/library`。

如需无人值守链路，改用常驻监督服务：`docker compose --profile supervisor up -d`。

## 5. 将媒体库接入 Emby/Jellyfin

把 `media-sync-data` 卷的 `/data/library` 以只读方式挂给媒体服务器并添加为“剧集”媒体库。NFO、海报与剧集按创作者确定性生成。

## 6. 验收清单（如实记录）

| 验收行 | 证据 |
| --- | --- |
| 真人扫码登录（哪个平台/账户） | 控制台结果 + `login-status` 显示 `authenticated` |
| 创作者抓取（哪个创作者、条数） | 调度任务结果 + 资产计数 |
| 真实媒体下载 | 资产行达到 `verified`/`archived`；`/data/archive` 下出现 SHA-256 文件 |
| Emby 目录发布 | `/data/library` 的作者目录列表 |
| 媒体服务器扫描/播放 | 可选；未执行则记 `NOT_RUN` |

现网证据以实际运行为准；未执行的项一律保持 `NOT_RUN`，遵守项目真实性规则。
