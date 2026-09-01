# Execution 0026 progress / 执行 0026 推进记录

- Status / 状态：Frozen offline scope and implementation verification complete / 冻结离线范围与实现验证完成
- Last updated / 最近更新：2026-09-02
- Predecessor / 前置：`7cb84fc6c93b832492b95513d9cb6a9708ee6cc9`
- Plan commit / 计划提交：`0694934bc9230151a85c040a061d6e704dffc4fc`
- Implementation commit / 实现提交：`190488f77d1704492cc148b890d6f9ae16d84f84`

## Completed / 已完成

- [x] Reconciled the Execution 0025 closeout, audited the strict single-segment parser/private bridge/normalizer/downloader boundaries and kept both pinned checkouts unchanged. / 已核对 Execution 0025 收尾，审计严格单段解析器/私有桥接/归一化器/下载器边界，并保持两个锁定 checkout 未修改。
- [x] Upgraded the bounded detail process protocol to v6 and parsed `durl[0].url` plus equivalent `backup_url`/`backupUrl` aliases through `ResolvedLocator`; absent backups remain compatible, while malformed, conflicting, duplicate, primary-equal or over-eight candidates fail closed. / 已把有界详情进程协议升级到 v6，并通过 `ResolvedLocator` 解析 `durl[0].url` 与等价 `backup_url`/`backupUrl` 别名；无备用保持兼容，畸形、冲突、重复、与主地址相同或超过八个候选均关闭失败。
- [x] Added a bounded private single-page backup field and optional multipart `backup_urls`, accepted historical primary-only payloads and recursively removed every private field before durable raw/SQLite/Job state. / 已增加有界私有单 P 备用字段与可选多分 P `backup_urls`，兼容历史仅主地址 payload，并在持久 raw/SQLite/Job 状态前递归移除全部私有字段。
- [x] Extracted one shared primary-first candidate pass for ordinary and DASH resolved locators under the existing asset lock, shared deadline, byte cap and restart budget. / 已为普通与 DASH resolved locator 提取共享的主地址优先候选轮次，并沿用既有 Asset 锁、共享截止时间、字节上限与 restart 预算。
- [x] Limited failover to DNS, timeout, transport, interruption, HTTP and Range-incompatibility outcomes; network-policy, redirect/header/encoding, chunk/size, filesystem, probe, mux, archive and publication failures remain immediate. / 已把故障切换限制为 DNS、timeout、传输、中断、HTTP 与 Range 不兼容结果；网络策略、重定向/header/encoding、chunk/size、文件系统、探测、合并、归档与发布失败继续立即关闭。
- [x] Preserved exact cross-candidate offset/total-length/validator continuity, retained valid partials through mixed failures and allowed destructive restart only after the complete candidate pass rejected the partial. / 已保持跨候选 offset/总长度/validator 精确连续，在混合失败中保留合法 partial，且只有完整候选轮次拒绝 partial 后才允许破坏性 restart。
- [x] Preserved direct-locator behavior and changed adapter auth rotation only at the intended boundary: one all-`401`/`403` pass re-resolves detail once; a second all-auth pass returns `locator_refresh_auth_expired`. / 已保持 direct locator 行为，并只在预定边界调整 adapter 鉴权轮换：一轮全部 `401`/`403` 后重解析详情一次；第二轮仍全鉴权失败则返回 `locator_refresh_auth_expired`。
- [x] Extended both single-page and three-page SQLite compositions so each primary returns `503`, its backup supplies the bytes, the existing probe/archive/Emby publication succeeds and replay performs zero new detail/DNS/HTTP/probe/archive/export work. / 已扩展单 P 与三分 P SQLite 组合：每个主地址返回 `503`，备用地址提供字节，既有探测/归档/Emby 发布成功，重放不新增 detail/DNS/HTTP/probe/archive/export 工作。
- [x] Added 24 focused cases across parser, bridge, normalizer and downloader boundaries; retained signed primary/backup candidates and private fields are absent from SQLite/runtime/work/archive/export/operator evidence. / 已在解析器、桥接、归一化与下载器边界增加 24 个专项用例；保留 SQLite/runtime/work/归档/导出/运维证据均不含签名主/备用候选与私有字段。
- [x] Passed focused `490`, complete `1814 + 1 skip`, single-/multipart backup compositions, DASH compatibility, Ruff, format, strict mypy, compileall, build, docs, upstream, diff and repository audits. / 已通过专项 `490`、完整 `1814 + 1 skip`、单 P/多分 P 备用组合、DASH 兼容、Ruff、格式、严格 mypy、compileall、构建、文档、上游、diff 与仓库审计门。
- [x] Created and pushed bilingual plan and implementation commits; root truth documents are aligned in the documentation closeout. / 已创建并推送双语计划与实现提交；根真值文档在文档收尾中完成对齐。

## Remaining outside this execution / 本执行外待实现

Multiple progressive segments, FLV remux, CDN ranking/racing/cache, mixed-exhaustion detail refresh, subtitles/danmaku, pages above 64, broader media shapes, REST/production packaging and every real platform/CDN/media-server row remain deferred or `NOT_RUN`; the broader seven-platform goal stays active. / 多段 progressive、FLV remux、CDN 排序/竞速/缓存、混合穷尽详情刷新、字幕/弹幕、超过 64 个分 P、更广媒体形状、REST/生产打包及全部真人平台/CDN/媒体服务器行继续延期或保持 `NOT_RUN`；更大的七平台目标保持进行中。
