[English](verification.md) | **中文**

# 执行 0033 验证

- 状态：冻结的离线知乎回答有界图集范围通过全部最终门禁；真人验收 `NOT_RUN`
- 日期：2026-09-03
- 前驱：执行 0032 收尾 `41508b1cc57672aa9e18252498d10d98bc371b90`
- 计划提交：`92651bc`

## 基线（任何 0033 变更之前）

| 检查 | 结果 |
| --- | --- |
| 0032 专项回归 | `PASS — 316 passed in 5.09s` |
| 0032 DB 摄取契约 | `PASS — 25 passed in 2.64s` |
| 0032 完整套件 | `PASS — 1971 passed, 1 skipped in 390.84s` |
| Ruff、格式、strict mypy、docs、upstream | `PASS`（记录于 0032 验证文档） |

## 实现证据

| 范围 | 结果 |
| --- | --- |
| 有界捕获 | `PASS` — 2–64 张有序图片捕获为完整元组（逐图属性优先级选择、两两互异）；恰一张图保持 v1 字段；65 张、无效、重复或禁用媒体的回答不捕获 |
| 归一化 v2 分支 | `PASS` — ARTICLE 与有序 `{content_id}:image:0..N-1` IMAGE 资产；双字段、标量、单项、超界、非字符串、无效与重复 payload 以 `INVALID_RECORD` 隔离；v2 字段从持久 raw envelope 递归移除 |
| 兄弟绑定刷新 | `PASS` — `zhihu_image_source_hints` 上下文元组从完整 SQLite 兄弟组装；每个 position 经一次精确 canonical-answer detail 子进程重新解析当前签名 URL；替换或超界漂移以 `locator_refresh_schema_changed` 关闭；v1 单图路径保持等价 |
| 下载与发布 | `PASS` — 两个 position 经 DEFAULT profile 下载、通过静态 PNG sniff 门、以不同 SHA-256 摘要归档，并发布 Emby poster/backdrop/两张 gallery 图/body/NFO，零工作重放 |
| 不泄密 | `PASS` — 刷新签名与两个签名 URL 不出现在任何留存的 runtime/work/archive/export/library 树或 SQLite 产物中 |

## 测试与质量门

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 专项实现回归 | `uv run pytest -q tests/unit/test_zhihu_media.py tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_zhihu_answer_image_pipeline.py tests/integration/test_zhihu_scheduled_creator_bound.py` | `PASS — 538 passed in 71.18s` |
| 图集收尾复跑 | `uv run pytest -q tests/integration/test_zhihu_answer_image_pipeline.py::test_zhihu_answer_gallery_reaches_emby_with_sibling_bound_refresh` | `PASS — 1 passed in 2.05s` |
| 完整套件 | `uv run pytest -q` | `PASS — 1984 passed, 1 skipped in 336.62s`；跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 463 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 84 source files` |
| Compileall 与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — 编译通过；构建 wheel 与源码分发包` |
| 文档与上游锁定 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 296 Markdown 文件；2 个锁定干净 checkout` |
| Git/上游审计 | 显式 status 与跟踪路径扫描 | `PASS — 仅预期变更；跟踪 runtime/upstream/dist 0；两个上游 dirty 计数 0` |

## 不宣称

不宣称运行过覆盖率。未执行任何真实账户、登录、作者流、知乎 API、CDN 字节或 Emby/Jellyfin 服务器交互；全部真人行保持 `NOT_RUN`。
