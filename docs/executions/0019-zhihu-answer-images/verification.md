# Execution 0019 verification / 执行 0019 验证记录

- Status / 状态：Plan-only checkpoint; offline implementation evidence pending; live qualification `NOT_RUN` / 仅计划检查点；离线实现证据待完成；真人验收 `NOT_RUN`
- Date / 日期：2026-09-01
- Predecessor / 前置：`4fb639a`
- Plan commit / 计划提交：`PENDING`
- Implementation commit / 实现提交：`PENDING`

## Selection evidence / 选型证据

| Candidate / 候选 | Locked evidence / 锁定证据 | Decision / 决策 |
| --- | --- | --- |
| Zhihu creator answer, exactly one static image / 知乎 creator 回答精确一张静态图片 | The default creator path already receives answer `content` HTML, but the locked extractor removes all tags before a media-free `ZhihuContent` is dumped to JSONL. This has an exact integration-owned interception point. / 默认 creator 路径已经收到回答 `content` HTML，但锁定 extractor 会在无媒体字段的 `ZhihuContent` 写入 JSONL 前删除全部标签；该路径具有精确的集成拦截点。 | Execution 0019 / 本轮计划实现 |
| Zhihu answer gallery / 知乎回答多图 gallery | Multiple images introduce ordering, edit/replacement and partial-capture semantics beyond the minimum sixth-platform slice. / 多图片会引入顺序、编辑/替换及部分捕获语义，超出最小第六平台切片。 | Deferred / 延期 |
| Zhihu article media / 知乎文章媒体 | The API requests `content` and `thumbnail`, but the locked creator core comments out article enumeration; enabling and bounding another content family is additional scope. / API 会请求 `content` 与 `thumbnail`，但锁定 creator core 注释了文章枚举；启用并约束另一个内容族属于额外范围。 | Deferred / 延期 |
| Zhihu zvideo playback/cover / 知乎 zvideo 播放/封面 | The locked extractor receives a nested `video` mapping but does not traverse it; pinned source does not freeze its playable/cover key schema, and no real redacted fixture exists. / 锁定 extractor 会收到嵌套 `video` mapping，但不下钻；锁定源码没有冻结其播放/封面键结构，且当前无真实脱敏夹具。 | Deferred pending fixture / 延期，等待夹具 |

## Planned implementation evidence / 计划实现证据

| Scope / 范围 | Current result / 当前结果 | Required evidence / 所需证据 |
| --- | --- | --- |
| Locked upstream loss boundary / 锁定上游丢失边界 | `PENDING` | Verify SHA, execute or AST-bind actual pinned answer extractor, HTML stripper and store functions, and prove image attributes disappear from the unshimmed JSONL row. / 校验 SHA，执行或 AST 绑定真实锁定回答 extractor、HTML 清理器及 store 函数，并证明未安装 shim 的 JSONL 行会丢失图片属性。 |
| Bounded creator pagination / 有界 creator 分页 | `PENDING` | At most Subscription `max_items`, validated page/data/paging shapes and offset progress, no extra page at cap, preserved callback pacing/cancellation/watchdog behavior. / 最多 Subscription `max_items`，校验 page/data/paging 形状及 offset 推进，达到上限无额外页面，并保留 callback 节奏、取消/watchdog 行为。 |
| Runtime shim / 运行时 shim | `PENDING` | Verified module origin, full/idempotent install, partial/collision failures, exact model/content binding, exception cleanup and concurrent task isolation; no `.upstream` edit. / 校验模块来源、完整/幂等安装、部分/冲突失败、精确模型/content 绑定、异常清理及并发任务隔离；不修改 `.upstream`。 |
| One-image HTML and URL gate / 单图 HTML 与 URL 门 | `PENDING` | Exactly one selected static image; zero/multiple/duplicate/ambiguous/malformed-plus-valid/video/animation shapes fail the media claim. Strict HTTPS LDH `zhimg.com` subdomain and path/port/userinfo/fragment/control bounds. / 精确一个选中静态图片；零张/多张/重复/歧义/畸形+有效/video/动图形状不通过媒体声明。严格 HTTPS LDH `zhimg.com` 子域及路径/port/userinfo/fragment/控制字符边界。 |
| Normalized and durable identity / 归一化与持久身份 | `PENDING` | ARTICLE plus exactly one `image:0` Asset, stable `<content_id>:image:0`, private-field stripping and query/userinfo/fragment-free raw/source hint/SQLite. / ARTICLE 加精确一个 `image:0` Asset、稳定 `<content_id>:image:0`、私有字段移除及无 query/userinfo/fragment 的 raw/source hint/SQLite。 |
| Exact answer detail refresh / 精确回答详情刷新 | `PENDING` | Persisted canonical answer URL, exact question/content path validation, one matching answer/IMAGE/hint, current locator revalidation and DEFAULT profile without CDN credential forwarding. / 持久 canonical 回答 URL、精确问题/content 路径校验、唯一匹配回答/IMAGE/hint、当前 locator 再校验及不向 CDN 转发凭据的 DEFAULT profile。 |
| SQLite/archive/Emby composition / SQLite/归档/Emby 组合 | `PENDING` | Exact provenance, mock public DNS/HTTP, production decoding of real static image bytes, SHA-256 archive, poster/gallery/NFO/source publication and query-only zero-work replay. / 精确来源、mock 公网 DNS/HTTP、生产代码解码真实静态图片字节、SHA-256 归档、poster/gallery/NFO/source 发布及仅 query 变化的零工作重放。 |

## Planned test and quality gates / 计划测试与质量门禁

| Check / 检查 | Planned command / 计划命令 | Current result / 当前结果 |
| --- | --- | --- |
| Pre-edit focused baseline / 编辑前专项基线 | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_asset_download_orchestration.py tests/integration/test_pipeline_runtime.py tests/unit/test_mediacrawler_refresh.py` | `PASS` — `255 passed in 48.32s` |
| Locked Zhihu source contract / 锁定知乎源码合约 | `uv run pytest -q tests/contract/test_zhihu_upstream_answer_media.py` | `PENDING` |
| Focused Zhihu image gate / 知乎图片专项门禁 | `uv run pytest -q tests/contract/test_zhihu_upstream_answer_media.py tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_zhihu_answer_image_pipeline.py tests/unit/test_mediacrawler_refresh.py` | `PENDING` |
| Complete suite / 完整套件 | `uv run pytest -q` | `PENDING` |
| Ruff / Ruff | `uv run ruff check .` | `PENDING` |
| Format / 格式 | `uv run ruff format --check .` | `PENDING` |
| Strict mypy / 严格 mypy | `uv run mypy src/media_sync` | `PENDING` |
| Compileall / 字节编译 | `uv run python -m compileall -q src/media_sync` | `PENDING` |
| Upstream locks / 上游锁 | `uv run python scripts/check_upstreams.py` | `PENDING` |
| Build / 构建 | `uv build` | `PENDING` |
| Documentation / 文档 | `uv run python scripts/check_docs.py` | `PENDING` |
| Diff and retained-artifact audit / Diff 与保留产物审计 | `git diff --check` plus retained-artifact/upstream-cleanliness audit / 加保留产物与上游干净性审计 | `PENDING` |
| Independent final review / 独立最终审查 | Read-only review plus selected regression gate / 只读审查及专项回归 | `PENDING` |

No coverage run is planned or claimed unless it is explicitly executed and recorded later. / 除非后续明确执行并记录，否则不计划也不宣称 coverage 运行。

## Source-bound evidence limit / 源码绑定证据限制

The pinned-source contract and synthetic HTML fixtures can prove that the integration intercepts the exact locked loss boundary and handles the frozen shape deterministically without network access. They cannot prove that current live Zhihu emits `data-original`, `data-actualsrc` or `src` in every qualifying answer, nor that the real CDN accepts `MediaRequestProfile.DEFAULT`. Those remain live qualification questions, not offline PASS results. / 锁定源码合约与合成 HTML 夹具可以证明集成在无需网络时拦截精确的锁定丢失边界，并确定性处理冻结形状；它们不能证明知乎现网在每条合格回答中都会输出 `data-original`、`data-actualsrc` 或 `src`，也不能证明真实 CDN 接受 `MediaRequestProfile.DEFAULT`。这些仍属于真人验收问题，不是离线 PASS 结果。

## Retained/Git audit / 保留产物与 Git 审计

No Execution 0019 retained-artifact or post-implementation Git audit has run yet. Closeout must confirm no tracked/untracked runtime artifact, no retained secret-bearing URL or completed attempt root, clean pinned upstream checkouts, and reconciled local/tracking/GitHub SHAs. / Execution 0019 尚未运行保留产物或实现后 Git 审计。收尾必须确认无 tracked/untracked 运行时产物、无保留的含 secret URL 或已完成 attempt 根、锁定上游 checkout 干净，并核对本地/tracking/GitHub SHA。

## Live qualification / 真人在线验收

| Row / 验收行 | Result / 结果 |
| --- | --- |
| Real Zhihu QR/Cookie login / 真人知乎 QR/Cookie 登录 | `NOT_RUN` |
| Real creator answer pagination and detail lookup / 真实 creator 回答分页与详情查找 | `NOT_RUN` |
| Real `zhimg.com` image bytes, redirects and DEFAULT-profile behavior / 真实 `zhimg.com` 图片字节、重定向及 DEFAULT profile 行为 | `NOT_RUN` |
| Real Emby/Jellyfin scan/display / 真实 Emby/Jellyfin 扫描/展示 | `NOT_RUN` |

Offline mocks will not imply these rows. Execution 0019 can qualify only one ordinary answer with exactly one static IMAGE; multiple images, article/zvideo media, complete Zhihu coverage, the seventh media platform and the broader goal remain active work. / 离线 mock 不代表这些行通过。Execution 0019 只能验收一条普通回答中的精确一张静态 IMAGE；多图片、文章/zvideo 媒体、完整知乎覆盖、第七个媒体平台及更大的目标仍需继续推进。
