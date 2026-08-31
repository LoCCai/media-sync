# Execution 0016 plan / 执行 0016 计划

- Status / 状态：Complete for the frozen offline delivery sequence / 冻结离线交付序列已完成
- Plan date / 计划日期：2026-08-31
- Predecessor / 前置：Execution 0015 closeout commit `b105d00`
- Plan commit / 计划提交：`b7bb818`
- Implementation commit / 实现提交：`a77ca74`

## Executed delivery sequence / 已执行交付顺序

1. **Freeze scope and baseline / 冻结范围与基线 — COMPLETE**
   - Audited the locked Weibo, Tieba and Zhihu paths and selected Weibo because raw `mblog.pics` already reaches creator/detail workflows while the pinned JSONL store discards it. Tieba required new HTML extraction and Zhihu exposed no equivalent stable media contract. / 已审计锁定的微博、贴吧与知乎路径；选择微博是因为原始 `mblog.pics` 已进入 creator/detail 工作流，只是在锁定 JSONL store 被丢弃。贴吧需要新增 HTML 提取，知乎没有等价的稳定媒体契约。
   - Created the four bilingual execution records before source edits and recorded the predecessor gate: `272 passed in 46.92s`. / 在源码编辑前创建四份双语执行记录，并记录前置门禁：`272 passed in 46.92s`。

2. **Install one shared Weibo media shim / 安装共享微博媒体 shim — COMPLETE**
   - Added one integration-owned task-local shim and installed it after verified-checkout import in both creator and detail children. It enriches only the transient contents JSONL boundary and leaves `.upstream` untouched. / 新增一个由集成拥有的 task-local shim，并在 creator 与 detail child 导入已验证 checkout 后安装。它只增强瞬态 contents JSONL 边界，保持 `.upstream` 不变。
   - Frozen the accepted raw shape to canonical positive numeric original posts, no `retweeted_status`, no media `page_info`, unique ordered `pid` entries, source authority `sinaimg.cn` or a subdomain, and static `jpg/jpeg/png/webp` files. All other shapes fail closed. / 把接受的原始形状冻结为规范正整数原创帖子、无 `retweeted_status`、无媒体 `page_info`、唯一有序 `pid` 项、源站仅 `sinaimg.cn` 或其子域，以及静态 `jpg/jpeg/png/webp` 文件；其他形状全部关闭失败。

3. **Normalize and refresh exact image Assets / 归一化并刷新精确图片 Asset — COMPLETE**
   - Parsed only the private v1 image field, mapped one image to `IMAGE`, multiple images to `GALLERY`, and generated ordered position-based IMAGE Assets. All media-sync private fields are recursively removed before durable raw is built. / 只解析私有 v1 图片字段，把单图映射为 `IMAGE`、多图映射为 `GALLERY`，并生成按 position 排序的 IMAGE Asset；构建持久 raw 前递归移除全部 media-sync 私有字段。
   - Added WB image-only detail/refresh support. Request construction, resolved reference and child loading require the same canonical plain numeric ID, while refresh retains exact Account, Subscription, content, Asset identity, order and query-free source-hint matching. / 增加 WB 仅 image 的 detail/refresh 支持；请求构造、引用解析与 child 加载都要求同一个规范纯 numeric ID，同时刷新保留精确 Account、Subscription、content、Asset identity、顺序及无 query source-hint 匹配。

4. **Compose the production path offline / 离线组合生产路径 — COMPLETE**
   - Extended isolated fake-checkout contracts for creator/detail installation, concurrency isolation, configuration, framing and normal-success cleanup. Normalization plus SQLite proves ordered Assets and exact `AssetRefreshSource` provenance. / 扩展隔离 fake checkout 契约，覆盖 creator/detail 安装、并发隔离、配置、framing 与正常成功清理；归一化加 SQLite 证明有序 Asset 与精确 `AssetRefreshSource` 来源。
   - Expanded the platform composition E2E to two pictures. Each Asset independently performs exact detail refresh, default-profile public-DNS/HTTP transfer and SHA-256 archive publication; Emby layout receives first-image poster, second-image backdrop, two ordered gallery files, NFO and allowlisted source metadata. Replay performs zero additional work. / 把平台组合 E2E 扩展为双图；每个 Asset 分别执行精确 detail 刷新、默认 profile 公网 DNS/HTTP 传输与 SHA-256 归档发布；Emby 布局接收首图 poster、次图 backdrop、两个有序 gallery 文件、NFO 与白名单 source 元数据；重放不产生额外工作。

5. **Review and repair / 审查与修复 — COMPLETE**
   - Independent review found and closed three boundary defects: arbitrary embedded proxy host acceptance, non-static/unknown extension acceptance, and different-but-valid WB numeric detail references. / 独立审查发现并关闭三项边界缺陷：任意代理内嵌源站、非静态/未知扩展名，以及不同但合法的 WB numeric detail reference。
   - The same review found the one-picture composition evidence too weak for a Gallery claim; the E2E now proves two distinct Assets, downloads, archives and gallery outputs. / 同一审查发现单图组合证据不足以支持 Gallery 声明；E2E 现已证明两个不同 Asset、下载、归档与 gallery 输出。

6. **Verify implementation / 验证实现 — COMPLETE**
   - Combined 15-file focused gate: `388 passed in 125.73s`. / 合并 15 文件专项门禁：`388 passed in 125.73s`。
   - Complete suite: `1251 passed, 1 skipped in 359.38s`; the skip is the Windows-inapplicable POSIX mode-bit case. / 完整套件：`1251 passed, 1 skipped in 359.38s`；跳过项是 Windows 不适用的 POSIX mode-bit 用例。
   - Ruff check passes; all 228 files are formatted; strict mypy passes 78 source files; both pinned upstream entries verify; `uv build` produces the wheel and source distribution; diff checks pass. / Ruff 静态检查通过；228 个文件格式正确；严格 mypy 通过 78 个源码文件；两个锁定上游条目校验通过；`uv build` 产生 wheel 与源码分发包；diff 检查通过。

7. **Close out for delivery / 完成交付收尾 — COMPLETE**
   - Finalized the bilingual truth documents, reran documentation/build/diff checks, audited retained artifacts and prepared the separate bilingual closeout commit. Pushing that commit and reconciling local, `origin/main` and GitHub SHAs are post-commit delivery actions reported in the task handoff. / 已定稿双语真值文档，重跑文档/构建/diff 检查，审计保留产物，并准备独立双语收尾提交。推送该提交并核对本地、`origin/main` 与 GitHub SHA 属于提交后的交付动作，由任务交接结果报告。

## Deferred scope and risks / 延期范围与风险

- Weibo video, GIF/animated-image semantics, long-image handling, media `page_info`, retweets and restricted/live media remain outside this slice. / 微博视频、GIF/动图语义、长图处理、媒体 `page_info`、转发及受限/直播媒体仍不属于本切片。
- Creator mode still walks full history; explicit `allow_full_history` and outer watchdogs remain mandatory because bounded creator pagination is not implemented. / creator 模式仍遍历完整历史；由于尚未实现有界 creator 分页，显式 `allow_full_history` 与外层 watchdog 仍为强制要求。
- Offline acceptance proves deterministic proxy URL construction and the closed request profile, not third-party proxy availability, rate limits, service terms or a Sina-direct profile. / 离线验收证明确定性代理 URL 构造与封闭请求 profile，不证明第三方代理可用性、限流、服务条款或新浪直连 profile。
- Same-ID media replacement detection, injected cleanup-failure quarantine and all live platform/CDN/media-server qualification remain deferred or `NOT_RUN`. / 同 ID 媒体替换检测、注入清理失败 quarantine 及全部真人平台/CDN/媒体服务器验收继续延期或保持 `NOT_RUN`。
