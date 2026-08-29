# media-sync

`media-sync` is a local-first author subscription and media archiving service. It is being designed around the platform coverage of [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) and the media-library workflow of [bili-sync-up](https://github.com/NeeYoonc/bili-sync-up).

`media-sync` 是一个本地优先的作者订阅与媒体归档服务。项目目标是覆盖 MediaCrawler 所支持的平台登录与创作者内容抓取，并将图文、视频和元数据整理为 Emby/Jellyfin 可识别的媒体库结构。

## Current status / 当前状态

The core foundation and credential-safe MediaCrawler bridge are runnable. The bridge verifies the exact pinned checkout, isolates accounts/jobs, keeps secrets out of arguments, manifests, receipts, operator output and SQLite, normalizes fixtures for all seven platform identifiers, and ingests sealed output with restart-safe checkpoint fencing. Real downloads, Emby export, scheduler/API, and user-authorized live qualification remain under construction. Requirements, capability truth, progress, and exact verification evidence are tracked in [`docs/`](docs/README.md).

核心基线与安全凭据的 MediaCrawler 桥接已可运行。桥接会验证精确锁定检出、隔离账户/任务、阻止密钥进入持久落点、归一化七个平台标识的夹具，并通过密封输出和可恢复 checkpoint fencing 导入。真实下载、Emby 导出、调度/API 和用户授权线上验收仍在持续实现。需求、真实能力、进展及准确验证证据均保存在 [`docs/`](docs/README.md)。

## Foundation quickstart / 基线快速开始

The commands below are network-free and use the deterministic Fake adapter. They do not log in to a real platform or prove live platform compatibility.

以下命令无需网络并使用确定性 Fake 适配器；它们不会登录真实平台，也不能作为线上平台兼容性证明。

```powershell
uv sync --all-groups --locked
uv run media-sync db init
uv run media-sync account add --platform bili --display-name local-demo --login-method cookie --json
uv run media-sync account list --json
```

Use the account UUID returned above to create and run the fixture subscription:

使用上一步返回的账户 UUID 创建并运行测试订阅：

```powershell
uv run media-sync subscription add --account-id <ACCOUNT_UUID> --platform bili --creator-remote-id creator-001 --display-name "Fixture Creator" --max-items 30 --json
uv run media-sync subscription list --json
uv run media-sync sync run --subscription-id <SUBSCRIPTION_UUID> --json
```

Only opaque secret references such as `env:MEDIA_SYNC_BILI_COOKIE` or `keyring:media-sync/bili-demo` may be passed to `--credential-ref`; raw Cookie/password values are rejected. Run the complete offline quality gate with `uv run pytest` and see [`docs/executions/0004-mediacrawler-bridge/verification.md`](docs/executions/0004-mediacrawler-bridge/verification.md) for the recorded environment and results.

OS-keyring lookup is optional; install it with `uv sync --extra keyring` before using a `keyring:` reference. Confined `file:<relative-path>` references resolve below `MEDIA_SYNC_SECRET_FILE_DIR` (or the private state-directory default).

`--credential-ref` 只接受 `env:MEDIA_SYNC_BILI_COOKIE`、`keyring:media-sync/bili-demo` 等不透明引用；原始 Cookie/密码会被拒绝。可用 `uv run pytest` 运行完整离线质量门禁；执行环境与结果记录在 [`docs/executions/0004-mediacrawler-bridge/verification.md`](docs/executions/0004-mediacrawler-bridge/verification.md)。

系统钥匙串是可选能力；使用 `keyring:` 引用前请运行 `uv sync --extra keyring`。`file:<relative-path>` 只会在 `MEDIA_SYNC_SECRET_FILE_DIR` 下解析；未配置时使用私有状态目录中的默认位置。

## Scope / 范围

- Platforms / 平台：小红书、抖音、快手、哔哩哔哩、微博、百度贴吧、知乎。
- Authentication / 登录：当前桥接按锁定源码的可达路径支持二维码、Cookie 与已保存浏览器会话；不宣称手机号登录可用。
- Subscription / 订阅：保存作者身份、定时增量扫描、去重与失败重试。
- Content / 内容：归一化图文、视频、图片及相关元数据。
- Media library / 媒体库：输出稳定目录、媒体文件、海报/封面和 Emby/Jellyfin NFO。

## Important license boundary / 重要许可证边界

MediaCrawler uses a custom non-commercial learning license. Its checkout is treated as an optional external runtime and is not vendored into this repository. See [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md) before distributing or using this project commercially.

MediaCrawler 使用定制的“非商业学习使用许可证”。本仓库只把它视为可选外部运行时，不把其源码纳入版本历史。分发或商业使用前，请先阅读 [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md)。
