# Execution 0019 plan / 执行 0019 计划

- Status / 状态：Plan frozen; implementation pending / 计划已冻结；实现待执行
- Plan date / 计划日期：2026-09-01
- Predecessor / 前置：Execution 0018 closeout commit `4fb639a`
- Plan commit / 计划提交：`PENDING`
- Implementation commit / 实现提交：`PENDING`
- Database migration / 数据库迁移：None planned / 计划无

## Baseline / 前置基线

The branch begins from clean predecessor `4fb639a`. Before source edits, the focused MediaCrawler ingestion/detail/download/Emby baseline passed `255 passed in 48.32s`; the exact command is retained in `verification.md`. No Execution 0019 implementation or live result is claimed by this planning checkpoint. The main thread will still reconcile local `main`, `origin/main` and GitHub and confirm both pinned upstream checkouts remain clean before implementation. / 分支从干净前置 `4fb639a` 开始。源码编辑前，MediaCrawler 导入/detail/下载/Emby 专项基线通过 `255 passed in 48.32s`；精确命令保留在 `verification.md`。本计划检查点不宣称任何 Execution 0019 实现或真人结果。实现前，主线程仍会核对本地 `main`、`origin/main` 与 GitHub，并确认两个锁定上游 checkout 继续干净。

## Planned delivery sequence / 计划交付顺序

1. **Freeze locked-source evidence / 冻结锁定源码证据 — pending / 待执行**
   - Add a source-bound contract that verifies MediaCrawler SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`, AST-extracts or executes the actual pinned answer extractor, HTML text stripper and Zhihu store functions, and proves that image attributes reach `_extract_answer_content` but disappear before the current JSONL row. / 增加源码绑定合约，校验 MediaCrawler SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`，通过 AST 提取或执行真实锁定的回答 extractor、HTML 文本清理器与知乎 store 函数，并证明图片属性会到达 `_extract_answer_content`，但在当前 JSONL 行前消失。
   - Assert from the locked source that creator mode calls answers only, the answer request includes raw `content`, article/video creator calls are disabled, and current answer pagination ignores the configured note cap. Tests must execute or structurally bind pinned source rather than validating copied implementation code. / 从锁定源码断言 creator 模式只调用回答、回答请求包含原始 `content`、文章/视频 creator 调用被禁用，且当前回答分页忽略配置的 note 上限。测试必须执行或结构绑定锁定源码，不得只验证复制出的实现代码。
   - Record explicitly that synthetic HTML proves the integration contract but, without a real redacted fixture, cannot qualify live Zhihu attribute behavior. / 明确记录合成 HTML 只能证明集成合约；在没有真实脱敏夹具时，不能资格化知乎现网属性行为。

2. **Install the answer-image shim and bounded creator path / 安装回答图片 shim 与有界 creator 路径 — pending / 待执行**
   - Add one integration-owned `zhihu_media` module with strict bounded HTML/image parsing and HTTPS `zhimg.com` URL validation. Qualify exactly one static `jpg`/`jpeg`/`png`/`webp` image selected by the frozen `data-original` → `data-actualsrc` → `src` contract; reject multiple/duplicate/ambiguous images, malformed-plus-valid mixtures, video/player markers and animation. / 增加一个由集成拥有的 `zhihu_media` 模块，实现严格有界 HTML/图片解析及 HTTPS `zhimg.com` URL 校验。只按冻结的 `data-original` → `data-actualsrc` → `src` 合约验收精确一张静态 `jpg`/`jpeg`/`png`/`webp` 图片；拒绝多张/重复/歧义图片、畸形+有效混合、video/player 标记及动图。
   - Patch only verified-checkout runtime objects: wrap `ZhihuExtractor._extract_answer_content`, carry a frozen capture on the exact returned model, bind it with a task-local context through `store.zhihu.update_zhihu_content`, and enrich only `ZhihuJsonlStoreImplement.store_content` under a versioned private field. Double installation is idempotent only when complete; partial installation, collision or module-origin drift fails. / 只 patch 校验过的 checkout 运行时对象：包装 `ZhihuExtractor._extract_answer_content`，在精确返回模型上携带冻结捕获，通过任务局部上下文贯穿 `store.zhihu.update_zhihu_content`，并只在版本化私有字段下增强 `ZhihuJsonlStoreImplement.store_content`。完整重复安装才允许幂等；部分安装、冲突或模块来源漂移均失败。
   - Install the shim in both scheduled creator and detail children after verified upstream import and before `main()` execution. Never edit or track `.upstream`. / 在 scheduled creator 与 detail 两类子进程中，均于校验上游导入后、`main()` 执行前安装 shim；绝不修改或跟踪 `.upstream`。
   - Replace or wrap the locked all-answer loop so it writes at most Subscription `max_items`, stops without another page at the bound, validates page/data/paging shapes and offset progress, and preserves callback pacing/cancellation/watchdog behavior. / 替换或包装锁定的全回答循环，使其最多写入 Subscription `max_items`，达到边界后不再请求下一页，校验 page/data/paging 形状与 offset 推进，并保留 callback 节奏、取消与 watchdog 行为。

3. **Normalize one exact IMAGE safely / 安全归一化一张精确 IMAGE — pending / 待执行**
   - Add the versioned Zhihu private field to recursive private-field stripping. Parse it all-or-nothing only for `content_type="answer"`; keep `ContentKind.ARTICLE` and emit exactly one position-zero `AssetKind.IMAGE` with remote ID `<content_id>:image:0`. Zero-image historical rows remain ARTICLE with no Asset and are outside the new claim. / 把版本化知乎私有字段加入递归私有字段移除。只对 `content_type="answer"` 全有或全无解析；保持 `ContentKind.ARTICLE`，并输出精确一个 position 0 `AssetKind.IMAGE`，remote ID 为 `<content_id>:image:0`。历史零图片行继续作为无 Asset 的 ARTICLE，且不属于新增声明。
   - Preserve only a query/userinfo/fragment-free source hint in SQLite and durable raw. Reject container drift, duplicate identity and unsupported media without silently degrading a claimed answer image into a different Asset shape. / SQLite 与持久 raw 只保留无 query/userinfo/fragment 的 source hint。拒绝容器漂移、重复 identity 及不支持媒体，不得把已声明的回答图片静默降级为其他 Asset 形状。

4. **Add exact canonical answer detail refresh / 增加精确 canonical 回答详情刷新 — pending / 待执行**
   - Extend the detail/refresh supported-platform sets only for Zhihu IMAGE position zero and validate one exact non-secret canonical answer reference: HTTPS `www.zhihu.com`, `/question/<positive-question-id>/answer/<content-id>`, no query, fragment, userinfo, custom port or trailing-path drift, and exact content-ID equality. The reference comes from the persisted trusted Content row rather than reconstructed raw media or caller input. / 只为知乎 IMAGE position 0 扩展 detail/refresh 支持平台集合，并校验一个精确非 secret canonical 回答引用：HTTPS `www.zhihu.com`、`/question/<正整数问题ID>/answer/<content-id>`、无 query、fragment、userinfo、自定义端口或尾路径漂移，且 content ID 精确相等。引用来自已持久化可信 Content 行，不从原始媒体或调用方输入重建。
   - Require exactly one normalized matching answer and one matching IMAGE remote ID/kind/position/query-free hint. Revalidate the current `zhimg.com` locator before `ResolvedLocator`, return `MediaRequestProfile.DEFAULT`, and preserve existing redirect public-network enforcement without forwarding account credentials. / 要求精确一条归一化匹配回答，以及一条匹配 IMAGE remote ID/kind/position/query-free hint。在创建 `ResolvedLocator` 前重新校验当前 `zhimg.com` locator，返回 `MediaRequestProfile.DEFAULT`，保留既有重定向公网检查且不转发账户凭据。

5. **Compose SQLite, archive and Emby / 组合 SQLite、归档与 Emby — pending / 待执行**
   - Add an offline end-to-end test covering exact Subscription provenance, bounded creator output, exact detail refresh, mock public DNS/HTTP, a real decodable PNG/JPEG through the production image validator, SHA-256 archive and deterministic Emby poster/gallery/NFO/source output. / 增加离线端到端测试，覆盖精确 Subscription 来源、有界 creator 输出、精确 detail 刷新、mock 公网 DNS/HTTP、真实可解码 PNG/JPEG 通过生产图片校验、SHA-256 归档及确定性 Emby poster/gallery/NFO/source 输出。
   - Prove durable data contains no shim field, query, userinfo or fragment; completed attempt roots are removed; query-only replay performs zero additional detail, DNS, HTTP, validation, archive or export work. / 证明持久数据不含 shim 字段、query、userinfo 或 fragment；已完成 attempt 根会删除；仅 query 变化的重放不会新增 detail、DNS、HTTP、校验、归档或导出工作。

6. **Verify and close / 验证与收尾 — pending / 待执行**
   - Run focused pytest, locked-source contract, the full suite, Ruff check/format, strict mypy, compileall, upstream locks, build, documentation, diff and retained-artifact audits. Record exact commands, counts, durations and skips only after they run. / 运行专项 pytest、锁定源码合约、完整套件、Ruff 检查/格式、严格 mypy、compileall、上游锁、构建、文档、diff 及保留产物审计；仅在真实运行后记录精确命令、数量、耗时与跳过项。
   - Update the four execution documents plus repository capability/roadmap truth. Keep real login, live creator/detail/CDN and real Emby rows `NOT_RUN`, and keep the broader seven-platform goal active. / 更新四份执行文档及仓库能力/路线图真值。真人登录、现网 creator/detail/CDN 及真实 Emby 行保持 `NOT_RUN`，更大的七平台目标继续推进。
   - Create and push separate bilingual plan, implementation and closeout commits, reconciling local, tracking and GitHub SHAs after each push. / 分别创建并推送双语计划、实现与收尾提交；每次推送后核对本地、tracking 与 GitHub SHA。

## Commit sequence / 提交序列

1. `PENDING` — `docs: 启动知乎回答图片闭环 / start Zhihu answer-image pipeline`
2. `PENDING` — `feat: 闭环知乎回答图片 / close Zhihu answer-image pipeline`
3. `PENDING` — `docs: 收尾知乎回答图片闭环 / close Zhihu answer-image pipeline`

`.upstream` must remain excluded, unmodified and clean throughout the execution. / 整个执行期间，`.upstream` 必须继续排除在跟踪外、保持未修改且干净。
