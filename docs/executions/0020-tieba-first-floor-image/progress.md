# Execution 0020 progress / 执行 0020 推进记录

- Status / 状态：Planning and response-shape audit complete; implementation pending / 规划与响应形状审计已完成；实现待执行
- Last updated / 最近更新：2026-09-02
- Predecessor / 前置：`431fd855dafce502e83f74a055a4b27ae5c6f40b`
- Plan commit / 计划提交：`PENDING`
- Implementation commit / 实现提交：`PENDING`

## Completed before implementation / 实现前已完成

- [x] Reconciled clean local `main`, `origin/main` and GitHub predecessor at `431fd855dafce502e83f74a055a4b27ae5c6f40b`. / 已核对干净的本地 `main`、`origin/main` 与 GitHub 前置提交 `431fd855dafce502e83f74a055a4b27ae5c6f40b`。
- [x] Verified both pinned upstream locks and clean checkout worktrees: MediaCrawler `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`, bili-sync-up `dcb5bb73b56ac45b2525da14b389e185b0ea6dbd`. / 已校验两个锁定上游及干净 checkout：MediaCrawler `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`、bili-sync-up `dcb5bb73b56ac45b2525da14b389e185b0ea6dbd`。
- [x] Audited the locked Tieba `page_pc` → extractor → `TiebaNote` → gather child/parent store → JSONL path and identified the exact loss boundary: structured first-floor media is available to the extractor but only `text`/`c` survives. / 已审计锁定贴吧 `page_pc` → extractor → `TiebaNote` → gather 子任务/父存储 → JSONL 路径，并定位精确丢失边界：结构化首楼媒体可到达 extractor，但只有 `text`/`c` 被保留。
- [x] Ran a bounded unauthenticated read-only current-response audit. It confirmed integer type 3, the current ten-key image item family, exact `tiebapic.baidu.com` origin and single `tbpicau` query key, including real one-image rows. No query values or bodies were retained. / 已运行有界、未登录、只读的当前响应审计，确认整数 type 3、当前十键图片项族、精确 `tiebapic.baidu.com` origin 与唯一 `tbpicau` query 键，并找到真实单图行；未保留 query 值或正文。
- [x] Demonstrated transiently that signed and query-free requests can both return HTTP 200 JPEG while returning different byte bodies (`65,144` versus `4,262` bytes). Durable query-free identity plus pre-download signed refresh is therefore mandatory. / 已瞬态证明带签名与无 query 请求都可能返回 HTTP 200 JPEG，但字节正文不同（`65,144` 对 `4,262` 字节）；因此必须使用持久无 query 身份加下载前签名刷新。
- [x] Passed the pre-edit focused baseline: `307 passed in 36.66s`. / 编辑前专项基线通过：`307 passed in 36.66s`。
- [x] Frozen the claim to one ordinary first-floor static IMAGE while keeping the thread ARTICLE. Multiple images and every other media/rich-content type remain deferred. / 已把声明冻结为普通首楼精确一张静态 IMAGE，同时保持主题为 ARTICLE；多图片与全部其他媒体/富内容类型继续延期。

## Implementation pending / 待实现

- [ ] Add the pinned-source loss/creator-bound contract without changing `.upstream`. / 增加锁定源码丢失/作者边界合约，且不修改 `.upstream`。
- [ ] Implement strict Tieba ID, canonical URL, current type-3 item, signed locator and query-free source-hint validators. / 实现严格贴吧 ID、canonical URL、当前 type-3 item、签名 locator 与无 query source-hint 校验器。
- [ ] Implement verified-checkout exact-object capture with parent-store task isolation, collision/origin guards and scheduled creator cap hardening. / 实现校验 checkout 的精确对象捕获，覆盖父存储任务隔离、冲突/来源 guard 与 scheduled creator 上限加固。
- [ ] Normalize ARTICLE plus one `image:0`, remove private/transient data, and add exact detail refresh with DEFAULT profile. / 归一化 ARTICLE 加一个 `image:0`，移除私有/瞬态数据，并增加 DEFAULT profile 的精确详情刷新。
- [ ] Enable the static byte gate and prove SQLite/detail/mock HTTP/archive/Emby composition plus zero-work replay. / 启用静态字节门，并证明 SQLite/detail/mock HTTP/archive/Emby 组合及零工作重放。
- [ ] Run final focused/full/static/type/build/docs/audit gates, update truth documents, review, commit and push bilingual implementation/closeout changes. / 运行最终专项/全量/静态/类型/构建/文档/审计门，更新真值文档，复核、提交并推送双语实现/收尾变更。

## Verification status / 验证状态

- Pre-edit focused baseline / 编辑前专项基线：`PASS — 307 passed in 36.66s`.
- Current public response shape audit / 当前公开响应形状审计：`PASS — bounded unauthenticated read-only evidence; no values retained / 有界未登录只读证据；未保留值`.
- Implementation and complete suite / 实现与完整套件：`PENDING`.
- Authenticated Tieba login/creator/detail, future real CDN bytes and real Emby/Jellyfin server / 登录态贴吧 login/creator/detail、未来真实 CDN 字节及真实 Emby/Jellyfin 服务：`NOT_RUN`.

The broader goal remains active. Execution 0020 can establish a seventh-platform media slice without claiming complete Tieba media or complete seven-platform product coverage. / 更大的目标继续推进。Execution 0020 可以建立第七个平台媒体切片，但不宣称贴吧媒体或七平台产品能力已全部完成。
