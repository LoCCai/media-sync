# Execution 0013 plan / 执行 0013 计划

- Status / 状态：Frozen before implementation / 实现前已冻结
- Plan date / 计划日期：2026-08-31
- Predecessor / 前置：Execution 0012 closeout commit `7c6f567`

## Delivery sequence / 交付顺序

1. **Freeze contracts and baseline / 冻结契约与基线**
   - Record all four bilingual execution files, add execution 0013 to the journal/roadmap, and create a bilingual local plan commit before source edits. / 在修改源码前记录四份中英双语执行文档，把执行 0013 加入日志/路线图，并创建双语本地计划提交。
   - Preserve the exact pinned upstream commits and the external-runtime/license boundary; do not copy MediaCrawler or bili-sync-up source. / 保持精确锁定的上游提交及外部 runtime/许可证边界；不复制 MediaCrawler 或 bili-sync-up 源码。
   - Run the existing ingestion/detail-refresh/locator/network/downloader/layout/offline-pipeline tests as the starting baseline. / 运行既有导入、detail refresh、locator、网络、下载、layout 与离线 pipeline 测试作为起始基线。

2. **Create a stable Bilibili video discovery slot / 创建稳定 Bilibili 视频发现槽位**
   - Add red tests showing that one Bilibili video metadata record emits a cover and one position-zero video Asset while a dynamic emits no synthetic media. / 先加红测，证明一个 Bilibili 视频元数据记录产生封面与一个 position 0 视频 Asset，而动态不会产生合成媒体。
   - Make the domain snapshot source URL explicitly optional and emit a locator-only `<aid>:video:0` slot with `source_url=None`. The database column, `AssetUpsert`, fingerprinting and refresh-source provenance already support this shape, so no migration is planned. / 让领域快照的 source URL 显式可选，并产生一个 `source_url=None` 的 locator-only `<aid>:video:0` 槽。数据库列、`AssetUpsert`、指纹与刷新来源追踪已支持该形状，因此不计划 migration。
   - Permit a missing source hint only for the exact Bilibili video/position-zero shape in the application and refresher. Select the refreshed candidate by bound content/remote-id/kind/position; keep exact non-null source-hint matching unchanged for every predecessor shape. / 只在精确 Bilibili video/position 0 形状中允许缺少 source hint；refresher 按绑定 content/remote-id/kind/position 选择刷新候选，所有既有形状继续保持非空 source-hint 精确匹配。

3. **Resolve the first-page progressive URL in the isolated child / 在隔离 child 中解析首 P progressive URL**
   - Extend the numeric-aid detail path to validate returned aid and first-page CID, call the pinned `get_video_play_url_task`, and parse a closed single-`durl` result. / 扩展 numeric-aid detail 路径：校验返回 aid 与首 P CID，调用锁定的 `get_video_play_url_task`，并解析封闭的单 `durl` 结果。
   - Return a typed, repr-safe progressive result alongside upstream completion. Read the ordinary content JSONL first, then inject one private bridge field into bounded bytes in memory; do not rewrite the attempt tree. A default-off detail-only normalization gate accepts that field, strips it before envelope/raw retention and emits the same durable Asset identity with the transient URL. / 在上游完成结果旁返回一个具名、repr-safe 的 progressive 结果。先读取普通 content JSONL，再只在内存中向有界字节注入一个私有桥字段；不改写 attempt 树。默认关闭的 detail-only 归一化 gate 接受该字段，在 envelope/raw 保留前移除它，并以瞬态 URL 产生同一个持久 Asset 身份。
   - Add closed child outcomes for unsupported progressive shapes and distinguish them from temporary play-url fetch failures and malformed results. / 为不支持的 progressive 形状增加封闭 child 结果，并与播放地址瞬时获取失败及非法结果区分。

4. **Carry a non-secret Bilibili HTTP profile to the downloader / 把非密钥 Bilibili HTTP 配置传入下载器**
   - Extend ephemeral `ResolvedLocator` with a closed request-profile identifier; persisted locator schema v1 remains unchanged. / 为瞬态 `ResolvedLocator` 增加封闭 request-profile 标识；持久 locator schema v1 保持不变。
   - Apply exact fixed User-Agent, Referer and Origin headers inside the bounded HTTP layer while continuing to accept only Range/If-Range from resume state. Never pass Cookie, Authorization or arbitrary headers. / 在有界 HTTP 层应用精确固定的 User-Agent、Referer 与 Origin，同时仍只接受续传状态提供的 Range/If-Range；绝不传递 Cookie、Authorization 或任意 header。
   - Prove the profile across redirects, resume and the existing one-time 401/403 re-resolution without weakening DNS/redirect/header limits. / 证明该配置在重定向、续传与既有一次 401/403 重解析中保持正确，且不削弱 DNS、重定向与 header 限制。

5. **Compose the offline playable-to-Emby path / 组合离线可播放到 Emby 链路**
   - Add contract tests for exact aid/CID binding, transient signed output, unsupported/malformed play-url shapes and attempt-root cleanup. / 增加契约测试，覆盖精确 aid/CID 绑定、瞬态签名输出、不支持/非法播放地址形状及 attempt 根清理。
   - Add a focused integration using synthetic metadata, a fake current Subscription source, deterministic CDN bytes and a controlled media probe. Assert durable download success, SHA-256/archive identity, primary `.mp4` episode output, NFO/source metadata and idempotent replay. / 增加一个专项集成：使用合成元数据、假的当前 Subscription 来源、确定性 CDN 字节与受控媒体探测；断言持久下载成功、SHA-256/归档身份、主 `.mp4` episode 输出、NFO/source 元数据及幂等重放。
   - Scan SQLite, runtime output, CLI/log capture and Git-visible files for the signed URL, Cookie sentinel and forbidden headers. / 扫描 SQLite、runtime 输出、CLI/日志捕获及 Git 可见文件，确认不存在签名 URL、Cookie 哨兵与禁止 header。

6. **Verify, document and commit / 验证、记录并提交**
   - Run the focused execution gate, full pytest, Ruff lint/format, mypy, docs/upstream checks, build and `git diff --check`. / 运行执行专项门禁、完整 pytest、Ruff lint/格式、mypy、文档/上游检查、构建及 `git diff --check`。
   - Run the retained-artifact and high-confidence secret audits without printing matched secret values. / 运行保留产物与高置信密钥审计，不打印命中的密钥值。
   - Update goal/plan/progress/verification with exact commands, results and commits; update capability documents without promoting any live row; create bilingual implementation and closeout commits. / 用精确命令、结果与提交更新目标/计划/推进/验证；更新能力文档但不提升任何真人行；创建双语实现与收尾提交。

## Risks and rollback points / 风险与回退点

- A `NULL` source URL is allowed only for the exact Bilibili first-page video slot and only with the stable MediaCrawler refresh locator. Every other predecessor shape retains its current source-hint rule. / `NULL` source URL 只允许用于精确 Bilibili 首 P 视频槽，且必须搭配稳定 MediaCrawler refresh locator；其他既有形状继续保持当前 source-hint 规则。
- `durl` can represent legacy segmented media. Execution 0013 accepts exactly one segment so its output is independently playable; multi-segment concatenation and FLV remux remain future work. / `durl` 可能表示旧式分段媒体。执行 0013 只接受精确一个分段，确保输出可独立播放；多段拼接与 FLV remux 留待后续。
- Fixed Bilibili headers are non-secret protocol metadata. They must be selected by a closed profile, not persisted as caller-controlled mappings or mixed with credentials. / 固定 Bilibili header 属于非密钥协议元数据；必须由封闭 profile 选择，不能作为调用方可控 mapping 持久化或与凭据混合。
- Because forward metadata lacks CID, the stable 0013 identity is the logical `<aid>:video:0` slot. A same-aid first-CID replacement cannot invalidate already-verified bytes automatically and is deferred with CID-aware multi-page discovery. / 因为 forward 元数据缺少 CID，0013 的稳定身份是逻辑 `<aid>:video:0` 槽；同一 aid 下首 CID 替换无法自动使已验证字节失效，该能力与 CID-aware 多 P 发现一并延期。
- Rollback removes the synthetic Bilibili video discovery slot, play-url enrichment and request profile while retaining execution 0012 and the historical cover-only Bilibili support. No destructive migration is required. / 回退时移除合成 Bilibili 视频发现槽、播放地址补充及 request profile，同时保留执行 0012 与历史封面能力；不需要破坏性 migration。
