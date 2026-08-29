# ADR-0001: Keep MediaCrawler behind an external process boundary

# ADR-0001：通过外部进程边界使用 MediaCrawler

- Status / 状态：Accepted / 已接受
- Date / 日期：2026-08-30

## Context / 背景

MediaCrawler provides the required seven-platform browser/login and creator-crawl behavior, but its `NON-COMMERCIAL LEARNING LICENSE 1.1` limits use, copying, modification and merging to non-commercial learning purposes. `bili-sync-up` is MIT-licensed and can be studied or reused subject to its notice requirements.

MediaCrawler 提供所需的七平台浏览器登录和创作者抓取能力，但其 `NON-COMMERCIAL LEARNING LICENSE 1.1` 将使用、复制、修改和合并限制在非商业学习用途。`bili-sync-up` 使用 MIT 许可证，在保留声明的条件下可以研究或复用。

## Decision / 决策

`media-sync` will not vendor, import, modify or redistribute MediaCrawler source. An adapter will execute a separately obtained, explicitly pinned checkout as an external process and ingest documented output files. The user remains responsible for accepting and complying with that upstream license and each platform's terms. The adapter must fail clearly if the external runtime is absent.

`media-sync` 不会内嵌、导入、修改或再分发 MediaCrawler 源码。适配器只会执行用户单独获取并明确锁定版本的外部检出，然后导入其输出文件。用户必须自行接受并遵守上游许可证及各平台条款。外部运行时不存在时，适配器必须清晰失败。

Design ideas from `bili-sync-up` may inform our independent implementation. Any copied MIT-licensed code, if introduced later, must be identified and accompanied by its copyright notice.

可以借鉴 `bili-sync-up` 的设计思想来独立实现；后续如果实际复制 MIT 代码，必须逐项标注并附带其版权声明。

## Consequences / 影响

- A clean installation can run the core, fake adapters and Emby exporter without MediaCrawler.
- Live crawling is an optional integration and inherits MediaCrawler's license restrictions.
- Process/file contracts are easier to test and upgrade, but login progress and errors require explicit bridging.
- No claim is made that this architecture alone grants commercial-use rights; legal review is required for commercial distribution.

- 核心、假适配器和 Emby 导出器可以在没有 MediaCrawler 时运行。
- 真人抓取属于可选集成，并继承 MediaCrawler 的许可证限制。
- 进程/文件契约更容易测试和升级，但登录进度与错误需要显式桥接。
- 该架构本身不代表获得商业使用权；商业分发仍需法律审查。
