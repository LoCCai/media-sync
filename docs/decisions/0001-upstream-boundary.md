**English** | [中文](0001-upstream-boundary.zh.md)

# ADR-0001: Keep MediaCrawler behind an external process boundary

- Status: Accepted
- Date: 2026-08-30

## Context

MediaCrawler provides the required seven-platform browser/login and creator-crawl behavior, but its `NON-COMMERCIAL LEARNING LICENSE 1.1` limits use, copying, modification and merging to non-commercial learning purposes. `bili-sync-up` is MIT-licensed and can be studied or reused subject to its notice requirements.

## Decision

`media-sync` will not vendor, import, modify or redistribute MediaCrawler source. An adapter will execute a separately obtained, explicitly pinned checkout as an external process and ingest documented output files. The user remains responsible for accepting and complying with that upstream license and each platform's terms. The adapter must fail clearly if the external runtime is absent.

Design ideas from `bili-sync-up` may inform our independent implementation. Any copied MIT-licensed code, if introduced later, must be identified and accompanied by its copyright notice.

## Consequences

- A clean installation can run the core, fake adapters and Emby exporter without MediaCrawler.
- Live crawling is an optional integration and inherits MediaCrawler's license restrictions.
- Process/file contracts are easier to test and upgrade, but login progress and errors require explicit bridging.
- No claim is made that this architecture alone grants commercial-use rights; legal review is required for commercial distribution.
