# Upstream baseline / 上游基线

The machine-readable source of truth is [`../upstreams.lock.json`](../upstreams.lock.json).

机器可读的唯一事实来源是 [`../upstreams.lock.json`](../upstreams.lock.json)。

## MediaCrawler

- Repository / 仓库：`https://github.com/NanmiCoder/MediaCrawler.git`
- Branch / 分支：`main`
- Commit：`d6f7c5bb906b6dac40ddf343ef9e26438a3de092`
- Commit date / 提交时间：`2026-08-14T16:18:52+08:00`
- License / 许可证：`NON-COMMERCIAL LEARNING LICENSE 1.1`
- Declared platforms / 声明平台：`xhs`, `dy`, `ks`, `bili`, `wb`, `tieba`, `zhihu`。
- Declared creator mode / 声明创作者模式：`CRAWLER_TYPE=creator`。
- Declared login foundation / 登录基础：Playwright/CDP browser state, QR code, phone or Cookie depending on platform capability.

## bili-sync-up

- Repository / 仓库：`https://github.com/NeeYoonc/bili-sync-up.git`
- Branch / 分支：`main`
- Commit：`dcb5bb73b56ac45b2525da14b389e185b0ea6dbd`
- Commit date / 提交时间：`2026-07-28T21:04:06+08:00`
- License / 许可证：MIT。
- Relevant design areas / 相关设计：Bilibili source subscription, persistent download state, media processing, NFO generation and Web administration.

## Reproduction / 复现

```powershell
New-Item -ItemType Directory -Path .upstream -Force
git clone https://github.com/NanmiCoder/MediaCrawler.git .upstream/MediaCrawler
git -C .upstream/MediaCrawler checkout d6f7c5bb906b6dac40ddf343ef9e26438a3de092
git clone https://github.com/NeeYoonc/bili-sync-up.git .upstream/bili-sync-up
git -C .upstream/bili-sync-up checkout dcb5bb73b56ac45b2525da14b389e185b0ea6dbd
```

The `.upstream/` directory is intentionally ignored by this repository.

`.upstream/` 目录被本仓库有意忽略。
