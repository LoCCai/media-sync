**English** | [中文](upstreams.zh.md)

# Upstream baseline

The machine-readable source of truth is [`../upstreams.lock.json`](../upstreams.lock.json).

## MediaCrawler

- Repository: `https://github.com/NanmiCoder/MediaCrawler.git`
- Branch: `main`
- Commit：`d6f7c5bb906b6dac40ddf343ef9e26438a3de092`
- Commit date: `2026-08-14T16:18:52+08:00`
- License: `NON-COMMERCIAL LEARNING LICENSE 1.1`
- Declared platforms: `xhs`, `dy`, `ks`, `bili`, `wb`, `tieba`, `zhihu`。
- Declared creator mode: `CRAWLER_TYPE=creator`。
- Declared login foundation: Playwright/CDP browser state, QR code, phone or Cookie depending on platform capability.

## bili-sync-up

- Repository: `https://github.com/NeeYoonc/bili-sync-up.git`
- Branch: `main`
- Commit：`dcb5bb73b56ac45b2525da14b389e185b0ea6dbd`
- Commit date: `2026-07-28T21:04:06+08:00`
- License: MIT。
- Relevant design areas: Bilibili source subscription, persistent download state, media processing, NFO generation and Web administration.

## Reproduction

```powershell
New-Item -ItemType Directory -Path .upstream -Force
git clone https://github.com/NanmiCoder/MediaCrawler.git .upstream/MediaCrawler
git -C .upstream/MediaCrawler checkout d6f7c5bb906b6dac40ddf343ef9e26438a3de092
git clone https://github.com/NeeYoonc/bili-sync-up.git .upstream/bili-sync-up
git -C .upstream/bili-sync-up checkout dcb5bb73b56ac45b2525da14b389e185b0ea6dbd
```

The `.upstream/` directory is intentionally ignored by this repository.
