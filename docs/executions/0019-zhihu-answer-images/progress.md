# Execution 0019 progress / 执行 0019 推进记录

- Status / 状态：Frozen offline Zhihu answer-image slice and documentation closeout complete / 冻结离线知乎回答图片切片与文档收尾已完成
- Last updated / 最近更新：2026-09-02
- Predecessor / 前置：`4fb639a`
- Plan commit / 计划提交：`dc1714c`
- Implementation commit / 实现提交：`2edb9d763b4948c56cc182bcc5012914bcb644d1`

## Completed / 已完成

- [x] Audited and source-bound the pinned MediaCrawler Zhihu answer request, real extractor/update/JSONL loss boundary, answers-only creator dispatch and missing native cap at SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`; no upstream file was edited. / 已审计并源码绑定 SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` 的锁定 MediaCrawler 知乎回答请求、真实 extractor/update/JSONL 丢失边界、仅回答 creator dispatch 及缺少原生上限事实；未修改任何上游文件。
- [x] Implemented the frozen `data-original` → `data-actualsrc` → `src` one-image parser and strict canonical answer/`zhimg.com` URL gates. Duplicate/competing lazy or `srcset` attributes, multiple images, media-container drift, empty delimiters and unsupported URLs fail closed. / 已实现冻结的 `data-original` → `data-actualsrc` → `src` 单图解析器及严格 canonical 回答/`zhimg.com` URL 门；重复/竞争性 lazy 或 `srcset` 属性、多图、媒体容器漂移、空分隔符与不支持 URL 均关闭失败。
- [x] Fixed the review-discovered P1 by binding capture to the exact returned object and using `ContextVar` only inside nested storage. The gather-child → parent-store regression and real locked Pydantic carry/consume/non-serialization contract pass. / 已通过把捕获绑定到精确返回对象、只在嵌套 store 中使用 `ContextVar` 修复审查发现的 P1；gather child → 父 store 回归及真实锁定 Pydantic 携带/消费/不序列化合约均通过。
- [x] Bounded scheduled creator execution by Subscription `max_items`. The end-to-end child proof turns 23 into two API requests and two callback invocations with page sizes `20 + 3`, exactly 23 callback-processed rows and one between-page pacing sleep; there is no third request or post-cap sleep. Short non-terminal, repeated, malformed and extractor-drift pages fail closed. Zhihu no longer requires full-history acknowledgement. / 已以 Subscription `max_items` 约束 scheduled creator 执行；端到端 child 证据把 23 转换为页面大小 `20 + 3` 的两次 API 请求与两次 callback 调用，callback 精确处理 23 行，页间执行一次节奏 sleep；达到上限后没有第三次请求或额外 sleep。短非终止页、重复页、畸形页与 extractor 漂移均关闭失败。知乎不再要求全历史确认。
- [x] Normalized ARTICLE plus one position-zero `<content_id>:image:0` IMAGE, removed private/transient authority from durable state, and implemented exact canonical-answer detail refresh with credential-free `MediaRequestProfile.DEFAULT`. / 已归一化 ARTICLE 加 position 0 的唯一 `<content_id>:image:0` IMAGE，从持久状态移除私有/瞬态权限，并实现精确 canonical 回答 detail 刷新与无凭据 `MediaRequestProfile.DEFAULT`。
- [x] Added automatic bounded static structural qualification for Zhihu IMAGE downloads. Qualified JPEG/PNG/WebP pass; GIF/APNG/animated WebP/AVIF fail; normal, recovery and takeover preparation preserve the flag. This is structural qualification, not complete pixel decoding. / 已为知乎 IMAGE 下载增加自动有界静态结构资格校验；合格 JPEG/PNG/WebP 通过，GIF/APNG/animated WebP/AVIF 失败；normal、recovery 与 takeover 准备链保留该标志。该能力是结构资格校验，不是完整像素解码。
- [x] Passed the SQLite → fake detail → mock public DNS/HTTP → production byte gate → SHA-256 archive → Emby poster/backdrop/gallery/body/NFO/source composition, zero-work query replay and retained SQLite/runtime/archive/export/WAL/SHM audit. / 已通过 SQLite → fake detail → mock 公网 DNS/HTTP → 生产字节门 → SHA-256 归档 → Emby poster/backdrop/gallery/body/NFO/source 组合、query 零工作重放及保留 SQLite/runtime/archive/export/WAL/SHM 审计。
- [x] Passed the final 505-test focused gate, complete suite (`1543 passed, 1 skipped`), Ruff, format, strict mypy, compileall, upstream locks, build, docs, diff/retained-artifact audit and a fresh independent 461-test review with no P0/P1/P2. / 已通过最终 505 项专项门、完整套件（`1543 passed, 1 skipped`）、Ruff、格式、严格 mypy、compileall、上游锁、构建、文档、diff/保留产物审计，以及未发现 P0/P1/P2 的全新 461 项独立复核。
- [x] Created and pushed bilingual implementation commit `2edb9d763b4948c56cc182bcc5012914bcb644d1`; local `main`, `origin/main` and GitHub were reconciled. / 已创建并推送双语实现提交 `2edb9d763b4948c56cc182bcc5012914bcb644d1`；本地 `main`、`origin/main` 与 GitHub 已核对一致。

## Documentation closeout / 文档收尾

- [x] The commit containing this record is the bilingual documentation closeout. Its self-referential SHA is intentionally not embedded; post-push local/tracking/GitHub reconciliation is reported in the task handoff. / 包含本记录的提交即双语文档收尾；其自引用 SHA 有意不嵌入，推送后的本地/tracking/GitHub 核对结果在任务交接中报告。

## Deferred product scope / 延期产品范围

Multiple-answer images/gallery, Zhihu articles, zvideo playback/covers, real redacted fixtures and live login/creator/detail/CDN/Emby qualification remain deferred or `NOT_RUN`. Tieba downloadable media and complete seven-platform coverage remain active work. / 知乎回答多图/gallery、文章、zvideo 播放/封面、真实脱敏夹具及真人登录/作者/detail/CDN/Emby 验收继续延期或保持 `NOT_RUN`。贴吧可下载媒体与七平台完整覆盖继续推进。
