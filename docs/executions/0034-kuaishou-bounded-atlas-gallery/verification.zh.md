[English](verification.md) | **中文**

# 执行 0034 验证

- 状态：冻结的离线快手图集范围通过全部最终门禁；真人验收 `NOT_RUN`
- 日期：2026-09-03
- 前驱：执行 0033 收尾 `e9d1fcdb8970b5a10f84e3947e1570159c9f9011`
- 计划提交：`eeff45e`

## 基线（任何 0034 变更之前）

| 检查 | 结果 |
| --- | --- |
| 0033 专项回归 | `PASS — 538 passed in 71.18s` |
| 0033 完整套件 | `PASS — 1984 passed, 1 skipped in 336.62s` |
| Ruff、格式、strict mypy、docs、upstream | `PASS`（记录于 0033 验证文档） |

## 实现证据

| 范围 | 结果 |
| --- | --- |
| 封闭 URL 校验器 | `PASS` — HTTPS DNS-host 加静态扩展名的 URL 接受签名 query；http、非静态扩展、fragment、userinfo、显式端口、空路径与超长值全部拒绝 |
| Store 边界捕获 | `PASS` — 真实子进程的锁定 `update_kuaishou_video` shim 只捕获冻结的 `photo.ext_params.atlas.pics[].cdn` 形状（1–64 个两两互异候选）；insecure、重复或超界图集不捕获且不产出私有字段 |
| 归一化分支 | `PASS` — 一个私有字符串列表字段物化 `ContentKind.IMAGE`（一张）或 `ContentKind.GALLERY`（2–64）及有序 `{video_id}:image:0..N-1` IMAGE 资产加可选 COVER 伴随；畸形 payload 隔离且字段递归移除 |
| 刷新 | `PASS` — KS IMAGE 加入支持集合；每个图集 position 经一次精确 numeric-ID detail 子进程重新解析当前签名 URL，路径漂移以 `locator_refresh_asset_mismatch` 关闭；普通视频 photo 字节级兼容 |
| 下载与发布 | `PASS` — 两个 position 经 DEFAULT profile（无 Cookie/Authorization/Referer/Origin）下载、通过静态 PNG/JPEG 门、以不同 SHA-256 摘要归档并发布 Emby 双图 gallery，零工作重放 |
| 不泄密 | `PASS` — 图集签名与两个签名 URL 不出现在任何留存的 runtime/work/archive/export/library 树或 SQLite 产物中 |

## 测试与质量门

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 专项实现回归 | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_kuaishou_playable_pipeline.py tests/unit/test_mediacrawler_refresh.py` | `PASS — 445 passed in 73.39s`（checkout fixture 修复后；441 项通过加恢复的四个 KS 契约合例） |
| Detail 刷新契约套件 | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py` | `PASS — 106 passed in 69.98s` |
| 图集收尾复跑 | `uv run pytest -q tests/integration/test_kuaishou_playable_pipeline.py::test_kuaishou_atlas_gallery_reaches_emby_without_persisting_signed_queries` | `PASS — 1 passed in 2.10s` |
| 完整套件 | `uv run pytest -q` | `PASS — 2002 passed, 1 skipped in 352.79s`；跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 474 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 85 source files` |
| Compileall 与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — 编译通过；构建 wheel 与源码分发包` |
| 文档与上游锁定 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 304 Markdown 文件；2 个锁定干净 checkout` |
| Git/上游审计 | 显式 status 与跟踪路径扫描 | `PASS — 仅预期变更加一个新模块与一个新测试文件；跟踪 runtime/upstream/dist 0；两个上游 dirty 计数 0` |

## 不宣称

不宣称运行过覆盖率。未执行任何真实账户、登录、作者流、快手 API、CDN 字节或 Emby/Jellyfin 服务器交互；全部真人行保持 `NOT_RUN`。冻结的 `atlas.pics[].cdn` 形状是文档化的 store 输入契约而非实活验证。
