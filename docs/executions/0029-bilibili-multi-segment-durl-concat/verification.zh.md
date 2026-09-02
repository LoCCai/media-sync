[English](verification.md) | **中文**

# 执行 0029 验证

- 状态：冻结的离线多段普通 `durl` 范围通过全部最终门禁；真人验收 `NOT_RUN`
- 日期：2026-09-02
- 前驱：执行 0028 收尾 `2621f6a119aac60eaf89f0195d4fbe23bd5160f0`
- 计划提交：`9a40968`

## 基线（任何 0029 变更之前）

| 检查 | 结果 |
| --- | --- |
| 0028 遗留的 Python 文档复检 | `PASS — uv run python scripts/check_docs.py; Documentation links OK (256 Markdown files checked)` |
| 上游锁定 | `PASS — uv run python scripts/check_upstreams.py; Upstreams OK (2 locked checkouts verified)` |
| Ruff 与格式 | `PASS — all checks; 427 files already formatted` |
| Bilibili 组合基线 | `PASS — 4 passed in 6.95s` |

## 实现证据

| 范围 | 结果 |
| --- | --- |
| 协议 v8 有界多段解析 | `PASS` — 2–64 个有序 `durl` 条目各自产生一个主地址加至多八个备用地址；DASH 保持优先；精确一段行为字节级兼容；空、超限、跨段重复主地址与畸形元组以固定结局关闭；顶层 FLV 且分段数大于一保持不支持 |
| 类型化瞬态目标 | `PASS` — `ResolvedSegmentsLocator` 强制 2–64 边界、Bilibili profile 与主地址两两互异；repr 不含签名 URL；resolver 联合类型、导出与惰性刷新校验接受它，持久 locator v1 不变 |
| 私有桥接 | `PASS` — `{"cid", "segments"}` 为单页与多分 P 元组携带逐段主/备用地址，与全部既有私有字段递归防碰撞，持久化前移除，且仅当 payload CID 与所选分 P 匹配时重建；无页面、碰撞与畸形 payload 以 `locator_refresh_schema_changed` 关闭 |
| 逐段下载 | `PASS` — 每段按序主地址→备用地址候选故障切换，全部分段共享一个字节上限与截止时间；每个完成分段必须精确探测为 `video/mp4`；混合/非 MP4 或超预算分段不发布即关闭 |
| 鉴权刷新 | `PASS` — 一次全鉴权分段轮次只刷新整目标一次；刷新后分段数或类型漂移返回 `locator_refresh_schema_changed`；第二次全鉴权返回 `locator_refresh_auth_expired` |
| 拼接与成品门 | `PASS` — 一次固定 argv 的 concat-demuxer `ffmpeg -c copy` 调用只消费受控 parts 目录内的相对文件名脚本；身份/大小/超时/有界输出检查关闭失败；仅精确探测为 `video/mp4` 的成品可发布；脚本不跨越尝试存活 |
| 恢复与清理 | `PASS` — 拼接/成品门失败保留可续传分段 store 并移除未备成品；已备成品无 DNS/HTTP 即可恢复；`cleanup_partial` 丢弃全部分段 store 与脚本 |
| 生产多段组合 | `PASS` — 两个本地生成的 H.264+AAC MP4 贯穿 SQLite → 主地址 `503` → 备用 → 第二段 → 逐段生产 ffprobe → 生产 ffmpeg 拼接 → 成品 ffprobe → 不可变 SHA-256 `.mp4` → Emby `.mp4`/NFO/source；两个分段 URL 与私有字段不出现在任何留存的 runtime/work/archive/export/library/SQLite 证据中 |
| 零工作重放与兼容 | `PASS` — 重放零新增 detail/DNS/HTTP/probe/ffmpeg/archive/export 工作；无格式/MP4 progressive、FLV 转封装、DASH、多分 P 与静态形状保持绿色 |

## 测试与质量门

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 专项实现回归 | `uv run pytest -q tests/unit/test_media_locator.py tests/unit/test_media_probe.py tests/unit/test_media_mux.py tests/unit/test_media_downloader.py tests/unit/test_media_dash_downloader.py tests/unit/test_media_flv_downloader.py tests/unit/test_media_segments_downloader.py tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_detail_refresh.py` | `PASS — 447 passed in 70.97s` |
| Bilibili 组合 | `uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_bilibili_multipart_progressive_pipeline.py tests/integration/test_bilibili_dash_pipeline.py` | `PASS — 5 passed in 10.93s` |
| 多段收尾复跑 | `uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py::test_bilibili_multi_segment_backup_reaches_emby_through_production_concat_with_zero_work_replay` | `PASS — 1 passed in 2.26s` |
| 完整套件 | `uv run pytest -q` | `PASS — 1902 passed, 1 skipped in 409.85s`；跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 432 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 84 source files` |
| Compileall 与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — 编译通过；构建 wheel 与源码分发包` |
| 文档与上游锁定 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 260 Markdown 文件；2 个锁定干净 checkout` |
| Git/上游审计 | 显式 status 与跟踪路径扫描 | `PASS — 仅预期变更加一个新测试文件；跟踪 runtime/upstream/dist 0；两个上游 dirty 计数 0` |

## 工作站门禁基础设施说明

本工作站前两次完整套件分别在 `test_mediacrawler_supervision.py`/`test_mediacrawler_login.py` 中失败 10 项、6 项既有契约测试。把全部 0029 变更 stash 后，在干净前驱 `9a40968` 上复现完全相同的失败，证明其早于本执行。根因：两个文件的 `_pid_is_alive` 辅助用 `text=True` 解码 `tasklist.exe` 输出，而本中文 Windows 主机的本地化 GBK 字节破坏 UTF-8 reader 线程（`UnicodeDecodeError`、`completed.stdout is None`）。这两个仅测试侧的辅助现在传入 `encoding="utf-8", errors="replace"` —— PID 的 CSV 行是 ASCII，存活判定语义不变 —— 两文件单独通过（`14 passed, 1 skipped`；`43 passed`）后，上方最终完整套件门全绿。为此没有改动任何生产代码。

## 不宣称

不宣称运行过覆盖率。未执行任何真实账户、登录、作者、detail、播放 URL、CDN 或 Emby/Jellyfin 服务器交互；全部真人行保持 `NOT_RUN`。多段 FLV 拼接按契约保持不支持，而非静默降级。
