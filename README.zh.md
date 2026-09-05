[English](README.md) | **中文**

# media-sync

`media-sync` 是一个本地优先的作者订阅与媒体归档服务。它把 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 的平台覆盖（作为受许可证门禁的外部采集运行时）与 [bili-sync-up](https://github.com/NeeYoonc/bili-sync-up) 的媒体库工作流结合起来：鉴权创作者订阅、增量采集、可续传的可验证下载、SHA-256 归档与确定性 Emby/Jellyfin 媒体库——运行在一个 Python 模块化单体 + SQLite 之上。

## 当前状态

当前实现和验证以 [`docs/status.zh.md`](docs/status.zh.md) 为准；最新增量是[0064作者资料](docs/executions/0064-douyin-tieba-profiles/progress.zh.md)。源码已支持不等于真实平台验收通过。

| 方面 | 当前范围 |
| --- | --- |
| 本地媒体库 | 归档和Emby/Jellyfin兼容目录独立于可选服务器连接；图文/图集sidecar不等于原生视频播放 |
| 账户与作者 | 五平台粘贴Cookie校验、六平台准确昵称查询；B站/微博/贴吧有可选头像。七平台扫码入口仍需真实环境验收 |
| 订阅与任务 | 可恢复移除订阅保留媒体/历史；平台资料、本地备注、安全Job报告和面向用户的状态/下一步说明已实现 |
| 验证 | 当前精确测试、构建、打包结果、失败与环境跳过见[0064验证](docs/executions/0064-douyin-tieba-profiles/verification.zh.md)，不继承旧测试数 |
| 待实现/验收 | 小红书资料、抖音/快手粘贴本人校验、抖音/快手/知乎头像、剩余媒体形状及当前Linux/平台/归档/播放验收；历史B站采集失败仍未解决 |

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
