# media-sync

`media-sync` is a local-first author subscription and media archiving service. It is being designed around the platform coverage of [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) and the media-library workflow of [bili-sync-up](https://github.com/NeeYoonc/bili-sync-up).

`media-sync` 是一个本地优先的作者订阅与媒体归档服务。项目目标是覆盖 MediaCrawler 所支持的平台登录与创作者内容抓取，并将图文、视频和元数据整理为 Emby/Jellyfin 可识别的媒体库结构。

## Current status / 当前状态

The core foundation is runnable: packaged Alembic migrations, SQLite repositories, durable leases, account/subscription CLI commands, a deterministic seven-platform-capable test adapter contract, and an idempotent sync pipeline are implemented. The MediaCrawler bridge, real downloads, Emby export, scheduler/API, and user-authorized live qualification remain under active construction. Requirements, capability truth, progress, and exact verification evidence are tracked in [`docs/`](docs/README.md).

核心基线已可运行：已实现随包发布的 Alembic 迁移、SQLite 仓储、持久租约、账户/订阅 CLI、覆盖七个平台标识的确定性测试适配协议，以及幂等同步链路。MediaCrawler 桥接、真实下载、Emby 导出、调度/API 和用户授权的线上验收仍在持续实现。需求、真实能力、进展及准确验证证据均保存在 [`docs/`](docs/README.md)。

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

Only opaque secret references such as `env:MEDIA_SYNC_BILI_COOKIE` or `keyring:media-sync/bili-demo` may be passed to `--credential-ref`; raw Cookie/password values are rejected. Run the complete offline quality gate with `uv run pytest` and see [`docs/executions/0003-core-foundation/verification.md`](docs/executions/0003-core-foundation/verification.md) for the recorded environment and results.

`--credential-ref` 只接受 `env:MEDIA_SYNC_BILI_COOKIE`、`keyring:media-sync/bili-demo` 等不透明引用；原始 Cookie/密码会被拒绝。可用 `uv run pytest` 运行完整离线质量门禁；执行环境与结果记录在 [`docs/executions/0003-core-foundation/verification.md`](docs/executions/0003-core-foundation/verification.md)。

## Scope / 范围

- Platforms / 平台：小红书、抖音、快手、哔哩哔哩、微博、百度贴吧、知乎。
- Authentication / 登录：按平台能力支持二维码、手机号与 Cookie/已保存浏览器会话。
- Subscription / 订阅：保存作者身份、定时增量扫描、去重与失败重试。
- Content / 内容：归一化图文、视频、图片及相关元数据。
- Media library / 媒体库：输出稳定目录、媒体文件、海报/封面和 Emby/Jellyfin NFO。

## Important license boundary / 重要许可证边界

MediaCrawler uses a custom non-commercial learning license. Its checkout is treated as an optional external runtime and is not vendored into this repository. See [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md) before distributing or using this project commercially.

MediaCrawler 使用定制的“非商业学习使用许可证”。本仓库只把它视为可选外部运行时，不把其源码纳入版本历史。分发或商业使用前，请先阅读 [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md)。
