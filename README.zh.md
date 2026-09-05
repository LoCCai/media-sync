[English](README.md) | **中文**

# media-sync

`media-sync` 是一个本地优先的作者订阅与媒体归档服务。它把 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 的平台覆盖（作为受许可证门禁的外部采集运行时）与 [bili-sync-up](https://github.com/NeeYoonc/bili-sync-up) 的媒体库工作流结合起来：鉴权创作者订阅、增量采集、可续传的可验证下载、SHA-256 归档与确定性 Emby/Jellyfin 媒体库——运行在一个 Python 模块化单体 + SQLite 之上。

## 当前状态

单一事实来源是 [`docs/status.zh.md`](docs/status.zh.md)。当前执行 0055 增量实现检查点摘要：

| 维度 | 状态 |
| --- | --- |
| 离线实现 | 鉴权、revision `0008`／账本、浏览器确认及作者证据／资格 v3 已发布（投影 `2e1949f`）；当前安全 Web login/session/CSRF 与迁移前预检已实现且本地合成浏览器门禁已通过。播放确认 UI 仍待实现 |
| 离线验证 | 当前 Python 为 3155 项通过、22 项跳过、1 个既有 warning（670.16 秒）；Web 9 文件／114 项、Svelte check 零 error/warning 与 build 通过；准确结果见[安全控制台验证](docs/executions/0055-operator-auth-playback-evidence/secure-console/verification.zh.md)；投影 2999 项属于 `2e1949f` 历史门。本工作站 Docker／Linux UID 与真实 PostgreSQL 尚未执行 |
| REST API + Web 控制台 | 安全控制台与启动预检已实现，本地离线与合成浏览器门禁已通过；会话串行初始化、内存 CSRF、退出／过期／401、QR／SSE 已接线。私有页面仅在 session 成功后挂载；`/legacy` 为受保护迁移提示，没有 v2 构建时根页只提示构建／CLI  本地视频只验证加载／解码，未点击播放，不等于真人播放资格 |
| Docker 打包 | 示例 Compose 把宿主机提供的操作者凭据挂载为 Docker secret，容器内绑定 `0.0.0.0` 时只显式允许宿主机回环浏览器 origin；0047 Linux 重启/恢复/进程证据仍为 `NOT_RUN` |
| 真人验收 | **全部已实现平台/CDN/媒体服务器真人行保持 `NOT_RUN`**。Schema v3 将播放证据标为 IMPLEMENTED，只评估显式指定的一个作者；仅重验通过的持久确认可产生该作者范围 PASS。Provider completion 与自动扫描仍为 NOT_IMPLEMENTED |
| 发布阻塞 | 精确当前 Linux 镜像及 Bilibili／小红书获授权金丝雀；P1 确认 UI 不阻塞 CLI 真人流程。见[当前验证](docs/executions/0055-operator-auth-playback-evidence/secure-console/verification.zh.md)与[状态](docs/status.zh.md) |

逐执行细节、证据与准确命令都在 [`docs/executions/`](docs/README.zh.md)——本 README 有意不堆叠执行叙事。

## 离线快速开始（Fake 适配器，无网络）

```powershell
uv sync --all-groups --locked
uv run media-sync db init
uv run media-sync account add --platform bili --display-name local-demo --login-method cookie --json
uv run media-sync subscription add --account-id <ACCOUNT_UUID> --platform bili --creator-remote-id creator-001 --display-name "Fixture Creator" --max-items 30 --json
uv run media-sync scheduler tick --json
uv run media-sync scheduler run --max-jobs 1 --json
uv run media-sync pipeline run --max-jobs 1 --json
```

质量门：`uv run ruff check . && uv run ruff format --check .`、`uv run mypy --strict src`、`uv run pytest -q`、`uv run python scripts/check_docs.py`、`uv run python scripts/check_upstreams.py`（需按 [`docs/upstreams.zh.md`](docs/upstreams.zh.md) 准备 `.upstream/` checkout）。

## 部署与真人验证

Docker 部署与七平台资格验收流程见 [`docs/deployment.zh.md`](docs/deployment.zh.md)（构建/运行）、[`docs/operations.zh.md`](docs/operations.zh.md)（备份/恢复/升级）与 [`docs/executions/0047-seven-platform-live-qualification/`](docs/executions/0047-seven-platform-live-qualification/)（带支持等级的验收计划）。`media-sync serve` 现在必须先从外部解析操作者凭据才能绑定端口。示例端口应继续只发布到宿主机回环；非回环浏览器 origin 必须使用 HTTPS。当前 Web 鉴权已接线，已按[检查点记录](docs/executions/0055-operator-auth-playback-evidence/secure-console/verification.zh.md)通过本地合成浏览器验证；CLI 与常驻 supervisor 继续可用。配置预检不替代当前 Linux 镜像、平台账户或媒体服务器真人资格。

## 范围

- 平台：小红书、抖音、快手、哔哩哔哩、微博、贴吧、知乎（适配框架；逐平台真人状态以资格矩阵为准，不作隐含声明）。
- 登录：平台账户继续使用显式双重门禁扫码登录、不透明 Cookie 引用与仅后台保存会话；管理后端另有单一进程内操作者 session 及可选独立 Bearer 自动化，Web 登录客户端现已实现且本地合成浏览器门禁已通过。不支持手机号登录。
- 非目标：评论/关键词抓取、番剧/直播媒体、多用户/公网部署。

## 许可证边界

MediaCrawler 使用定制非商业学习许可证。其 checkout 是可选外部运行时，绝不在本仓库内嵌。内嵌它的 Docker 镜像仅供个人本地使用——不得发布或再分发。见 [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md)。
