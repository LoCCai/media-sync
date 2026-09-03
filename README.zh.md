[English](README.md) | **中文**

# media-sync

`media-sync` 是一个本地优先的作者订阅与媒体归档服务。它把 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 的平台覆盖（作为受许可证门禁的外部采集运行时）与 [bili-sync-up](https://github.com/NeeYoonc/bili-sync-up) 的媒体库工作流结合起来：鉴权创作者订阅、增量采集、可续传的可验证下载、SHA-256 归档与确定性 Emby/Jellyfin 媒体库——运行在一个 Python 模块化单体 + SQLite 之上。

## 当前状态

单一事实来源是 [`docs/status.zh.md`](docs/status.zh.md)。执行 0048 边界摘要：

| 维度 | 状态 |
| --- | --- |
| 离线实现 | 冻结于 0039 功能边界 + 0040 API/控制台 + 0044 最小运维端点；弹幕/字幕延期至 0.2 |
| 离线验证 | 编写工作站完整套件：见 [`docs/status.zh.md`](docs/status.zh.md)；已跑 Python 3.11/3.12/3.13 矩阵 |
| REST API + Web 控制台 | 已交付（`media-sync serve`、中文控制台、二维码中继） |
| Docker 打包 | 候选文件 + 可复现加固已交付；**镜像构建/运行仅在操作者 Linux 主机验证** |
| 真人验收 | **全部平台/CDN/Emby 行 `NOT_RUN`**——执行 0047 是操作者协助的最终门 |
| 发布阻塞 | Linux 基线（阶段 B）+ 真人行零记录；见 [`docs/status.zh.md`](docs/status.zh.md) |

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

Docker 部署、Web 控制台扫码登录与七平台资格验收流程见 [`docs/deployment.zh.md`](docs/deployment.zh.md)（构建/运行）、[`docs/operations.zh.md`](docs/operations.zh.md)（备份/恢复/升级）与 [`docs/executions/0047-seven-platform-live-qualification/`](docs/executions/0047-seven-platform-live-qualification/)（带支持等级的验收计划）。API/控制台无鉴权：只保持在回环或可信网络内。

## 范围

- 平台：小红书、抖音、快手、哔哩哔哩、微博、贴吧、知乎（适配框架；逐平台真人状态以资格矩阵为准，不作隐含声明）。
- 登录：显式双重门禁扫码登录、不透明 Cookie 引用、仅后台使用的保存会话；不支持手机号登录。
- 非目标：评论/关键词抓取、番剧/直播媒体、多用户/公网部署。

## 许可证边界

MediaCrawler 使用定制非商业学习许可证。其 checkout 是可选外部运行时，绝不在本仓库内嵌。内嵌它的 Docker 镜像仅供个人本地使用——不得发布或再分发。见 [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md)。
