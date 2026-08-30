# Execution 0013 progress / 执行 0013 推进结果

- Status / 状态：Plan frozen; implementation not started / 计划已冻结；尚未开始实现
- Started / 开始时间：2026-08-31 05:12 +08:00

## Completed / 已完成

- Closed execution 0012 in local documentation commit `7c6f567`; the working tree was clean before execution 0013 planning. / 已在本地文档提交 `7c6f567` 收尾执行 0012；执行 0013 规划前工作树干净。
- Audited the current normalizer, detail runner, provenance-bound refresher, bounded downloader, Emby layout and pipeline composition. Bilibili currently emits only a cover Asset, and its detail refresher supports only covers. / 已审计当前 normalizer、detail runner、按来源绑定的 refresher、有界下载器、Emby layout 与 pipeline 组合；Bilibili 当前只产生封面 Asset，detail refresher 也只支持封面。
- Audited both locked upstreams without networking or modification. MediaCrawler provides the numeric-aid detail and `fnval=1` `durl` play-url path; bili-sync-up proves the fixed header requirement and documents the wider DASH/multi-page path reserved for later work. / 已在不联网、不修改的前提下审计两个锁定上游。MediaCrawler 提供 numeric-aid detail 与 `fnval=1` 的 `durl` 播放地址路径；bili-sync-up 证明固定 header 要求，并记录留待后续的更宽 DASH/多 P 路径。
- Frozen the minimal product boundary to ordinary numeric-aid uploads, the first page and exactly one progressive segment. DASH, split audio/video, multi-segment, multi-page, subtitle and danmaku work is explicitly excluded. / 已把最小产品边界冻结为普通 numeric-aid 投稿、首 P 与精确一个 progressive 分段；明确排除 DASH、音视频分离、多段、多 P、字幕与弹幕。
- Re-ran the 158-test predecessor baseline covering ingestion, detail refresh, locator/network/downloader, layout and offline pipeline; all passed. / 已重跑覆盖导入、detail refresh、locator/网络/下载、layout 与离线 pipeline 的 158 项前置基线，全部通过。

## Decisions / 决策

- Reuse the current stable `adapter_refresh` identity and database schema. The Bilibili video slot uses `source_url=NULL`; an exact detail lookup supplies the ephemeral CDN URL. Existing nullable persistence, fingerprints and source provenance make a migration unnecessary. / 复用当前稳定 `adapter_refresh` 身份与数据库 schema。Bilibili 视频槽使用 `source_url=NULL`；精确 detail 查询提供瞬态 CDN URL。既有 nullable 持久化、指纹与来源追踪使 migration 无必要。
- Accept exactly one `durl` item. Choosing one item from a multi-segment list could publish an incomplete file, so that shape is unsupported rather than guessed. / 只接受精确一个 `durl` item。从多段列表任取一项可能发布不完整文件，因此该形状标记为不支持，不做猜测。
- Add a named fixed Bilibili request profile instead of carrying arbitrary headers. This preserves the existing prohibition on Cookie/Authorization injection while satisfying the documented CDN protocol requirement. / 增加具名、固定的 Bilibili request profile，而不是传递任意 header；这样既保留 Cookie/Authorization 注入禁令，也满足已有源码证据支持的 CDN 协议要求。
- Keep the signed play URL out of the attempt tree: the detail child returns a typed result and augments the already-read JSONL bytes only in memory under a default-off gate. / 让签名播放 URL 不进入 attempt 树：detail child 返回具名结果，并仅在默认关闭 gate 下对已经读取的 JSONL 字节做内存补充。
- The stable identity remains the logical `<aid>:video:0` slot because forward metadata has no CID. Same-aid first-CID replacement detection is an explicit deferred limitation, not an execution 0013 claim. / 由于 forward 元数据没有 CID，稳定身份继续使用逻辑 `<aid>:video:0` 槽；检测同 aid 首 CID 替换属于明确延期限制，不是执行 0013 声明。
- Automated success will remain offline evidence. It cannot promote real account, creator request, signed CDN or Emby/Jellyfin scan/playback rows. / 自动化成功仍只属于离线证据，不能提升真人账户、作者请求、签名 CDN 或 Emby/Jellyfin 重扫/播放行。

## Remaining / 待完成

- Create and record the bilingual local plan commit. / 创建并记录双语本地计划提交。
- Implement and test the Bilibili video discovery slot and exact refresh selection. / 实现并测试 Bilibili 视频发现槽及精确刷新选择。
- Implement and test first-page single-`durl` child resolution and fixed outcomes. / 实现并测试首 P 单 `durl` child 解析及固定结果。
- Implement and test the closed Bilibili HTTP request profile. / 实现并测试封闭的 Bilibili HTTP request profile。
- Compose the offline signed-locator → download/probe → archive → Emby integration and idempotent replay. / 组合离线“签名 locator → 下载/探测 → 归档 → Emby”集成及幂等重放。
- Run full gates, update all documentation and create bilingual implementation/closeout commits. / 运行完整门禁，更新全部文档，并创建双语实现/收尾提交。
