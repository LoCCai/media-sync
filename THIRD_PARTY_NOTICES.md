**English** | [中文](THIRD_PARTY_NOTICES.zh.md)

# Third-party notices

No third-party source code is currently vendored or copied into this repository. The following projects were inspected as design inputs and are reproducibly pinned in [`upstreams.lock.json`](upstreams.lock.json).

## MediaCrawler

- Copyright: `Copyright (c) 2024 relakkes@gmail.com`
- Source: `https://github.com/NanmiCoder/MediaCrawler`
- License: `NON-COMMERCIAL LEARNING LICENSE 1.1`
- Treatment: this Git repository neither vendors nor distributes the source. Operator-built Docker images download and embed the locked checkout at build time; such images are for the operator's own personal local use and must not be pushed or redistributed

The license restricts use to non-commercial learning/research and prohibits large-scale crawling and commercial use without written consent. An external-process boundary does not remove those obligations.

## bili-sync-up

- Copyright: `Copyright (c) 2024 ᴀᴍᴛᴏᴀᴇʀ`
- Source: `https://github.com/NeeYoonc/bili-sync-up`
- License: MIT
- Treatment: design study only at present

If MIT-licensed source is copied or adapted later, the relevant copyright and full MIT permission notice must accompany that code and this file must identify the affected paths.
