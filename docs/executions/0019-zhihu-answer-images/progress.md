# Execution 0019 progress / 执行 0019 推进记录

- Status / 状态：Planning complete; implementation not started / 规划完成；实现尚未开始
- Last updated / 最近更新：2026-09-01
- Predecessor / 前置：`4fb639a`
- Plan commit / 计划提交：`PENDING`
- Implementation commit / 实现提交：`PENDING`

## Completed before implementation / 实现前已完成

- [x] Read-only audit of the locked MediaCrawler Zhihu creator, answer, article, zvideo, detail, model and JSONL store paths at SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`; neither upstream checkout was modified. / 已对 SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` 的锁定 MediaCrawler 知乎 creator、回答、文章、zvideo、detail、模型及 JSONL store 路径完成只读审计；两个上游 checkout 均未修改。
- [x] Confirmed that creator mode currently calls answers only, raw answer HTML reaches `_extract_answer_content`, all image attributes are removed by `extract_text_from_html`, `ZhihuContent` has no media field, and JSONL therefore contains no downloadable Asset locator. / 已确认 creator 模式当前只调用回答，原始回答 HTML 会到达 `_extract_answer_content`，全部图片属性被 `extract_text_from_html` 删除，`ZhihuContent` 没有媒体字段，因此 JSONL 不含可下载 Asset locator。
- [x] Confirmed that the locked all-answer creator loop ignores `CRAWLER_MAX_NOTES_COUNT`; successful bounded pagination is included in scope instead of being misrepresented as an existing guarantee. / 已确认锁定的全回答 creator 循环忽略 `CRAWLER_MAX_NOTES_COUNT`；成功有界分页已纳入范围，不把它误述为现有保证。
- [x] Frozen the minimum claim to an ordinary answer with exactly one static `zhimg.com` IMAGE. Zero-image answers remain compatible but outside the media claim; multiple images/gallery, article media and zvideo remain deferred. / 已把最小声明冻结为普通回答中的精确一张 `zhimg.com` 静态 IMAGE。零图片回答继续兼容但不属于媒体声明；多图/gallery、文章媒体及 zvideo 均延期。
- [x] Recorded the evidence limit: no real redacted Zhihu answer/API fixture exists, so the planned result can be source-bound offline evidence only; all live rows remain `NOT_RUN`. / 已记录证据限制：当前没有真实脱敏知乎回答/API 夹具，因此计划结果只能形成源码绑定的离线证据；全部真人行保持 `NOT_RUN`。
- [x] Pre-edit focused baseline passed `255 passed in 48.32s`, covering MediaCrawler ingestion, detail refresh, database ingestion, Asset download orchestration, pipeline runtime and refresh units. / 编辑前专项基线通过 `255 passed in 48.32s`，覆盖 MediaCrawler 导入、detail 刷新、数据库导入、Asset 下载编排、pipeline runtime 及刷新单元测试。

## Implementation pending / 待实现

- [ ] Reconcile local/tracking/GitHub predecessor SHAs before implementation. / 实现前核对本地/tracking/GitHub 前置 SHA。
- [ ] Add the pinned-source contract proving the exact HTML-to-text and model-to-JSONL loss boundary without network access. / 增加锁定源码合约，在无需网络时证明精确 HTML→文本与模型→JSONL 丢失边界。
- [ ] Implement strict one-image HTML/URL capture and verified-checkout runtime shim with collision, partial-installation and task-isolation protections. / 实现严格单图 HTML/URL 捕获及校验 checkout 运行时 shim，并覆盖冲突、部分安装与任务隔离保护。
- [ ] Enforce successful creator pagination at Subscription `max_items`, with bounded page/data/paging validation and no extra request after the cap. / 在 Subscription `max_items` 强制成功 creator 分页边界，校验有界 page/data/paging，并保证达到上限后无额外请求。
- [ ] Normalize exactly one ARTICLE-owned position-zero IMAGE while stripping the private field and signed query from durable state. / 在 ARTICLE 下归一化精确一个 position 0 IMAGE，同时从持久状态移除私有字段与签名 query。
- [ ] Add strict persisted canonical answer authority and one-detail refresh with exact content/Asset/source-hint matching and `MediaRequestProfile.DEFAULT`. / 增加严格持久 canonical 回答权限与单详情刷新，要求精确 content/Asset/source-hint 匹配并使用 `MediaRequestProfile.DEFAULT`。
- [ ] Prove SQLite provenance → bounded detail → mock DNS/HTTP → real image validation → immutable archive → Emby publication and zero-work replay. / 证明 SQLite 来源 → 有界 detail → mock DNS/HTTP → 真实图片校验 → 不可变归档 → Emby 发布及零工作重放。
- [ ] Run all quality, build, documentation, upstream-cleanliness and retained-artifact gates; obtain independent final review; create/push separate bilingual implementation and closeout commits. / 运行全部质量、构建、文档、上游干净性及保留产物门禁；取得独立最终审查；分别创建/推送双语实现与收尾提交。

## Verification status / 验证状态

- Execution 0019 pre-edit baseline: `PASS` — `255 passed in 48.32s`. / Execution 0019 编辑前基线：`PASS` — `255 passed in 48.32s`。
- Focused implementation tests: `PENDING`. / 实现专项测试：`PENDING`。
- Complete suite and static/build/docs gates: `PENDING`. / 完整套件及静态/构建/文档门禁：`PENDING`。
- Real Zhihu login, creator/detail traffic, real CDN bytes and real Emby/Jellyfin server: `NOT_RUN`. / 真人知乎登录、creator/detail 流量、真实 CDN 字节及真实 Emby/Jellyfin 服务：`NOT_RUN`。

The broader user goal remains active. Execution 0019 will add only one narrow media shape for the sixth platform and will not claim complete Zhihu or seven-platform media coverage. / 更大的用户目标继续推进。Execution 0019 只会为第六个平台增加一个狭窄媒体形状，不宣称完成全部知乎或七平台媒体覆盖。
