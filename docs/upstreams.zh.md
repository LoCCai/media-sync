[English](upstreams.md) | **中文**

# 上游基线

机器可读的唯一事实来源是 [`../upstreams.lock.json`](../upstreams.lock.json)。

## MediaCrawler

- 仓库：`https://github.com/NanmiCoder/MediaCrawler.git`
- 分支：`main`
- Commit：`d6f7c5bb906b6dac40ddf343ef9e26438a3de092`
- 提交时间：`2026-08-14T16:18:52+08:00`
- 许可证：`NON-COMMERCIAL LEARNING LICENSE 1.1`
- 声明平台：`xhs`, `dy`, `ks`, `bili`, `wb`, `tieba`, `zhihu`。
- 声明创作者模式：`CRAWLER_TYPE=creator`。
- 登录基础：Playwright/CDP 浏览器状态、二维码、手机号或 Cookie，视平台能力而定。

## bili-sync-up

- 仓库：`https://github.com/NeeYoonc/bili-sync-up.git`
- 分支：`main`
- Commit：`dcb5bb73b56ac45b2525da14b389e185b0ea6dbd`
- 提交时间：`2026-07-28T21:04:06+08:00`
- 许可证：MIT。
- 相关设计：Bilibili 来源订阅、持久下载状态、媒体处理、NFO 生成与 Web 管理。

## 复现

```powershell
New-Item -ItemType Directory -Path .upstream -Force
git clone https://github.com/NanmiCoder/MediaCrawler.git .upstream/MediaCrawler
git -C .upstream/MediaCrawler checkout d6f7c5bb906b6dac40ddf343ef9e26438a3de092
git clone https://github.com/NeeYoonc/bili-sync-up.git .upstream/bili-sync-up
git -C .upstream/bili-sync-up checkout dcb5bb73b56ac45b2525da14b389e185b0ea6dbd
```

`.upstream/` 目录被本仓库有意忽略。
