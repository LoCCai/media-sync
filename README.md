# media-sync

`media-sync` is a local-first author subscription and media archiving service. It is being designed around the platform coverage of [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) and the media-library workflow of [bili-sync-up](https://github.com/NeeYoonc/bili-sync-up).

`media-sync` 是一个本地优先的作者订阅与媒体归档服务。项目目标是覆盖 MediaCrawler 所支持的平台登录与创作者内容抓取，并将图文、视频和元数据整理为 Emby/Jellyfin 可识别的媒体库结构。

## Current status / 当前状态

The project is under active construction. Upstream sources have been pinned; requirements, architecture, capability truth and the implementation roadmap are tracked in [`docs/`](docs/README.md).

项目正在持续实现中。上游源码已经锁定，需求、架构、真实能力矩阵以及分阶段目标、计划、进展和验证记录均保存在 [`docs/`](docs/README.md)。

## Scope / 范围

- Platforms / 平台：小红书、抖音、快手、哔哩哔哩、微博、百度贴吧、知乎。
- Authentication / 登录：按平台能力支持二维码、手机号与 Cookie/已保存浏览器会话。
- Subscription / 订阅：保存作者身份、定时增量扫描、去重与失败重试。
- Content / 内容：归一化图文、视频、图片及相关元数据。
- Media library / 媒体库：输出稳定目录、媒体文件、海报/封面和 Emby/Jellyfin NFO。

## Important license boundary / 重要许可证边界

MediaCrawler uses a custom non-commercial learning license. Its checkout is treated as an optional external runtime and is not vendored into this repository. See [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md) before distributing or using this project commercially.

MediaCrawler 使用定制的“非商业学习使用许可证”。本仓库只把它视为可选外部运行时，不把其源码纳入版本历史。分发或商业使用前，请先阅读 [`docs/decisions/0001-upstream-boundary.md`](docs/decisions/0001-upstream-boundary.md)。
