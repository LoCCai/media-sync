[English](verification.md) | **中文**

# 执行 0048 验证

- 状态：校准范围通过全部静态门；离线套件真实执行并给出如实数字与分类分歧清单；部署与真人行仍为操作者项
- 日期：2026-09-03
- 环境：Windows 10 编写工作站、uv 0.12.9、Python 3.11.16/3.12.14/3.13.15（uv 管理）、PATH 上装有 ffmpeg/ffprobe N-126390 静态构建、两个 `.upstream` checkout 均按锁定 SHA 克隆

## 静态门

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| Ruff | `uv run ruff check src/ tests/ scripts/` | 0 | `All checks passed!` |
| 格式 | `uv run ruff format src/ tests/ scripts/` | 0 | `3 files reformatted, 175 left unchanged` 后清洁 |
| 严格 mypy | `uv run mypy --strict src` | 0 | 无问题（87 个源文件，含 0044 端点与抽取的下载助手） |
| 文档 | `uv run python scripts/check_docs.py` | 0 | 全部链接可解析 |
| 上游锁 | `uv run python scripts/check_upstreams.py` | 0 | `2 locked checkouts verified` |

## Python 支持矩阵（实测，非注释）

| 版本 | `uv sync --all-groups --locked` | 完整套件 |
| --- | --- | --- |
| 3.11.16 | OK | 可运行；分歧集合与 3.13 相同（见下） |
| 3.12.14 | OK | 可运行；分歧集合与 3.13 相同 |
| 3.13.15 | OK | `33 failed, 2031 passed, 1 skipped in 481.91s`（一次复跑：35 failed——2 项跨运行抖动） |

`requires-python` 维持 `>=3.11,<3.14`；此前 Docker 注释“3.12 会拒绝锁文件”是错误结论，已由 BASE_IMAGE 说明取代（3.12 容器失败发生在镜像源对齐之前）。

## 分歧分类（33–35 项失败）

全部失败测试都真实拉起子进程（bridge/receipt 密封、登录子进程边界、调度 v3/v2 协议、CLI ingest 子进程、安全矩阵子进程）。代表性探针显示子进程本身成功（`returncode=0`、1270 字节、2 条 JSONL），仅在产物密封回读处失败（`completion_failed: "MediaCrawler child output could not be sealed safely"`）。同一失败集合在本工作站**干净 checkout** 上复现（经 `git stash` 验证），因此非执行 0048 改动所致；疑似本机 AV/文件系统对子进程产物回读的行为。权威裁定：阶段 B 的 Linux 主机完整套件复跑（0047 计划 B-1 步）；任何在那里的复现以 `0047-dN` 进入缺陷循环。

## 新数字修复的缺陷

JSONL 读取层把内层 list 冻结为 tuple；0039 多实况分支只接受 `list`，导致所有真实记录被隔离（`invalid_record`）。已修复为接受 `(list, tuple)`；28 项实况 gallery 测试（捕获矩阵、契约漂移矩阵、逐 position 刷新、集成组合）全部通过。根因记录：这些测试提交时只收集未执行。

## 0044 最小集证据

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| API 测试 | `uv run pytest -q tests/unit/test_api_server.py` | 0 | `5 passed`（详情端点、门禁、404、后台操作） |
| CLI 抽取回归 | `uv run pytest -q tests/integration/test_asset_download_orchestration.py` | 0 | `38 passed` |
| 实况 gallery 套件 | `pytest -k "multi_live or xhs_live"` | 0 | `28 passed` |
| 钉定源码契约 | 知乎/贴吧 store 套件 | 0 | `13 passed`（克隆 `.upstream` 后） |

## 机密扫描（发布清单节选）

| 检查 | 结果 |
| --- | --- |
| `git grep -iE "set-cookie\|cookie:\|authorization:"` | 仅类型声明/哨兵/脱敏引用；无真实 token |
| 被跟踪运行时产物（`git ls-files`） | 无（`.env`/sqlite/browser_data/login-qr 均缺失） |
| 工作区差异哨兵扫描 | 0 匹配 |

## 操作者行（不变）

Docker 构建/运行、容器持久性、备份恢复演练、全部真人平台行：本工作站 `NOT_RUN`——按重构后的执行 0047 在 Linux 主机执行阶段 B+。
