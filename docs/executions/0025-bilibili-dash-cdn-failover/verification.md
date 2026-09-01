# Execution 0025 verification / 执行 0025 验证记录

- Status / 状态：Frozen offline scope passes all final gates; authenticated/live qualification `NOT_RUN` / 冻结离线范围通过全部最终门禁；登录/现网验收 `NOT_RUN`
- Date / 日期：2026-09-02
- Predecessor / 前置：`46905a50bbba19b7c4b74a0f7a274d5efdb013d6`
- Plan commit / 计划提交：`8e9467d2ecbedfd8f87e8d1d2ffb5a66d6d15591`
- Implementation commit / 实现提交：`fe45abcb7262c3d70437aff82a05609e43902af4`

## Baseline / 前置基线

| Check / 检查 | Result / 结果 |
| --- | --- |
| Execution 0024 focused regression / Execution 0024 专项回归 | `PASS — 456 passed in 66.47s` |
| Execution 0024 complete suite / Execution 0024 完整套件 | `PASS — 1780 passed, 1 skipped in 333.43s` |
| Production ffmpeg/ffprobe closeout rerun / 生产 ffmpeg/ffprobe 收尾复验 | `PASS — 1 passed in 1.83s` |
| Documentation/upstreams/repository audit / 文档/上游/仓库审计 | `PASS — 112 Markdown files; 2 locked clean checkouts; tracked 300; untracked 0; tracked runtime/upstream 0 / 112 份 Markdown；2 个锁定且干净的 checkout；跟踪 300；未跟踪 0；跟踪 runtime/upstream 0` |
| Local/tracking/GitHub reconciliation / 本地/tracking/GitHub 核对 | `PASS — 46905a50bbba19b7c4b74a0f7a274d5efdb013d6` |

## Implemented evidence / 已实现证据

| Scope / 范围 | Result / 结果 |
| --- | --- |
| Candidate order and bound / 候选顺序与边界 | `PASS` — each DASH component uses validated `primary + 0..8 backups` in source order; primary success causes zero backup DNS/HTTP / 每个 DASH 组件按来源顺序使用已校验的“主地址 + 0..8 个备用地址”；主地址成功时备用地址 DNS/HTTP 为零 |
| Eligible failover / 可切换失败 | `PASS` — DNS, timeout, transport, interruption, HTTP and partial Range incompatibility advance candidates under one deadline / DNS、timeout、传输、中断、HTTP 与 partial Range 不兼容在同一截止时间下推进候选 |
| Fail-closed classes / 关闭失败类别 | `PASS` — forbidden/mixed network policy, redirect/header/encoding, chunk/size, filesystem, probe and mux failures do not touch later candidates / 禁用/混合网络策略、重定向/header/encoding、chunk/size、文件系统、探测与合并失败不会触碰后续候选 |
| Strict partial continuity / 严格 partial 连续性 | `PASS` — backup append requires exact offset, total length and validator; interruption resumes across candidates; mixed invalid candidates preserve bytes; full-pass `200`/bad-`206` rejection precedes bounded discard/restart / 备用追加要求 offset、总长度与 validator 完全一致；中断可跨候选续传；混合无效候选保留字节；完整轮次 `200`/错误 `206` 拒绝后才有界丢弃/restart |
| Exhaustion semantics / 穷尽语义 | `PASS` — all `401`/`403` returns `locator_refresh_auth_expired`; mixed exhaustion returns the last fixed error without URL/host disclosure / 全部 `401`/`403` 返回 `locator_refresh_auth_expired`；混合穷尽返回最后一个固定错误且不披露 URL/host |
| Independent components / 独立组件 | `PASS` — video primary `503` and audio primary `403` independently reach their backups, are probed, combined within the byte cap and muxed once / 视频主地址 `503` 与音频主地址 `403` 各自到达备用地址，完成探测、组合字节约束及一次合并 |
| Production-process composition / 生产进程组合 | `PASS` — backup H.264/AAC components traverse SQLite → mock public DNS/HTTP → production ffprobe → production ffmpeg → final ffprobe → SHA-256 archive → Emby/NFO/source; final MP4 has video+audio / 备用 H.264/AAC 组件贯穿完整链路；最终 MP4 同时含视频与音频流 |
| Ephemeral boundary / 瞬态边界 | `PASS` — signed primary/backup values, private fields and winning indices are absent from retained SQLite, Job, runtime, work, archive and export trees and from errors / 签名主/备用值、私有字段与胜出序号不存在于保留 SQLite、Job、runtime、work、归档、导出树及错误中 |
| Compatibility and recovery / 兼容与恢复 | `PASS` — no-backup, silent DASH, single-/multi-page progressive, failed mux, published-final recovery, cleanup and zero-work replay remain green / 无备用地址、无声 DASH、单 P/多分 P progressive、合并失败、已发布成品恢复、清理与零工作重放保持通过 |

## Test and quality gates / 测试与质量门禁

| Check / 检查 | Command / 命令 | Result / 结果 |
| --- | --- | --- |
| Focused implementation regression / 实现专项回归 | `uv run pytest tests/unit/test_media_locator.py tests/unit/test_mediacrawler_refresh.py tests/unit/test_media_mux.py tests/unit/test_media_dash_downloader.py tests/unit/test_media_downloader.py tests/unit/test_cli.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_asset_download_orchestration.py tests/integration/test_pipeline_runtime.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_bilibili_multipart_progressive_pipeline.py tests/integration/test_bilibili_dash_pipeline.py -q` | `PASS — 466 passed in 66.96s` |
| DASH candidate unit boundary / DASH 候选单元边界 | `uv run pytest -q tests/unit/test_media_dash_downloader.py` | `PASS — 17 passed in 1.43s` |
| Production backup ffmpeg/ffprobe composition / 生产备用路径 ffmpeg/ffprobe 组合 | `uv run pytest -q tests/integration/test_bilibili_dash_pipeline.py` | `PASS — 1 passed in 1.74s` on the documentation-closeout rerun (`1.78s` on the implementation run); final archive and Emby MP4 contain video+audio / 文档收尾复验 `1 passed in 1.74s`（实现运行 `1.78s`）；最终归档与 Emby MP4 同时含视频与音频 |
| Complete suite / 完整套件 | `uv run pytest -q` | `PASS — 1790 passed, 1 skipped in 331.33s`; skip is the Windows-inapplicable POSIX mode-bit boundary / 跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff and format / Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 286 files already formatted / 全部通过；286 个文件格式正确` |
| Strict mypy / 严格 mypy | `uv run mypy --strict src` | `PASS — no issues in 84 source files / 84 个源码文件无问题` |
| Compileall and build / 字节编译与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — wheel and source distribution built / wheel 与源码包构建成功` |
| Documentation and upstream locks / 文档与上游锁 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 116 Markdown files; 2 locked checkouts / 116 份 Markdown；2 个锁定 checkout` |
| Git/upstream/diff audit / Git/上游/diff 审计 | explicit status, tracked/runtime/upstream and diff checks / 显式状态、跟踪/runtime/upstream 与 diff 检查 | `PASS — tracked 304; untracked 0; tracked runtime/upstream 0; upstream diff 0; both upstream dirty counts 0 / 跟踪 304；未跟踪 0；跟踪 runtime/upstream 0；上游 diff 为 0；两个上游 dirty 数均为 0` |

No coverage run is claimed. / 不宣称运行过 coverage。

## Git reconciliation / Git 核对

Implementation `fe45abcb7262c3d70437aff82a05609e43902af4` is pushed and reconciled across local `main` and `origin/main`. The commit containing this record is the bilingual documentation closeout; its self-referential SHA is intentionally left to Git history. / 实现 `fe45abcb7262c3d70437aff82a05609e43902af4` 已推送并在本地 `main` 与 `origin/main` 间核对一致。包含本记录的提交即双语文档收尾；其自引用 SHA 有意只保留在 Git 历史中。

## Live qualification / 登录与现网验收

| Row / 验收行 | Result / 结果 |
| --- | --- |
| Real Bilibili QR/Cookie login / 真人 Bilibili QR/Cookie 登录 | `NOT_RUN` |
| Authenticated DASH detail/play API / 登录态 DASH 详情/播放 API | `NOT_RUN` |
| Real primary/backup bilivideo CDN behavior / 真实主/备用 bilivideo CDN 行为 | `NOT_RUN` |
| Real Emby/Jellyfin scan and playback / 真实 Emby/Jellyfin 扫描与播放 | `NOT_RUN` |

Offline evidence cannot imply these rows, progressive backup failover or complete Bilibili support. / 离线证据不能代表上述真人行、progressive 备用故障切换或完整 Bilibili 支持通过。
