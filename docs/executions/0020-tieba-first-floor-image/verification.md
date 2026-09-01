# Execution 0020 verification / 执行 0020 验证记录

- Status / 状态：Plan checkpoint; pre-edit and current-shape evidence pass; implementation pending; authenticated/live qualification `NOT_RUN` / 计划检查点；编辑前与当前形状证据通过；实现待执行；登录/现网验收 `NOT_RUN`
- Date / 日期：2026-09-02
- Predecessor / 前置：`431fd855dafce502e83f74a055a4b27ae5c6f40b`
- Plan commit / 计划提交：`PENDING`
- Implementation commit / 实现提交：`PENDING`

## Selection evidence / 选型证据

| Candidate / 候选 | Evidence boundary / 证据边界 | Decision / 决策 |
| --- | --- | --- |
| Ordinary creator thread, exactly one first-floor static IMAGE / 作者普通主题首楼精确一张静态 IMAGE | Locked `page_pc` passes full `first_floor.content` to the extractor, current public responses expose one integer type-3 item with `origin_src`, and the present text extractor discards it before JSONL. / 锁定 `page_pc` 把完整 `first_floor.content` 交给 extractor；当前公开响应会暴露一个含 `origin_src` 的整数 type-3 项；现有文本 extractor 会在 JSONL 前丢弃它。 | Execution 0020 / 本轮实现 |
| First-floor gallery / 首楼多图 gallery | Real audited rows include multiple type-3 items, but ordering/replacement/partial-refresh semantics are a separate scope. / 真实审计行中存在多个 type-3 项，但顺序、替换与部分刷新语义属于独立范围。 | Deferred / 延期 |
| Video/voice/emoji/link/rich card / 视频/语音/表情/链接/富卡片 | Other integer content types exist in current responses; their exact schemas and Emby semantics are not frozen. / 当前响应存在其他整数 content type，其精确 schema 与 Emby 语义尚未冻结。 | Deferred / 延期 |
| Replies/comments media / 回复/评论媒体 | This execution intercepts only `first_floor` note detail and note JSONL storage. / 本执行只拦截 `first_floor` 主题详情与主题 JSONL 存储。 | Deferred / 延期 |

## Read-only current-response evidence / 当前响应只读证据

The following evidence was produced transiently on 2026-09-02 and is summarized without response bodies, personal data, signed query values or saved fixtures. It is useful for freezing the current contract but is not a reproducible offline test and does not qualify authenticated flows or future platform behavior. / 以下证据于 2026-09-02 瞬态产生，仅保留摘要，不保留响应正文、个人数据、签名 query 值或保存夹具。它可用于冻结当前合约，但不是可复现离线测试，也不验收登录流程或未来平台行为。

| Check / 检查 | Result / 结果 |
| --- | --- |
| Signed anonymous `/c/s/pc/sync` / 匿名签名 `/c/s/pc/sync` | `PASS` — HTTP 200, `error_code=0`, public TBS returned transiently / HTTP 200、`error_code=0`，瞬态返回公开 TBS |
| Bounded `page_pc` sample scan / 有界 `page_pc` 样本扫描 | `PASS` — 18 candidate IDs requested; real zero-, one- and two-image rows observed; no body retained / 请求 18 个候选 ID；观察到真实零图、单图与双图行；未保留正文 |
| One-image item keys / 单图 item 键 | `PASS` — `type=3`; `origin_src`, `cdn_src`, `big_cdn_src`, `cdn_src_active`, `pic_id`, `bsize`, `origin_size`, `is_long_pic`, `show_original_btn` observed / 观察到上述键 |
| Origin authority / Origin 权限 | `PASS` — HTTPS exact `tiebapic.baidu.com`, `/forum/pic/item/<40-hex>.jpg`, one `tbpicau` query key / HTTPS 精确 host、规范路径、唯一 query 键 |
| Signed DEFAULT-profile byte check / 带签名 DEFAULT-profile 字节检查 | `PASS for observed request only / 仅观察请求通过` — HTTP 200 `image/jpeg`, 65,144 bytes, JPEG magic |
| Query-free comparison / 无 query 对照 | `PASS as risk evidence / 风险证据通过` — HTTP 200 `image/jpeg`, 4,262 bytes, different body length; HTTP success alone is insufficient / 字节长度不同；仅 HTTP 成功不足以作为验收 |

## Planned implementation evidence / 计划实现证据

| Scope / 范围 | Current result / 当前结果 | Required evidence / 所需证据 |
| --- | --- | --- |
| Locked loss boundary / 锁定丢失边界 | `PENDING` | Execute real pinned extractor/model/store objects and prove the unshimmed row loses type-3 fields while `.upstream` stays clean. / 执行真实锁定 extractor/model/store 对象，证明未安装 shim 的行丢失 type-3 字段，同时 `.upstream` 保持干净。 |
| Current type-3 gate / 当前 type-3 门 | `PENDING` | Exact one-image/text-only sibling shape, bounded list/keys/scalars, strict signed URL and query-free hint; zero/multiple/other/drift cases fail the media claim. / 精确单图/仅文本兄弟形状、有界列表/键/标量、严格签名 URL 与无 query 提示；零图/多图/其他/drift 不通过媒体声明。 |
| Exact-object capture / 精确对象捕获 | `PENDING` | Verified origins; full/idempotent install; partial/collision failures; gather-child → parent-store object carry; nested-store ContextVar isolation; no serialization/leakage. / 校验来源；完整/幂等安装；部分/冲突失败；gather 子任务 → 父存储对象携带；嵌套 store ContextVar 隔离；不序列化/不泄漏。 |
| Scheduled creator cap / 定时作者上限 | `PENDING` | `max_items=23` becomes detail/callback batches `20+3`, no third request or post-cap sleep; repeated/malformed/drift pages fail closed. / `max_items=23` 形成 `20+3` 详情/callback 批次，无第三次请求或达到上限后的 sleep；重复/畸形/drift 页面关闭失败。 |
| Normalization and durable identity / 归一化与持久身份 | `PENDING` | ARTICLE plus exact `<note_id>:image:0`; private field/query absent recursively from raw, SQLite and retained trees. / ARTICLE 加精确 `<note_id>:image:0`；私有字段/query 递归地不进入 raw、SQLite 与保留树。 |
| Exact detail refresh / 精确详情刷新 | `PENDING` | Canonical persisted note authority, one exact ARTICLE/IMAGE/hint match, revalidated current signed locator and credential-free DEFAULT profile. / canonical 持久主题权限、唯一精确 ARTICLE/IMAGE/hint 匹配、重新校验当前签名 locator 与无凭据 DEFAULT profile。 |
| Static byte gate / 静态字节门 | `PENDING` | Qualified JPEG/PNG/WebP accepted; GIF/APNG/animated WebP/AVIF rejected; preparation paths preserve the requirement. / 合格 JPEG/PNG/WebP 接受；GIF/APNG/animated WebP/AVIF 拒绝；准备路径保留要求。 |
| SQLite/archive/Emby composition / SQLite/归档/Emby 组合 | `PENDING` | Exact provenance, fake detail, mock public DNS/HTTP, production byte gate, SHA-256 archive, poster/backdrop/gallery/body/NFO/source and zero-work replay. / 精确来源、fake detail、mock 公网 DNS/HTTP、生产字节门、SHA-256 归档、poster/backdrop/gallery/body/NFO/source 及零工作重放。 |

## Test and quality gates / 测试与质量门禁

| Check / 检查 | Command / 命令 | Result / 结果 |
| --- | --- | --- |
| Pre-edit focused baseline / 编辑前专项基线 | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_asset_download_orchestration.py tests/integration/test_pipeline_runtime.py tests/unit/test_mediacrawler_refresh.py` | `PASS — 307 passed in 36.66s` |
| Upstream locks / 上游锁 | `uv run python scripts/check_upstreams.py` | `PASS — Upstreams OK (2 locked checkouts verified)` |
| Upstream worktrees / 上游工作树 | `git -C .upstream/MediaCrawler status --short --branch` and bili-sync-up equivalent / 及 bili-sync-up 对应命令 | `PASS — both clean on main...origin/main / 两者均干净` |
| Locked Tieba source contract / 锁定贴吧源码合约 | `uv run pytest -q tests/contract/test_tieba_upstream_first_floor_media.py` | `PENDING` |
| Focused Tieba gate / 贴吧专项门 | Planned targeted test set recorded after implementation / 实现后记录计划专项集合 | `PENDING` |
| Complete suite / 完整套件 | `uv run pytest -q` | `PENDING` |
| Ruff / Ruff | `uv run ruff check .` | `PENDING` |
| Format / 格式 | `uv run ruff format --check .` | `PENDING` |
| Strict mypy / 严格 mypy | `uv run mypy src/media_sync` | `PENDING` |
| Compileall / 字节编译 | `uv run python -m compileall -q src/media_sync` | `PENDING` |
| Build / 构建 | `uv build` | `PENDING` |
| Documentation / 文档 | `uv run python scripts/check_docs.py` | `PENDING` |
| Diff/retained-artifact audit / Diff/保留产物审计 | `git diff --check` plus explicit retained-tree and upstream audit / 加显式保留树及上游审计 | `PENDING` |

## Live qualification / 登录与现网验收

| Row / 验收行 | Result / 结果 |
| --- | --- |
| Real Tieba QR/Cookie login / 真人贴吧 QR/Cookie 登录 | `NOT_RUN` |
| Authenticated creator enumeration and exact detail / 登录态作者枚举与精确详情 | `NOT_RUN` |
| Future real CDN token/redirect/byte behavior / 未来真实 CDN token/重定向/字节行为 | `NOT_RUN` — one transient anonymous observation is recorded separately / 已单独记录一次瞬态匿名观察 |
| Real Emby/Jellyfin scan/display / 真实 Emby/Jellyfin 扫描/展示 | `NOT_RUN` |

Offline mocks and the transient public observation cannot imply these rows. Execution 0020 is limited to one frozen ordinary first-floor static-image slice. / 离线 mock 与瞬态公开观察均不能代表这些验收行通过。Execution 0020 仅限一个冻结的普通首楼静态图片切片。
