[English](README.md) | **中文**

# media-sync

`media-sync` 是一个本地优先的作者订阅与媒体归档服务。它把 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 的平台覆盖（作为受许可证门禁的外部采集运行时）与 [bili-sync-up](https://github.com/NeeYoonc/bili-sync-up) 的媒体库工作流结合起来：鉴权创作者订阅、增量采集、可续传的可验证下载、SHA-256 归档与确定性 Emby/Jellyfin 媒体库——运行在一个 Python 模块化单体 + SQLite 之上。

## 当前状态

单一事实来源是 [`docs/status.zh.md`](docs/status.zh.md)。当前执行 0055 阶段 A 实现检查点摘要：

| 维度 | 状态 |
| --- | --- |
| 离线实现 | 执行 0054 的功能边界保持不变；执行 0055 现已增加后端单操作者凭据/session/CSRF 边界及可选独立 Bearer 自动化；播放证据与 Web 鉴权集成仍未实现 |
| 离线验证 | 当前执行 0055 后端切片通过 **2811 项测试、14 项跳过、1 个既有 warning**；其中 3 项为 Windows/POSIX 差异，另 11 项因本工作站未配置测试 URL 而跳过真实 PostgreSQL 竞态。190 项 auth/API 专项、69 项 Web 测试、format/check/build、完整静态门、docs/upstreams 与 distribution build 也通过。Web 鉴权与播放证据仍使 0055 总退出门保持开启 |
| REST API + Web 控制台 | 所有非公开后端路由现已在精确 Host 与浏览器 session 或可选 Bearer 鉴权之后关闭失败。SvelteKit 与 `/legacy` 客户端尚未提供登录壳、内存 CSRF 传播或统一过期处理，因此当前不能把 Web 控制台当作可操作的管理界面 |
| Docker 打包 | 示例 Compose 把宿主机提供的操作者凭据挂载为 Docker secret，容器内绑定 `0.0.0.0` 时只显式允许宿主机回环浏览器 origin；0047 Linux 重启/恢复/进程证据仍为 `NOT_RUN` |
| 真人验收 | **全部已实现平台/CDN/媒体服务器真人行保持 `NOT_RUN`**；provider task completion、播放证据及导出后自动扫描是 `NOT_IMPLEMENTED`，不是“尚未运行的真人行” |
| 发布阻塞 | Web 鉴权集成、0055 剩余播放证据切片、Linux 操作者基线及真人行零记录；见 [`docs/status.zh.md`](docs/status.zh.md) |

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

Docker 部署与七平台资格验收流程见 [`docs/deployment.zh.md`](docs/deployment.zh.md)（构建/运行）、[`docs/operations.zh.md`](docs/operations.zh.md)（备份/恢复/升级）与 [`docs/executions/0047-seven-platform-live-qualification/`](docs/executions/0047-seven-platform-live-qualification/)（带支持等级的验收计划）。`media-sync serve` 现在必须先从外部解析操作者凭据才能绑定端口。示例端口应继续只发布到宿主机回环；非回环浏览器 origin 必须使用 HTTPS。当前 Web bundle 尚未接入该后端 session/CSRF 契约，因此请使用 CLI 或常驻 supervisor；0055 前端工作完成前，不得宣称 Web 扫码/登录流程可用。

## 范围

- 平台：小红书、抖音、快手、哔哩哔哩、微博、贴吧、知乎（适配框架；逐平台真人状态以资格矩阵为准，不作隐含声明）。
- 登录：平台账户继续使用显式双重门禁扫码登录、不透明 Cookie 引用与仅后台保存会话；管理后端另有单一进程内操作者 session 及可选独立 Bearer 自动化，但 Web 登录客户端仍待实现。不支持手机号登录。
- 非目标：评论/关键词抓取、番剧/直播媒体、多用户/公网部署。

## 许可证边界

MediaCrawler 使用定制非商业学习许可证。其 checkout 是可选外部运行时，绝不在本仓库内嵌。内嵌它的 Docker 镜像仅供个人本地使用——不得发布或再分发。见 [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md)。
