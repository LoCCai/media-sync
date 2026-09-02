# Execution 0027 verification / 执行 0027 验证记录

- Status / 状态：Frozen offline scope passes all final gates; authenticated/live qualification `NOT_RUN` / 冻结离线范围通过全部最终门禁；登录/现网验收 `NOT_RUN`
- Date / 日期：2026-09-02
- Predecessor / 前置：`245e8e377761ee8343b33f581dfcd27295eac532`
- Plan commit / 计划提交：`ec7095a9cc5e85fda1aee66f256eb16345c1294a`
- Implementation commit / 实现提交：`7f99aa480328a25b7e9c2acc8a9c2234128e7b74`

## Baseline / 前置基线

| Check / 检查 | Result / 结果 |
| --- | --- |
| Execution 0026 focused regression / Execution 0026 专项回归 | `PASS — 490 passed in 73.31s` |
| Execution 0026 complete suite / Execution 0026 完整套件 | `PASS — 1814 passed, 1 skipped in 342.33s` |
| Single-/multipart/DASH closeout reruns / 单 P/多分 P/DASH 收尾复验 | `PASS — 1 passed in 1.45s; 1 passed in 1.70s; 1 passed in 1.87s` |
| Documentation and upstream locks / 文档与上游锁 | `PASS — 120 Markdown files; 2 locked clean checkouts / 120 份 Markdown；2 个锁定且干净的 checkout` |
| Repository audit / 仓库审计 | `PASS — tracked 308; untracked 0; tracked runtime/upstream/dist 0 / 跟踪 308；未跟踪 0；跟踪 runtime/upstream/dist 0` |
| Local/tracking/GitHub reconciliation / 本地/tracking/GitHub 核对 | `PASS — 245e8e377761ee8343b33f581dfcd27295eac532` |

## Implemented evidence / 已实现证据

| Scope / 范围 | Result / 结果 |
| --- | --- |
| Protocol-v7 closed format classification / v7 协议封闭格式分类 | `PASS` — only an explicit valid top-level format containing FLV grants FLV authority; absent/`None` and MP4 remain ordinary, while unknown, mixed FLV+MP4, malformed or non-string values have fixed fail-closed outcomes / 只有显式合法且包含 FLV 的顶层格式授予 FLV 权限；缺失/`None` 与 MP4 保持普通类型，未知、FLV+MP4 混合、畸形或非字符串值均有固定关闭失败结果 |
| Typed target and bridge compatibility / 类型化 target 与桥接兼容 | `PASS` — one Bilibili-profile `ResolvedLocator` is wrapped repr-safely; exact single-/multipart private markers reconstruct it, collide recursively and disappear before persistence; historical marker-free payloads remain ordinary / 一个 Bilibili profile `ResolvedLocator` 被 repr-safe 包装；精确单 P/多分 P 私有标记可重建它、递归检测碰撞并在持久化前消失；历史无标记 payload 保持普通类型 |
| Source and final structural gates / 源与成品结构门 | `PASS` — video-bearing FLV is accepted, audio-only/non-FLV source is rejected, and only a final probing exactly as `video/mp4`/`.mp4` may publish / 含视频流 FLV 可接受，纯音频/非 FLV 源被拒绝，且只有精确探测为 `video/mp4`/`.mp4` 的成品才可发布 |
| Fixed bounded remux / 固定有界转封装 | `PASS` — non-shell argv maps `0:v:0` and optional `0:a:0?`, uses `-c copy`, fixed MP4 output, timeout/output/media caps and input/output identity checks; process, empty, oversized and alias failures close safely / 非 shell 参数映射 `0:v:0` 与可选 `0:a:0?`，使用 `-c copy`、固定 MP4 输出、超时/输出/媒体上限及输入/输出身份检查；进程、空、超限与别名失败安全关闭 |
| Ordered download and auth refresh / 有序下载与鉴权刷新 | `PASS` — primary failure advances to ordered backup with strict partial continuity; one all-`401`/`403` adapter pass refreshes once, and refreshed target-type drift returns `locator_refresh_schema_changed` / 主地址失败后按序推进备用并保持严格 partial 连续；adapter 一轮全部 `401`/`403` 后刷新一次，刷新 target 类型漂移返回 `locator_refresh_schema_changed` |
| Recovery and cleanup / 恢复与清理 | `PASS` — remux/final-gate failure retains the verified generation source, removes the unprepared final, retries through strict completed-range evidence, recovers an already-published final without detail/DNS/HTTP/ffmpeg and cleans all source/final stores / 转封装/成品门失败保留已验证 generation 源、移除未准备成品，通过严格已完成 Range 证据重试；已发布成品无需 detail/DNS/HTTP/ffmpeg 即可恢复，并可清理全部源/成品 store |
| Production FLV → Emby composition / 生产 FLV → Emby 组合 | `PASS` — a generated local H.264+AAC FLV traverses SQLite → primary `503` → backup → production ffprobe → production ffmpeg stream-copy → final ffprobe → immutable SHA-256 `.mp4` → Emby `.mp4`/NFO/source; both output copies contain video and audio / 生成的本地 H.264+AAC FLV 贯穿 SQLite → 主地址 `503` → 备用 → 生产 ffprobe → 生产 ffmpeg stream-copy → 最终 ffprobe → 不可变 SHA-256 `.mp4` → Emby `.mp4`/NFO/source；两份输出均含视频与音频 |
| Zero-work replay and non-retention / 零工作重放与不保留 | `PASS` — replay adds zero detail/DNS/HTTP/probe/ffmpeg/archive/export work; retained runtime/work/archive/export/library/SQLite evidence contains no signed primary/backup URL, private marker or published `.flv` / 重放不新增 detail/DNS/HTTP/probe/ffmpeg/archive/export 工作；保留 runtime/work/archive/export/library/SQLite 证据均不含签名主/备用 URL、私有标记或已发布 `.flv` |
| Compatibility / 兼容 | `PASS` — no-format/MP4 progressive, single-/multipart backup paths, DASH, static media, published recovery and the twelve frozen media-shape count remain green / 无格式/MP4 progressive、单 P/多分 P 备用路径、DASH、静态媒体、已发布恢复与十二个冻结媒体形状计数保持通过 |

## Test and quality gates / 测试与质量门禁

| Check / 检查 | Command / 命令 | Result / 结果 |
| --- | --- | --- |
| Focused implementation regression / 实现专项回归 | `uv run pytest -q tests/unit/test_media_locator.py tests/unit/test_media_probe.py tests/unit/test_media_mux.py tests/unit/test_media_downloader.py tests/unit/test_media_dash_downloader.py tests/unit/test_media_flv_downloader.py tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py` | `PASS — 394 passed in 59.12s` |
| Bilibili compatibility and production compositions / Bilibili 兼容与生产组合 | `uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_bilibili_multipart_progressive_pipeline.py tests/integration/test_bilibili_dash_pipeline.py` | `PASS — 4 passed in 4.51s` |
| Production FLV closeout rerun / 生产 FLV 收尾复验 | `uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py::test_bilibili_flv_backup_reaches_emby_through_production_remux_with_zero_work_replay` | `PASS — 1 passed in 1.82s` |
| Complete suite / 完整套件 | `uv run pytest -q` | `PASS — 1848 passed, 1 skipped in 347.72s`; skip is the Windows-inapplicable POSIX mode-bit boundary / 跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff and format / Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 295 files already formatted / 全部通过；295 个文件格式正确` |
| Strict mypy / 严格 mypy | `uv run mypy --strict src` | `PASS — no issues in 84 source files / 84 个源码文件无问题` |
| Compileall and build / 字节编译与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — wheel and source distribution built / wheel 与源码包构建成功` |
| Documentation and upstream locks / 文档与上游锁 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 124 Markdown files; 2 locked checkouts / 124 份 Markdown；2 个锁定 checkout` |
| Git/upstream/diff audit / Git/上游/diff 审计 | explicit status, tracked/runtime/upstream and diff checks / 显式状态、跟踪/runtime/upstream 与 diff 检查 | `PASS — tracked 313; untracked 0; tracked runtime/upstream/dist 0; both upstream dirty counts 0; locked SHAs exact / 跟踪 313；未跟踪 0；跟踪 runtime/upstream/dist 0；两个上游 dirty 数均为 0；锁定 SHA 精确` |

No coverage run is claimed. / 不宣称运行过 coverage。

## Git reconciliation / Git 核对

Plan `ec7095a9cc5e85fda1aee66f256eb16345c1294a` and implementation `7f99aa480328a25b7e9c2acc8a9c2234128e7b74` are pushed and reconciled across local `main`, `origin/main` and GitHub. The commit containing this record is the bilingual documentation closeout; its self-referential SHA is intentionally left to Git history. / 计划 `ec7095a9cc5e85fda1aee66f256eb16345c1294a` 与实现 `7f99aa480328a25b7e9c2acc8a9c2234128e7b74` 已推送并在本地 `main`、`origin/main` 与 GitHub 间核对一致。包含本记录的提交即双语文档收尾；其自引用 SHA 有意只保留在 Git 历史中。

## Live qualification / 登录与现网验收

| Row / 验收行 | Result / 结果 |
| --- | --- |
| Real Bilibili QR/Cookie login / 真人 Bilibili QR/Cookie 登录 | `NOT_RUN` |
| Authenticated FLV detail/play API / 登录态 FLV 详情/播放 API | `NOT_RUN` |
| Real primary/backup bilivideo FLV CDN behavior / 真实主/备用 bilivideo FLV CDN 行为 | `NOT_RUN` |
| Real Bilibili FLV bytes with production ffmpeg/ffprobe / 真实 Bilibili FLV 字节与生产 ffmpeg/ffprobe | `NOT_RUN` |
| Real Emby/Jellyfin scan and playback / 真实 Emby/Jellyfin 扫描与播放 | `NOT_RUN` |

Offline evidence cannot imply these live rows, multiple `durl` segments, concatenation, transcoding, CDN ranking/racing/cache or complete Bilibili support. / 离线证据不能代表上述真人行、多 `durl` 分段、拼接、转码、CDN 排序/竞速/缓存或完整 Bilibili 支持通过。
