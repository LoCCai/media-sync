[English](verification.md) | **中文**

# 执行 0039 验证

- 状态：静态门在编写工作站通过；按操作者指示，完整套件执行移交 Linux 部署主机
- 日期：2026-09-03
- 前置：执行 0038 收尾 `064bdb1d4ab493ec2b31afb96a29032a8b939b2d`

## 前置环境

Windows 10 工作站、Git Bash、uv 0.12.9、Python 3.13.15。操作者已把产品验证迁移到 Linux Docker 主机；本记录区分“本机实际运行”与“必须在 Linux 运行”。

## 已实现证据

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 捕获矩阵 | `uv run pytest -q tests/unit/test_xhs_live_capture.py` | 0 | `9 passed in 3.63s` |
| 0038 实况回归（ingestion） | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py -k "xhs_live"` | 0 | `8 passed`（0039 前子集） |
| 0038 实况回归（refresh） | `uv run pytest -q tests/unit/test_mediacrawler_refresh.py -k "xhs_live"` | 0 | `3 passed` |
| 0038 实况回归（integration） | `uv run pytest -q tests/integration/test_xhs_playable_video_pipeline.py::test_xhs_live_photo_reaches_emby_with_zero_work_replay` | 0 | 启用 Windows 长路径（`LongPathsEnabled=1`）后 `1 passed`；否则暂存路径超过 260 字符 |
| 新测试收集 | `uv run pytest --collect-only -q tests/unit/test_api_server.py tests/unit/test_xhs_live_capture.py tests/unit/test_mediacrawler_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_xhs_playable_video_pipeline.py` | 0 | `385 tests collected in 2.22s` |
| 严格 mypy | `uv run mypy --strict src` | 0 | `no issues found in 87 source files` |
| Ruff 与格式 | `uv run ruff check src/ tests/ scripts/`; `uv run ruff format --check src/ tests/ scripts/` | 0 | `All checks passed!`；`178 files already formatted` |
| 字节编译 | `uv run python -m compileall -q src/media_sync` | 0 | OK |
| 文档链接 | `uv run python scripts/check_docs.py` | 0 | `342 Markdown files checked` |

## 移交 Linux 部署主机

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 新增多实况 contract/refresh/integration 测试 | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_xhs_playable_video_pipeline.py` | 本工作站 `NOT_RUN`；Linux 必须执行 |
| 完整套件 | `uv run pytest -q` | 本工作站 `NOT_RUN`；Linux 必须执行 |
| 构建与上游锁 | `uv build`; `uv run python scripts/check_upstreams.py` | 本机未克隆 `/.upstream/`，`NOT_RUN` |

真人验收行保持 `NOT_RUN`，属于部署执行（0041）而非本执行。
