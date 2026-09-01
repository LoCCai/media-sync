# Execution 0020 plan / 执行 0020 计划

- Status / 状态：Completed for the frozen offline scope / 冻结离线范围已完成
- Plan date / 计划日期：2026-09-02
- Predecessor / 前置：Execution 0019 closeout commit `431fd855dafce502e83f74a055a4b27ae5c6f40b`
- Plan commit / 计划提交：`df7a38a6f9beee35c6c19336260b512ebc87ce0d`
- Implementation commit / 实现提交：`8a0e935624e944809af1a56b0f02186686433d95`
- Database migration / 数据库迁移：None planned / 计划无

## Baseline / 前置基线

The branch starts clean and reconciled at `431fd855dafce502e83f74a055a4b27ae5c6f40b`. The pre-edit focused ingestion/detail/database/download/runtime/refresh baseline passed `307 passed in 36.66s`. Both pinned upstream locks passed and both checkout worktrees were clean. A bounded unauthenticated public-API audit established the current type/key/host/query shape without retaining response bodies or query values. / 分支从已核对一致且干净的 `431fd855dafce502e83f74a055a4b27ae5c6f40b` 开始。编辑前的导入/detail/数据库/下载/runtime/refresh 专项基线通过 `307 passed in 36.66s`。两个锁定上游均通过校验，两个 checkout 工作树均干净。一次有界、未登录的公开 API 审计确认了当前 type/key/host/query 形状，且未保留响应正文或 query 值。

## Delivery sequence / 交付顺序

1. **Freeze source and response contracts / 冻结源码与响应合约 — completed / 已完成**
   - Add a source-bound contract for MediaCrawler SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` that executes the real `extract_note_detail_from_api` → `TiebaNote` → `update_tieba_note` → JSONL loss boundary. Bind the test to `_get_pc_page_data`, `get_note_by_id`, creator `asyncio.gather`/parent storage and the JSONL export without modifying upstream. / 增加绑定 MediaCrawler SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` 的源码合约，执行真实 `extract_note_detail_from_api` → `TiebaNote` → `update_tieba_note` → JSONL 丢失边界；把测试绑定到 `_get_pc_page_data`、`get_note_by_id`、creator `asyncio.gather`/父存储及 JSONL 导出，且不修改上游。
   - Freeze the synthetic offline response from the observed current shape: ordinary type-0 text plus exactly one type-3 image and exact `origin_src` authority. Record that the live read-only audit is current structural evidence, not a retained fixture or authenticated qualification. / 按已观察的当前形状冻结合成离线响应：普通 type-0 文本加精确一个 type-3 图片及精确 `origin_src` 权限。明确现网只读审计是当前结构证据，不是保留夹具或登录验收。

2. **Capture exact first-floor media and bound creators / 捕获精确首楼媒体并约束作者 — completed / 已完成**
   - Add integration-owned `tieba_media.py` with strict positive thread IDs, canonical thread URLs, bounded first-floor item validation, exact type-3 key contract, strict signed/query-free image URL validators and source-hint derivation. / 增加集成拥有的 `tieba_media.py`，实现严格正整数主题 ID、canonical 主题 URL、有界首楼 item 校验、精确 type-3 键合约、严格 signed/query-free 图片 URL 校验及 source-hint 派生。
   - Patch only verified checkout objects: extractor → exact-object frozen capture → parent `update_tieba_note` ContextVar → matching JSONL row. Full repeat installation is idempotent; wrong origin, partial/collision state, uncarryable model, identity mismatch and cross-task leakage fail closed. / 只 patch 校验 checkout 对象：extractor → 精确对象冻结捕获 → 父 `update_tieba_note` ContextVar → 匹配 JSONL 行。完整重复安装允许幂等；错误来源、部分/冲突状态、模型无法携带、身份不匹配及跨任务泄漏均关闭失败。
   - Wrap the pinned creator loop only for scheduled runs with the trusted Subscription cap. Validate page dictionaries, `thread_list`, positive unique IDs, `has_more`, exact returned note identity and callback batch bounds; truncate before detail, stop before post-cap sleep and reject repeated/no-progress/drift pages. / 只在 scheduled 运行中以可信 Subscription 上限包装锁定 creator 循环。校验页面字典、`thread_list`、正整数唯一 ID、`has_more`、精确返回 note 身份及 callback batch 边界；在详情前截断，达到上限前停止额外 sleep，并拒绝重复/无推进/漂移页面。
   - Install the capture in both scheduled creator and detail children after verified import and before upstream `main()`. / 在 scheduled creator 与 detail 子进程中，均于校验导入后、上游 `main()` 前安装捕获。

3. **Normalize and refresh one ARTICLE-owned IMAGE / 归一化并刷新 ARTICLE 所属单图 — completed / 已完成**
   - Extend Tieba normalization all-or-nothing: keep ARTICLE, emit one `<note_id>:image:0`, recursively strip the private field and persist only the canonical query-free hint. Preserve legacy zero-image ARTICLE rows. / 全有或全无地扩展贴吧归一化：保留 ARTICLE，输出一个 `<note_id>:image:0`，递归移除私有字段并只持久化规范无 query 提示；保持历史零图片 ARTICLE 行。
   - Add Tieba to exact detail execution and refresh support. Derive note ID only from the persisted canonical URL, require one exact normalized content/Asset/hint match, validate the new signed URL again and return DEFAULT profile without account headers. / 把贴吧加入精确详情执行与刷新支持。只从持久 canonical URL 派生 note ID，要求唯一精确 normalized content/Asset/hint 匹配，再次校验新签名 URL并以 DEFAULT profile 返回，不携带账户 header。

4. **Qualify bytes and compose Emby output / 校验字节并组合 Emby 输出 — completed / 已完成**
   - Enable the existing bounded static-image structure gate for Tieba IMAGE and prove acceptance/rejection plus normal/recovery/takeover flag preservation. / 为贴吧 IMAGE 启用既有有界静态图片结构门，并证明接受/拒绝边界及 normal/recovery/takeover 标志保持。
   - Add an isolated SQLite → fake detail → mock public DNS/HTTP → production byte gate → immutable archive → Emby integration test with poster/backdrop/gallery/body/NFO/source outputs and query-only zero-work replay. / 增加隔离的 SQLite → fake detail → mock 公网 DNS/HTTP → 生产字节门 → 不可变归档 → Emby 集成测试，覆盖 poster/backdrop/gallery/body/NFO/source 输出及 query-only 零工作重放。
   - Audit retained database, WAL/SHM, runtime, archive and export trees for private fields and transient token/query fragments. / 审计保留数据库、WAL/SHM、runtime、archive 与 export 树，确保不含私有字段及瞬态 token/query 片段。

5. **Verify, review and publish / 验证、审查与发布 — completed / 已完成**
   - Run the source contract, focused gate, complete suite, Ruff, format, strict mypy, compileall, upstream locks, build, docs, diff and retained-artifact audits. Record only executed commands, counts, durations and skips. / 运行源码合约、专项门、完整套件、Ruff、格式、严格 mypy、compileall、上游锁、构建、文档、diff 与保留产物审计；只记录真实执行的命令、数量、耗时与跳过项。
   - Update these four execution documents plus capability/roadmap/index truth. Keep authenticated Tieba login/creator/detail, future CDN behavior and real Emby/Jellyfin scan/display `NOT_RUN`; keep broader media shapes active. / 更新这四份执行文档及能力/路线图/索引真值。登录态贴吧 login/creator/detail、未来 CDN 行为及真实 Emby/Jellyfin 扫描/展示保持 `NOT_RUN`；更广媒体形状继续推进。
   - Create and push separate bilingual plan, implementation and closeout commits, reconciling local, tracking and GitHub SHAs. / 分别创建并推送双语计划、实现与收尾提交，并核对本地、tracking 与 GitHub SHA。

## Commit sequence / 提交序列

1. `df7a38a` — `docs: 启动贴吧首楼图片闭环 / start Tieba first-floor image pipeline`
2. `8a0e935` — `feat: 闭环贴吧首楼图片 / close Tieba first-floor image pipeline`
3. This documentation closeout commit / 本次文档收尾提交 — `docs: 收尾贴吧首楼图片闭环 / close Tieba first-floor image pipeline`; its self-referential SHA is intentionally left to Git history / 其自引用 SHA 有意只保留在 Git 历史中。

`.upstream` must remain excluded, unmodified and clean throughout this execution. / 整个执行期间，`.upstream` 必须继续排除在跟踪外、保持未修改且干净。
