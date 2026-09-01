# Execution 0019 verification / 执行 0019 验证记录

- Status / 状态：Frozen offline scope passes all final gates; live qualification `NOT_RUN` / 冻结离线范围通过全部最终门禁；真人验收 `NOT_RUN`
- Date / 日期：2026-09-02
- Predecessor / 前置：`4fb639a`
- Plan commit / 计划提交：`dc1714c`
- Implementation commit / 实现提交：`2edb9d763b4948c56cc182bcc5012914bcb644d1`

## Selection evidence / 选型证据

| Candidate / 候选 | Decision / 决策 | Evidence boundary / 证据边界 |
| --- | --- | --- |
| Ordinary creator answer, exactly one static IMAGE / 作者普通回答精确一张静态 IMAGE | Delivered / 已交付 | Locked upstream already receives answer HTML but loses image attributes before JSONL; the verified shim captures the frozen one-image shape and successfully bounds creator execution. / 锁定上游已接收回答 HTML，但会在 JSONL 前丢失图片属性；校验 shim 捕获冻结单图形状并成功约束作者执行。 |
| Answer gallery / 回答多图 gallery | Deferred / 延期 | Ordering, edit/replacement and partial-capture semantics are separate scope. / 顺序、编辑/替换及部分捕获语义属于独立范围。 |
| Article media / 文章媒体 | Deferred / 延期 | The pinned default creator path disables article enumeration. / 锁定默认 creator 路径关闭文章枚举。 |
| Zvideo playback/cover / zvideo 播放/封面 | Deferred pending fixture / 延期，等待夹具 | Nested playable/cover shape remains unfrozen and no real redacted fixture exists. / 嵌套播放/封面形状尚未冻结，且没有真实脱敏夹具。 |

## Implemented offline evidence / 已实现离线证据

| Scope / 范围 | Result / 结果 | Evidence / 证据 |
| --- | --- | --- |
| Locked upstream loss boundary / 锁定上游丢失边界 | `PASS` | Verifies pinned SHA, executes real `extract_text_from_html`, answer extractor/update/JSONL store, AST-binds the `content` include, answers-only dispatch, missing native cap and both child installation points. Real locked Pydantic content carries/consumes the private binding without exposing it through dump/JSON/repr. / 校验锁定 SHA，执行真实 `extract_text_from_html`、回答 extractor/update/JSONL store，以 AST 绑定 `content` include、仅回答 dispatch、缺少原生上限及两个 child 安装点；真实锁定 Pydantic content 可携带/消费私有绑定且不会通过 dump/JSON/repr 暴露。 |
| Runtime shim and creator bound / 运行时 shim 与作者上限 | `PASS` | Exact-object binding crosses `asyncio.gather` child → parent storage and remains task-isolated. Scheduled `max_items=23` produces two API requests and two callback invocations with page sizes `20 + 3`, exactly 23 callback-processed rows and one between-page pacing sleep; there is no third request or post-cap sleep. Empty, short non-terminal, repeated, malformed and cardinality-drift pages fail closed. / 精确对象绑定跨越 `asyncio.gather` child → 父存储且保持任务隔离。Scheduled `max_items=23` 产生页面大小 `20 + 3` 的两次 API 请求与两次 callback 调用，callback 精确处理 23 行，页间执行一次节奏 sleep；达到上限后没有第三次请求或额外 sleep。空页、短非终止页、重复页、畸形页与基数漂移均关闭失败。 |
| HTML and URL gate / HTML 与 URL 门 | `PASS` | Frozen attribute priority, duplicate/competing candidate rejection, multiple/playable/container-drift rejection, strict positive IDs and bounded canonical URLs are covered, including empty query/fragment delimiter rejection. / 已覆盖冻结属性优先级、重复/竞争候选拒绝、多图/可播放/容器漂移拒绝、严格正 ID 与有界 canonical URL，包括空 query/fragment 分隔符拒绝。 |
| Durable identity and refresh / 持久身份与刷新 | `PASS` | ARTICLE plus one `<content_id>:image:0` IMAGE, recursive private-field stripping, query-free SQLite hint, exact canonical answer authority, parent/child/current-locator revalidation and credential-free DEFAULT profile pass. Historical assetless answers remain compatible. / ARTICLE 加唯一 `<content_id>:image:0` IMAGE、递归私有字段移除、无 query SQLite hint、精确 canonical 回答权限、父/child/当前 locator 复核及无凭据 DEFAULT profile 均通过；历史无 Asset 回答保持兼容。 |
| Static structural qualification / 静态结构资格校验 | `PASS` | Zhihu IMAGE automatically enables the production gate. Qualified JPEG/PNG/WebP pass; GIF/APNG/animated WebP/AVIF fail. Normal, recovery and takeover paths preserve the flag. The gate is bounded structural/container qualification, not complete pixel decoding. / 知乎 IMAGE 自动启用生产门；合格 JPEG/PNG/WebP 通过，GIF/APNG/animated WebP/AVIF 失败；normal、recovery 与 takeover 路径保留该标志。该门是有界结构/容器资格校验，不是完整像素解码。 |
| SQLite/archive/Emby composition / SQLite/归档/Emby 组合 | `PASS` | Exact provenance, fake detail, mock public DNS/HTTP, production byte gate, SHA-256 archive, poster/backdrop/gallery/body/NFO/source publication and query-only zero-work replay pass. Private/transient values are absent from SQLite/runtime/archive/export and WAL/SHM sidecars. / 精确来源、fake detail、mock 公网 DNS/HTTP、生产字节门、SHA-256 归档、poster/backdrop/gallery/body/NFO/source 发布及仅 query 变化的零工作重放通过；SQLite/runtime/archive/export 与 WAL/SHM sidecar 均不含私有/瞬态值。 |

## Test and quality gates / 测试与质量门禁

| Check / 检查 | Command / 命令 | Result / 结果 |
| --- | --- | --- |
| Pre-edit focused baseline / 编辑前专项基线 | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_asset_download_orchestration.py tests/integration/test_pipeline_runtime.py tests/unit/test_mediacrawler_refresh.py` | `PASS` — `255 passed in 48.32s` |
| First focused combined gate / 首次专项联合门 | `uv run pytest -q tests/unit/test_zhihu_media.py tests/contract/test_zhihu_upstream_answer_store.py tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_zhihu_answer_image_pipeline.py tests/contract/test_mediacrawler_bridge.py::test_full_history_acknowledgement_matches_audited_platforms` | `PASS` — `364 passed in 41.04s` |
| First isolated SQLite-to-Emby composition / 首次隔离 SQLite→Emby 组合 | `uv run pytest -q tests/integration/test_zhihu_answer_image_pipeline.py` | `PASS` — `1 passed` |
| Final expanded focused gate / 最终扩大专项门 | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run pytest -q -p no:cacheprovider tests/unit/test_zhihu_media.py tests/contract/test_zhihu_upstream_answer_store.py tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_zhihu_answer_image_pipeline.py tests/integration/test_zhihu_scheduled_creator_bound.py tests/unit/test_media_downloader.py tests/integration/test_asset_download_orchestration.py tests/unit/test_media_locator.py tests/contract/test_mediacrawler_bridge.py::test_full_history_acknowledgement_matches_audited_platforms` | `PASS` — `505 passed in 48.82s` |
| Complete suite / 完整套件 | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run pytest -q -p no:cacheprovider` | `PASS` — `1543 passed, 1 skipped in 318.39s`; skip is the Windows-inapplicable POSIX mode-bit boundary / `1543 passed, 1 skipped in 318.39s`；跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff / Ruff | `uv run ruff check .` | `PASS` — all checks passed / 全部检查通过 |
| Format / 格式 | `uv run ruff format --check .` | `PASS` — `250 files already formatted` |
| Strict mypy / 严格 mypy | `uv run mypy src/media_sync` | `PASS` — no issues in 81 source files / 81 个源码文件无问题 |
| Compileall / 字节编译 | `uv run python -m compileall -q src/media_sync` | `PASS` |
| Upstream locks / 上游锁 | `uv run python scripts/check_upstreams.py` | `PASS` — 2 locked checkouts verified / 2 个锁定 checkout 已验证 |
| Build / 构建 | `uv build` | `PASS` — wheel and source distribution built / wheel 与源码包构建成功 |
| Documentation / 文档 | `uv run python scripts/check_docs.py` | `PASS` |
| Diff, retained-artifact and upstream audit / Diff、保留产物与上游审计 | `git diff --check` plus secret-sentinel, SQLite/WAL/SHM, retained-tree and upstream-cleanliness checks / 加密钥哨兵、SQLite/WAL/SHM、保留目录及上游干净性检查 | `PASS` — tracked `268`; untracked `0`; tracked runtime/upstream `0`; runtime/build files `914`; execution-0019 retained-marker hits `0`; frozen sentinel roots `2/2`; both upstream dirty-path counts `0` / tracked `268`；untracked `0`；tracked runtime/upstream `0`；runtime/build 文件 `914`；执行 0019 保留 marker 命中 `0`；冻结 sentinel 根 `2/2`；两个上游 dirty path 计数均为 `0` |
| Independent final review / 独立最终审查 | `uv run pytest -q tests/unit/test_zhihu_media.py tests/contract/test_zhihu_upstream_answer_store.py tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_asset_download_orchestration.py tests/unit/test_media_downloader.py tests/integration/test_zhihu_scheduled_creator_bound.py tests/integration/test_zhihu_answer_image_pipeline.py` | `PASS` — `461 passed in 44.33s`; no P0/P1/P2 findings / `461 passed in 44.33s`；未发现 P0/P1/P2 |

No coverage run is claimed. / 不宣称运行过 coverage。

## Source-bound evidence limit / 源码绑定证据限制

The pinned-source contract and synthetic HTML prove the locked interception boundary and deterministic frozen shape without network access. There is no real redacted Zhihu answer/API fixture, so the evidence does not prove current live attributes, creator/detail API compatibility, real `zhimg.com` redirect/profile behavior or complete pixel decoding of every image. It does prove the bounded structural cases above, including rejection of the tested GIF, APNG, animated WebP and AVIF payloads. / 锁定源码合约与合成 HTML 在无需网络时证明锁定拦截边界及冻结形状的确定性处理。当前没有真实脱敏知乎回答/API 夹具，因此证据不证明现网属性、creator/detail API 兼容性、真实 `zhimg.com` 重定向/profile 行为或每张图片的完整像素解码；它确实证明上述有界结构用例，包括拒绝已测试的 GIF、APNG、animated WebP 与 AVIF 字节。

## Git and live qualification / Git 与真人验收

Implementation commit `2edb9d763b4948c56cc182bcc5012914bcb644d1` is reconciled across local `main`, `origin/main` and GitHub. The commit containing this record is the bilingual documentation closeout; its self-referential SHA is intentionally not embedded, and post-push local/tracking/GitHub reconciliation is reported in the task handoff. / 实现提交 `2edb9d763b4948c56cc182bcc5012914bcb644d1` 已在本地 `main`、`origin/main` 与 GitHub 间核对一致。包含本记录的提交即双语文档收尾；其自引用 SHA 有意不嵌入，推送后的本地/tracking/GitHub 核对结果在任务交接中报告。

| Live row / 真人验收行 | Result / 结果 |
| --- | --- |
| Real Zhihu QR/Cookie login / 真人知乎 QR/Cookie 登录 | `NOT_RUN` |
| Real creator answer pagination / 真人 creator 回答分页 | `NOT_RUN` |
| Real answer detail lookup / 真人回答详情查找 | `NOT_RUN` |
| Real `zhimg.com` bytes, redirects and DEFAULT profile / 真实 `zhimg.com` 字节、重定向与 DEFAULT profile | `NOT_RUN` |
| Real Emby/Jellyfin scan/display / 真实 Emby/Jellyfin 扫描/展示 | `NOT_RUN` |

Offline mocks do not imply these live rows. Execution 0019 delivers only one ordinary answer with exactly one static IMAGE on the sixth media platform. Multiple images, articles, zvideo, complete Zhihu coverage, Tieba media and the broader seven-platform goal remain active work. / 离线 mock 不代表真人行通过。Execution 0019 只交付第六个媒体平台上一条普通回答中的精确一张静态 IMAGE；多图、文章、zvideo、完整知乎覆盖、贴吧媒体及更大的七平台目标仍需继续推进。
