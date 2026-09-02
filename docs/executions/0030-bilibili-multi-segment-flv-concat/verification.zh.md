[English](verification.md) | **中文**

# 执行 0030 验证

- 状态：冻结的离线多段 FLV 拼接范围通过全部最终门禁；真人验收 `NOT_RUN`
- 日期：2026-09-02
- 前驱：执行 0029 收尾 `dbd06075eac67377a911b503de9aa609fdc30c79`
- 计划提交：`e7395fb`

## 基线（任何 0030 变更之前）

| 检查 | 结果 |
| --- | --- |
| 0029 专项回归 | `PASS — 447 passed in 70.97s` |
| 0029 完整套件 | `PASS — 1902 passed, 1 skipped in 409.85s` |
| Bilibili 组合 | `PASS — 5 passed in 10.93s` |
| Ruff、格式、strict mypy、docs、upstream | `PASS`（记录于 0029 验证文档） |

## 实现证据

| 范围 | 结果 |
| --- | --- |
| 协议 v9 多段 FLV 分类 | `PASS` — 有界 2–64 `durl` 元组且顶层格式分类为 FLV 时产出一个类型化 FLV 分段目标；精确一段 FLV、多段普通与 DASH payload 保持字节级兼容；空、超限、跨段重复主地址与畸形元组保持固定结局 |
| 类型化瞬态目标 | `PASS` — `ResolvedFlvSegmentsLocator` 精确包装一个 `ResolvedSegmentsLocator`；resolver 联合类型、导出与惰性刷新校验接受它；repr 不含签名 URL；持久 locator v1 不变 |
| 私有桥接标记 | `PASS` — segments payload 只接受精确键集加精确 `"format": "flv"` 标记；非精确标记、平面字段碰撞与无页面 payload 以 `locator_refresh_schema_changed` 关闭；标记与 segments 字段不出现在任何留存 runtime 树中 |
| 逐段下载与探测 | `PASS` — 共享字节上限/截止时间下逐段主→备故障切换；每个完成分段必须精确探测为 `video/x-flv`；FLV 授权下的 MP4 探测或普通授权下的 FLV 探测以 `media_type_mismatch` 关闭且不发布 |
| 鉴权刷新 | `PASS` — 一次全鉴权分段轮次只刷新整目标一次；刷新后的普通/FLV 类型漂移或分段数漂移返回 `locator_refresh_schema_changed`；第二次全鉴权返回 `locator_refresh_auth_expired` |
| 拼接与成品门 | `PASS` — 一次固定 argv 的 concat-demuxer `ffmpeg -c copy` 调用只消费受控 parts 目录内的相对文件名脚本；仅精确探测为 `video/mp4` 的成品可发布；失败保留可续传分段、移除未备成品且脚本不存活 |
| 恢复与清理 | `PASS` — 已备成品无 DNS/HTTP 即可恢复；`cleanup_partial` 丢弃全部分段 store 与脚本；不归档、导出或发布任何原始 `.flv` |
| 生产多段 FLV 组合 | `PASS` — 两个本地生成的 H.264+AAC FLV 贯穿 SQLite → 主地址 `503` → 备用 → 第二段 → 逐段生产 ffprobe → 生产 ffmpeg 拼接 → 成品 ffprobe → 不可变 SHA-256 `.mp4` → Emby `.mp4`/NFO/source，含视频与音频流 |
| 零工作重放与兼容 | `PASS` — 重放零新增 detail/DNS/HTTP/probe/ffmpeg/archive/export 工作；单段 FLV 转封装、多段普通、DASH、多分 P 与静态形状保持绿色 |

## 测试与质量门

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 专项实现回归 | `uv run pytest -q tests/unit/test_media_locator.py tests/unit/test_media_probe.py tests/unit/test_media_mux.py tests/unit/test_media_downloader.py tests/unit/test_media_dash_downloader.py tests/unit/test_media_flv_downloader.py tests/unit/test_media_segments_downloader.py tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py` | `PASS — 460 passed in 91.95s` |
| Bilibili 组合 | `uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_bilibili_multipart_progressive_pipeline.py tests/integration/test_bilibili_dash_pipeline.py` | `PASS — 6 passed in 11.71s` |
| 多段 FLV 收尾复跑 | `uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py::test_bilibili_multi_segment_flv_backup_reaches_emby_through_production_concat_with_zero_work_replay` | `PASS — 1 passed in 2.88s` |
| 完整套件 | `uv run pytest -q` | `PASS — 1916 passed, 1 skipped in 446.64s`；跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 440 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 84 source files` |
| Compileall 与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — 编译通过；构建 wheel 与源码分发包` |
| 文档与上游锁定 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 272 Markdown 文件；2 个锁定干净 checkout` |
| Git/上游审计 | 显式 status 与跟踪路径扫描 | `PASS — 仅预期变更；跟踪 runtime/upstream/dist 0；两个上游 dirty 计数 0` |

## 不宣称

不宣称运行过覆盖率。未执行任何真实账户、登录、作者、detail、播放 URL、CDN 或 Emby/Jellyfin 服务器交互；全部真人行保持 `NOT_RUN`。转码与编解码修复按契约保持不支持，而非静默降级。
