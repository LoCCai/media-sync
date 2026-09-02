[English](verification.md) | **中文**

# 执行 0031 验证

- 状态：冻结的离线普通原创可播放视频范围通过全部最终门禁；真人验收 `NOT_RUN`
- 日期：2026-09-02
- 前驱：执行 0030 收尾 `e242b16097b2fb1f0f6ee1dc8e863ace1c68ab32`
- 计划提交：`1c79c6d`

## 基线（任何 0031 变更之前）

| 检查 | 结果 |
| --- | --- |
| 0030 专项回归 | `PASS — 460 passed in 91.95s` |
| 0030 完整套件 | `PASS — 1916 passed, 1 skipped in 446.64s` |
| Ruff、格式、strict mypy、docs、upstream | `PASS`（记录于 0030 验证文档） |

## 实现证据

| 范围 | 结果 |
| --- | --- |
| 封闭 URL 校验器 | `PASS` — HTTPS `sinaimg.cn`/`*.sinaimg.cn`/`f.video.weibocdn.com` host 加非根大小写不敏感 `.mp4` 路径接受签名 query；http、外域、非 mp4 扩展名、fragment、userinfo、显式端口、空路径段、点开头文件名与超长名称全部拒绝 |
| Shim 捕获矩阵 | `PASS` — 真实子进程的锁定 store 边界只为 `page_type == "video"` 原创帖捕获精确一个合法 `stream_url`；转发、`article`/`None` page 类型、外域或非 mp4 URL 不捕获且不产出私有字段 |
| 归一化分支 | `PASS` — `ContentKind.VIDEO` 与一个 position-0 `{note_id}:video:0` VIDEO 资产加 `video/mp4` mime；双私有字段、残留 `page_info`、转发、非规范身份与畸形 payload 隔离关闭失败；私有字段从持久 raw envelope 递归移除 |
| 刷新 | `PASS` — WB VIDEO 加入支持集合；一次精确 numeric-note detail 子进程在内存中重新捕获当前签名 URL，刷新器返回 DEFAULT-profile 瞬态 locator，提示或身份漂移以 `locator_refresh_asset_mismatch` 关闭 |
| 下载与发布 | `PASS` — DEFAULT-profile 请求不带 Cookie/Authorization/Referer/Origin；MP4 探测、SHA-256 归档、Emby `.mp4`/NFO/source 发布与零工作重放全部成立 |
| 不泄密 | `PASS` — 签名 URL、其 query 哨兵与私有字段不出现在任何留存的 runtime/work/archive/export/library 树或 SQLite 产物中 |
| 兼容 | `PASS` — 0016 图片语义、无媒体帖的 TEXT 回退与此前全部平台切片保持绿色 |

## 测试与质量门

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 专项实现回归 | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_weibo_image_pipeline.py tests/integration/test_weibo_playable_video_pipeline.py` | `PASS — 302 passed in 4.04s` |
| Detail 刷新契约套件 | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py` | `PASS — 100 passed in 70.92s` |
| 可播放视频收尾复跑 | `uv run pytest -q tests/integration/test_weibo_playable_video_pipeline.py::test_weibo_playable_video_reaches_emby_without_persisting_signed_queries` | `PASS — 1 passed in 1.82s` |
| 完整套件 | `uv run pytest -q` | `PASS — 1956 passed, 1 skipped in 408.57s`；跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 449 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 84 source files` |
| Compileall 与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — 编译通过；构建 wheel 与源码分发包` |
| 文档与上游锁定 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 280 Markdown 文件；2 个锁定干净 checkout` |
| Git/上游审计 | 显式 status 与跟踪路径扫描 | `PASS — 仅预期变更加一个新集成测试文件；跟踪 runtime/upstream/dist 0；两个上游 dirty 计数 0` |

## 不宣称

不宣称运行过覆盖率。未执行任何真实账户、登录、作者流、微博 API、CDN 字节或 Emby/Jellyfin 服务器交互；全部真人行保持 `NOT_RUN`。冻结的 `stream_url` 形状是文档化的 m.weibo.cn 契约而非实活验证；`playback_list` payload 保持不支持而非静默降级。
