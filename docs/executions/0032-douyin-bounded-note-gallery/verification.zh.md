[English](verification.md) | **中文**

# 执行 0032 验证

- 状态：冻结的离线有界抖音图集范围通过全部最终门禁；真人验收 `NOT_RUN`
- 日期：2026-09-02
- 前驱：执行 0031 收尾 `2e9e3b5378dd8966f56e068dced5f799e115f92b`
- 计划提交：`286dac9`

## 基线（任何 0032 变更之前）

| 检查 | 结果 |
| --- | --- |
| 0031 专项回归 | `PASS — 302 passed in 4.04s` |
| 0031 detail 契约 | `PASS — 100 passed in 70.92s` |
| 0031 完整套件 | `PASS — 1956 passed, 1 skipped in 408.57s` |
| Ruff、格式、strict mypy、docs、upstream | `PASS`（记录于 0031 验证文档） |

## 实现证据

| 范围 | 结果 |
| --- | --- |
| 严格图集解析器 | `PASS` — 逗号拼接 `note_download_url` 只接受字符串或 JSON 冻结序列输入，且每项恰为一个不含内嵌逗号的合法 URL；重复、非字符串、空项、无效 URL、错误类型与超过 64 张的图集以 `INVALID_RECORD` 隔离；空/缺失字段保持为空 |
| 物化 | `PASS` — 一张图产出 `ContentKind.IMAGE`，2–64 张产出带有序 `{aweme_id}:image:0..N-1` IMAGE 资产的 `ContentKind.GALLERY`；fixture 的 AUDIO/COVER 伴随资产位置保持 |
| 冻结兼容 | `PASS` — 空字段的视频/音频/文本回退、video/music/cover 宽容解析与锁定爬虫的图片优先选择保持字节级兼容；唯一语义变化是漂移图集从静默丢弃子项改为隔离（相应更新了一个既有集成 fixture） |
| 刷新 | `PASS` — 每个图集 position 经一次精确 numeric-ID detail 运动重新解析其当前签名 URL；第二张被替换的路径以 `locator_refresh_asset_mismatch` 关闭 |
| 下载与发布 | `PASS` — 两张图片均经 DEFAULT-profile 请求（无 Cookie/Authorization/Referer/Origin）下载、通过静态 PNG sniff 门、以不同 SHA-256 摘要归档，并发布 Emby poster/backdrop/两张 gallery 图/NFO，支持零工作重放 |
| 不泄密 | `PASS` — detail 签名、其哨兵与两个签名 URL 不出现在任何留存的 runtime/work/archive/export/library 树或 SQLite 产物中 |

## 测试与质量门

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 专项实现回归 | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_douyin_playable_pipeline.py` | `PASS — 316 passed in 5.09s` |
| 抖音 DB 摄取契约 | `uv run pytest -q tests/integration/test_mediacrawler_db_ingestion.py` | `PASS — 25 passed in 2.64s` |
| 图集收尾复跑 | `uv run pytest -q tests/integration/test_douyin_playable_pipeline.py::test_douyin_note_gallery_reaches_emby_without_persisting_signed_queries` | `PASS — 1 passed in 2.25s` |
| 完整套件 | `uv run pytest -q` | `PASS — 1971 passed, 1 skipped in 390.84s`；跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 459 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 84 source files` |
| Compileall 与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — 编译通过；构建 wheel 与源码分发包` |
| 文档与上游锁定 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 288 Markdown 文件；2 个锁定干净 checkout` |
| Git/上游审计 | 显式 status 与跟踪路径扫描 | `PASS — 仅预期变更；跟踪 runtime/upstream/dist 0；两个上游 dirty 计数 0` |

## 不宣称

不宣称运行过覆盖率。未执行任何真实账户、登录、作者流、抖音 API、CDN 字节或 Emby/Jellyfin 服务器交互；全部真人行保持 `NOT_RUN`。
