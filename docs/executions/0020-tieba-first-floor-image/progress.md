# Execution 0020 progress / 执行 0020 推进记录

- Status / 状态：Frozen offline slice implemented, verified and pushed; live rows `NOT_RUN` / 冻结离线切片已实现、验证并推送；真人行 `NOT_RUN`
- Last updated / 最近更新：2026-09-02
- Predecessor / 前置：`431fd855dafce502e83f74a055a4b27ae5c6f40b`
- Plan commit / 计划提交：`df7a38a6f9beee35c6c19336260b512ebc87ce0d`
- Implementation commit / 实现提交：`8a0e935624e944809af1a56b0f02186686433d95`

## Completed before implementation / 实现前已完成

- [x] Reconciled clean local `main`, `origin/main` and GitHub predecessor at `431fd855dafce502e83f74a055a4b27ae5c6f40b`. / 已核对干净的本地 `main`、`origin/main` 与 GitHub 前置提交 `431fd855dafce502e83f74a055a4b27ae5c6f40b`。
- [x] Verified both pinned upstream locks and clean checkout worktrees: MediaCrawler `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`, bili-sync-up `dcb5bb73b56ac45b2525da14b389e185b0ea6dbd`. / 已校验两个锁定上游及干净 checkout：MediaCrawler `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`、bili-sync-up `dcb5bb73b56ac45b2525da14b389e185b0ea6dbd`。
- [x] Audited the locked Tieba `page_pc` → extractor → `TiebaNote` → gather child/parent store → JSONL path and identified the exact loss boundary: structured first-floor media is available to the extractor but only `text`/`c` survives. / 已审计锁定贴吧 `page_pc` → extractor → `TiebaNote` → gather 子任务/父存储 → JSONL 路径，并定位精确丢失边界：结构化首楼媒体可到达 extractor，但只有 `text`/`c` 被保留。
- [x] Ran a bounded unauthenticated read-only current-response audit. It confirmed integer type 3, the current ten-key image item family, exact `tiebapic.baidu.com` origin and single `tbpicau` query key, including real one-image rows. No query values or bodies were retained. / 已运行有界、未登录、只读的当前响应审计，确认整数 type 3、当前十键图片项族、精确 `tiebapic.baidu.com` origin 与唯一 `tbpicau` query 键，并找到真实单图行；未保留 query 值或正文。
- [x] Demonstrated transiently that signed and query-free requests can both return HTTP 200 JPEG while returning different byte bodies (`65,144` versus `4,262` bytes). Durable query-free identity plus pre-download signed refresh is therefore mandatory. / 已瞬态证明带签名与无 query 请求都可能返回 HTTP 200 JPEG，但字节正文不同（`65,144` 对 `4,262` 字节）；因此必须使用持久无 query 身份加下载前签名刷新。
- [x] Passed the pre-edit focused baseline: `307 passed in 36.66s`. / 编辑前专项基线通过：`307 passed in 36.66s`。
- [x] Frozen the claim to one ordinary first-floor static IMAGE while keeping the thread ARTICLE. Multiple images and every other media/rich-content type remain deferred. / 已把声明冻结为普通首楼精确一张静态 IMAGE，同时保持主题为 ARTICLE；多图片与全部其他媒体/富内容类型继续延期。

## Implemented / 已实现

- [x] Added a source-bound contract that verifies the exact locked SHA and executes the real Tieba extractor/model/store loss boundary without changing `.upstream`. / 已增加源码绑定合约，校验精确锁定 SHA 并执行真实贴吧 extractor/model/store 丢失边界，且未修改 `.upstream`。
- [x] Added strict positive thread IDs, exact canonical thread URLs, the current ten-key integer type-3 item, signed `origin_src` and query-free source-hint validators. / 已增加严格正整数主题 ID、精确 canonical 主题 URL、当前十键整数 type-3 item、签名 `origin_src` 与无 query source-hint 校验器。
- [x] Added verified-checkout exact-object capture across gather-child → parent-store, nested-store-only `ContextVar`, module/marker/collision guards and scheduled creator cap hardening. `max_items=23` produces `20 + 3` detail/callback batches, no third page and no post-cap sleep. / 已增加校验 checkout 的精确对象捕获，跨越 gather-child → parent-store，只在嵌套 store 使用 `ContextVar`，并加入模块/marker/冲突 guard 与 scheduled creator 上限加固；`max_items=23` 形成 `20 + 3` 详情/callback 批次，无第三页或达到上限后的 sleep。
- [x] Kept ARTICLE and added exactly one `<note_id>:image:0` IMAGE, recursively removed private state, persisted only a query-free hint, and added canonical parent/child detail authority plus credential-free DEFAULT refresh. / 保持 ARTICLE 并增加精确一个 `<note_id>:image:0` IMAGE，递归移除私有状态，只持久化无 query hint，并增加 canonical 父/child 详情权限及无凭据 DEFAULT 刷新。
- [x] Enabled automatic static qualification for Tieba IMAGE. Qualified JPEG/PNG/WebP pass; GIF/APNG/animated WebP/AVIF fail; normal, recovery and takeover preparation preserve the flag. / 已为贴吧 IMAGE 自动启用静态资格门；合格 JPEG/PNG/WebP 通过，GIF/APNG/animated WebP/AVIF 失败，normal、recovery 与 takeover 准备链均保留该标志。
- [x] Added deterministic SQLite → fake detail → mock public DNS/HTTP → production byte gate → SHA-256 archive → Emby poster/backdrop/gallery/body/NFO/source composition. Query-only replay adds zero work, and retained SQLite/WAL/SHM/runtime/archive/export trees contain no private field or transient token. / 已增加确定性 SQLite → fake detail → mock 公网 DNS/HTTP → 生产字节门 → SHA-256 归档 → Emby poster/backdrop/gallery/body/NFO/source 组合；仅 query 变化的重放新增工作为零，保留 SQLite/WAL/SHM/runtime/archive/export 树不含私有字段或瞬态 token。
- [x] Passed the final focused/full/quality/build/upstream/audit gates and pushed bilingual implementation commit `8a0e935` with local, tracking and GitHub reconciliation. / 最终专项/全量/质量/构建/上游/审计门均通过；双语实现提交 `8a0e935` 已推送并完成本地、tracking 与 GitHub 核对。

## Still open / 仍待实现或验收

- [ ] Multiple first-floor images/gallery, video/voice/emoji/link/rich-card types, reply/comment media, alternate image authorities and media replacement semantics. / 首楼多图片/gallery、视频/语音/表情/链接/富卡片类型、回复/评论媒体、其他图片权限及媒体替换语义。
- [ ] A retained redacted real response fixture and authenticated/live Tieba qualification. / 可保留的真实脱敏响应夹具及登录/现网贴吧验收。
- [ ] Broader per-platform shapes and the full seven-platform product outcome. / 更广的逐平台形状及完整七平台产品结果。

## Verification status / 验证状态

- Pre-edit focused baseline / 编辑前专项基线：`PASS — 307 passed in 36.66s`.
- Current public response shape audit / 当前公开响应形状审计：`PASS — bounded unauthenticated read-only evidence; no values retained / 有界未登录只读证据；未保留值`.
- Focused implementation regression / 实现专项回归：`PASS — 368 passed in 41.18s`.
- Complete suite / 完整套件：`PASS — 1650 passed, 1 skipped in 310.82s`; the skip is the Windows-inapplicable POSIX mode-bit boundary / 跳过项为 Windows 不适用的 POSIX mode-bit 边界。
- Quality/build/upstream/audit gates / 质量/构建/上游/审计门：`PASS`.
- Authenticated Tieba login/creator/detail, future real CDN bytes and real Emby/Jellyfin server / 登录态贴吧 login/creator/detail、未来真实 CDN 字节及真实 Emby/Jellyfin 服务：`NOT_RUN`.

The broader goal remains active. Execution 0020 establishes a seventh-platform media slice without claiming complete Tieba media or complete seven-platform product coverage. / 更大的目标继续推进。Execution 0020 已建立第七个平台媒体切片，但不宣称贴吧媒体或七平台产品能力已全部完成。
