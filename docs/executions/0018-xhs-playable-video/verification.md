# Execution 0018 verification / 执行 0018 验证记录

- Status / 状态：Offline implementation and documentation gates pass; live qualification `NOT_RUN` / 离线实现与文档门禁通过；真人验收 `NOT_RUN`
- Date / 日期：2026-09-01
- Plan commit / 计划提交：`c9d3586`
- Implementation commit / 实现提交：`356e254`

## Selection evidence / 选型证据

| Candidate / 候选 | Locked evidence / 锁定证据 | Decision / 决策 |
| --- | --- | --- |
| XHS video / 小红书视频 | `store/xhs/__init__.py` emits origin-key or H.264 `video_url`; media-sync already normalizes VIDEO, refreshes XHS and probes/archives/publishes video. / `store/xhs/__init__.py` 输出 origin-key 或 H.264 `video_url`；media-sync 已能归一化 VIDEO、刷新小红书并探测/归档/发布视频。 | Execution 0018 / 本轮实现 |
| Tieba static images / 贴吧静态图片 | `TiebaNote` has no media field; first-floor API/HTML media is discarded before JSONL and anti-hotlink fields require a frozen redacted fixture. / `TiebaNote` 无媒体字段；首楼 API/HTML 媒体在 JSONL 前被丢弃，且防盗链字段需要冻结的脱敏夹具。 | Future integration shim / 后续集成 shim |
| Zhihu static/video / 知乎静态图/视频 | `ZhihuContent` retains text/landing URL only; HTML image attributes and nested playable-video structures are discarded before JSONL. / `ZhihuContent` 只保留文本/落地页 URL；HTML 图片属性及嵌套可播放视频结构在 JSONL 前被丢弃。 | Future integration shim / 后续集成 shim |

## Implementation evidence / 实现证据

| Scope / 范围 | Result / 结果 | Evidence / 证据 |
| --- | --- | --- |
| Locked upstream source shape / 锁定上游源码形状 | `PASS` | The contract verifies the pinned checkout, AST-extracts and executes its real XHS store functions, covering `origin_video_key`, `originVideoKey`, H.264 `master_url`, comma-scalar video and scalar image output. / 合约先校验锁定 checkout，再通过 AST 提取并执行真实小红书 store 函数，覆盖 `origin_video_key`、`originVideoKey`、H.264 `master_url`、逗号标量视频及标量图片输出。 |
| Initial XHS media locator / 小红书初始媒体 locator | `PASS` | Ordinary bounded HTTP/HTTPS, strict LDH/IDNA XHS CDN host, default port and non-root-path cases pass; userinfo, whitespace/control, fragment, malformed/foreign/custom-port cases fail closed. Redirects retain the existing per-hop public-network policy. / 普通有界 HTTP/HTTPS、严格 LDH/IDNA 小红书 CDN host、默认端口及非根路径用例通过；userinfo、空白/控制字符、fragment、畸形/外域/自定义端口用例关闭失败；重定向继续使用既有逐跳公网策略。 |
| Automatic creator-video target / 自动作者视频目标 | `PASS` | Exactly one raw scalar VIDEO and zero or one raw scalar IMAGE map one-to-one to ordinary `type="video"` VIDEO/MIXED content; duplicates, empty segments, whitespace, malformed+valid lists, multiple candidates, container drift and identity drift are rejected. / 精确一个 raw 标量 VIDEO 与零或一个 raw 标量 IMAGE 一一映射为普通 `type="video"` VIDEO/MIXED 内容；重复、空分段、空白、畸形+有效列表、多候选、容器漂移及身份漂移均被拒绝。 |
| Process and refresh contract / 进程与刷新合约 | `PASS` | A real isolated fake checkout proves bounded creator mode, exact URL selection, DEFAULT profile, successful cleanup and repr-safe authority handling; the explicit exact-note compatibility path remains unchanged. / 真实隔离 fake checkout 证明有界 creator 模式、精确 URL 选择、DEFAULT profile、成功清理及 repr-safe 权限处理；显式精确 note 兼容路径保持不变。 |
| Video validity / 视频有效性 | `PASS` | An embedded real H.264 MP4 passes production `FFprobeMediaProbe`; this proof is separate from the deterministic recording-probe composition. / 内嵌真实 H.264 MP4 通过生产 `FFprobeMediaProbe`；该证据与确定性记录型 probe 组合相互独立。 |
| Download/archive/Emby composition / 下载/归档/Emby 组合 | `PASS` | Exact SQLite provenance, creator lookup, mock public DNS/HTTP, controlled MP4/PNG, SHA-256 archive and idempotent `.mp4`/poster/NFO/source publication pass. Query-only replay adds no detail, DNS, HTTP, probe, archive or export work. / 精确 SQLite 来源、作者查找、mock 公网 DNS/HTTP、受控 MP4/PNG、SHA-256 归档及幂等 `.mp4`/poster/NFO/source 发布通过；仅 query 变化的重放不新增 detail、DNS、HTTP、probe、归档或导出工作。 |
| Durable/ephemeral boundary / 持久与瞬态边界 | `PASS` | Durable raw, Asset hints, SQLite, archive metadata, Emby output and completed attempt cleanup retain no signed query, userinfo or fragment; `.upstream` remains clean and untracked. / 持久 raw、Asset hint、SQLite、归档元数据、Emby 输出及已完成 attempt 清理均不保留签名 query、userinfo 或 fragment；`.upstream` 保持干净且未跟踪。 |

## Test and quality gates / 测试与质量门禁

| Check / 检查 | Command / 命令 | Result / 结果 |
| --- | --- | --- |
| Pre-edit seven-file baseline / 编辑前七文件基线 | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_asset_download_orchestration.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_pipeline_runtime.py tests/integration/test_xhs_creator_authority_pipeline.py tests/unit/test_mediacrawler_refresh.py` | `PASS` — `167 passed in 46.50s` |
| Focused nine-file pytest / 九文件专项 pytest | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_xhs_upstream_video_store.py tests/integration/test_asset_download_orchestration.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_pipeline_runtime.py tests/integration/test_xhs_creator_authority_pipeline.py tests/integration/test_xhs_playable_video_pipeline.py tests/unit/test_mediacrawler_refresh.py` | `PASS` — `222 passed in 43.69s` |
| Locked upstream source contract / 锁定上游源码合约 | `uv run pytest -q tests/contract/test_xhs_upstream_video_store.py` | `PASS` — `4 passed` |
| Real H.264 + upstream + composition / 真实 H.264 + 上游 + 组合 | `uv run pytest -q tests/contract/test_xhs_upstream_video_store.py tests/integration/test_xhs_playable_video_pipeline.py` | `PASS` — `6 passed in 8.84s` |
| Complete suite / 完整套件 | `uv run pytest -q` | `PASS` — `1353 passed, 1 skipped in 338.48s`; only skip: Windows POSIX mode-bit / 唯一跳过：Windows POSIX mode-bit |
| Ruff / Ruff | `uv run ruff check .` | `PASS` |
| Format / 格式 | `uv run ruff format --check .` | `PASS` — `241 files already formatted` |
| Strict mypy / 严格 mypy | `uv run mypy src/media_sync` | `PASS` — `80 source files` |
| Compileall / 字节编译 | `uv run python -m compileall -q src/media_sync` | `PASS` |
| Upstream locks / 上游锁 | `uv run python scripts/check_upstreams.py` | `PASS` — 2 checkouts / 两个 checkout |
| Build / 构建 | `uv build` | `PASS` — wheel and sdist / wheel 与 sdist |
| Documentation / 文档 | `uv run python scripts/check_docs.py` | `PASS` — 88 Markdown files checked / 检查 88 个 Markdown 文件 |
| Diff checks / Diff 检查 | `git diff --check`; `git diff --cached --check` | `PASS` |
| Independent final review / 独立最终审查 | Read-only review plus selected regression gate / 只读审查及专项回归 | `PASS` — no P0–P2 findings / 未发现 P0–P2 问题 |

No coverage run is claimed. / 不宣称运行过 coverage。

## Retained/Git audit / 保留产物与 Git 审计

The final read-only PowerShell audit ran `git ls-files`, `git ls-files --others --exclude-standard`, `git ls-files -- archive exports jobs .media-sync dist .upstream`, recursively counted real files below ignored `.media-sync`/`dist`, checked both frozen sentinel roots with `Test-Path`, and counted `git -C <checkout> status --short` for both pinned upstreams. It printed counts only, not retained values or matched paths. Result: `tracked=259`; `untracked=0`; `tracked_runtime_upstream=0`; `runtime_and_build_files=914`; `sentinel_roots_preserved=2/2`; `mediacrawler_dirty_paths=0`; `bili_sync_up_dirty_paths=0`. / 最终只读 PowerShell 审计运行 `git ls-files`、`git ls-files --others --exclude-standard`、`git ls-files -- archive exports jobs .media-sync dist .upstream`，递归统计被忽略的 `.media-sync`/`dist` 下真实文件，以 `Test-Path` 检查两个冻结 sentinel 根，并统计两个锁定上游的 `git -C <checkout> status --short`。审计只打印计数，不打印保留值或命中路径。结果：`tracked=259`；`untracked=0`；`tracked_runtime_upstream=0`；`runtime_and_build_files=914`；`sentinel_roots_preserved=2/2`；`mediacrawler_dirty_paths=0`；`bili_sync_up_dirty_paths=0`。

## Live qualification / 真人在线验收

| Row / 验收行 | Result / 结果 |
| --- | --- |
| Real XHS QR/Cookie login / 真人小红书 QR/Cookie 登录 | `NOT_RUN` |
| Real creator/feed/detail lookup / 真实 creator/feed/detail 查找 | `NOT_RUN` |
| Real XHS CDN video/artwork bytes / 真实小红书 CDN 视频/封面字节 | `NOT_RUN` |
| Real Emby/Jellyfin scan/playback / 真实 Emby/Jellyfin 扫描/播放 | `NOT_RUN` |

Offline mocks do not imply these rows. Execution 0018 is complete for one ordinary `type="video"` row with exactly one VIDEO and zero or one static IMAGE; multi-video, multi-image, broader mixed/live-photo/animation shapes, remaining platforms and the broader user goal remain active work. / 离线 mock 不代表这些行通过。Execution 0018 只完成一条普通 `type="video"` 行、精确一个 VIDEO 与零或一个静态 IMAGE；多视频、多图片、更广混合/实况/动图形状、其余平台及更大的用户目标仍需继续推进。
