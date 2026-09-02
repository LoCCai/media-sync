[English](verification.md) | **中文**

# 执行 0036 验证

- 状态：冻结的离线微博视频封面范围通过全部最终门禁；真人验收 `NOT_RUN`
- 日期：2026-09-03
- 前驱：执行 0035 收尾 `5a27e99949c54a5032454d91b8809d28afad7086`
- 计划提交：`1ad49a7`

## 基线（任何 0036 变更之前）

| 检查 | 结果 |
| --- | --- |
| 0035 专项回归 | `PASS — 451 passed in 74.84s` |
| 0035 完整套件 | `PASS — 2010 passed, 1 skipped in 360.55s` |
| Ruff、格式、strict mypy、docs、upstream | `PASS`（记录于 0035 验证文档） |

## 实现证据

| 范围 | 结果 |
| --- | --- |
| 封闭封面校验器 | `PASS` — HTTPS `sinaimg.cn` 族 host 加静态扩展与有界路径接受；外域、GIF/MP4 扩展、fragment、userinfo 与端口拒绝 |
| Store 边界捕获 | `PASS` — 封面只与可捕获视频（标量或 `playback_list`）一同捕获；缺失、畸形、外域或非静态封面仅捕获视频 |
| 归一化分支 | `PASS` — `{note_id}:cover:0` COVER 资产在 VIDEO 旁物化；畸形封面 payload 隔离；封面字段递归移除 |
| 刷新 | `PASS` — WB COVER 加入支持集合，封面像视频一样经一次精确 numeric-note detail 子进程重新解析 |
| 下载与发布 | `PASS` — 封面通过静态 PNG 门、以自己的 SHA-256 摘要归档并发布为 Emby 剧 poster，视频保持主媒体，零工作重放 |
| 不泄密 | `PASS` — 封面字段与其签名 URL 不出现在任何留存的 runtime/work/archive/export/library 树或 SQLite 产物中 |

## 测试与质量门

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 专项实现回归 | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_weibo_playable_video_pipeline.py tests/integration/test_weibo_image_pipeline.py` | `PASS — 341 passed in 4.29s` |
| 微博管线套件 | `uv run pytest -q tests/integration/test_weibo_playable_video_pipeline.py` | `PASS — 6 passed in 4.01s` |
| 封面收尾复跑 | `uv run pytest -q tests/integration/test_weibo_playable_video_pipeline.py::test_weibo_video_with_poster_reaches_emby_with_zero_work_replay` | `PASS — 1 passed in 2.20s` |
| 完整套件 | `uv run pytest -q` | `PASS — 2016 passed, 1 skipped in 370.47s`；跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 490 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 85 source files` |
| Compileall 与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — 编译通过；构建 wheel 与源码分发包` |
| 文档与上游锁定 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 320 Markdown 文件；2 个锁定干净 checkout` |
| Git/上游审计 | 显式 status 与跟踪路径扫描 | `PASS — 仅预期变更；跟踪 runtime/upstream/dist 0；两个上游 dirty 计数 0` |

## 不宣称

不宣称运行过覆盖率。未执行任何真实账户、登录、作者流、微博 API、CDN 字节或 Emby/Jellyfin 服务器交互；全部真人行保持 `NOT_RUN`。冻结的 `pic_info.pic_big.url` 形状是文档化的 store 输入契约而非实活验证。
