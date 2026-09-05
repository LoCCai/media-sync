[English](verification.md) | **中文**

# 投影验证记录

- 日期：2026-09-05
- 状态：本地回归、质量、文档与打包门通过

| 检查 | 证据 |
| --- | --- |
| 仓库 | `main` 干净且位于 `13de3b7`；`git fetch --prune origin` 与 `git pull --ff-only origin main` 成功，已是最新 |
| 父级需求 | 已检查冻结 0055 目标／计划；第 11–12 项在本增量实现，父级与子级冻结 goal/plan 保持不变 |
| 历史基线 | `13de3b7` 记录 Python 2941 项通过、22 项跳过、1 个 warning；这是历史证据，不是投影测试结果 |

## 已执行检查

| 检查 | 命令或证据 | 结果 |
| --- | --- | --- |
| 专项回归 | `uv run --frozen pytest -q tests/unit/test_playback_evidence_query.py tests/unit/test_api_playback_evidence_query.py tests/integration/test_playback_evidence_query.py tests/unit/test_qualifications.py tests/unit/test_api_media_server.py tests/unit/test_operator_auth_api.py tests/unit/test_playback_evidence_service.py tests/unit/test_api_playback_evidence.py tests/integration/test_playback_evidence_service.py tests/integration/test_playback_evidence_repository.py` | 220 项通过、1 个既有 warning、51.09 秒；此前较窄选择分别通过 91 与 117 项 |
| 完整 Python | `uv run --frozen pytest -q` | 2999 项通过、22 项跳过、1 个既有 warning、613.66 秒（`0:10:13`） |
| Web | `web/` 下依次运行 `pnpm test`、`pnpm format:check`、`pnpm check`、`pnpm build` | 7 文件／69 项；格式通过；0 error／0 warning；adapter-static 构建通过 |
| Python 质量 | `uv run --frozen ruff check .`；`uv run --frozen mypy src/media_sync`；`uv run --frozen ruff format --check .`；`uv run --frozen python -m compileall -q src tests` | 通过；strict mypy 检查 107 个源文件；format 检查 743 个文件 |
| 锁定参考 | `uv run --frozen python scripts/check_upstreams.py` | 两个锁定 checkout 均通过 |
| 数据库读取上限 | 62 行真实 SQLite 夹具与 SQL 捕获 | 独立找到最早当前行；两条有界 SELECT；无 COUNT、INSERT、UPDATE、DELETE 或 BEGIN IMMEDIATE；最多 limit + 2 行 |
| 安全与状态 | handler 工作前鉴权、严格 query、安全响应、权威／事务顺序、变化／失败／deadline 测试 | 通过；Cookie/Bearer 安全 GET 复用既有边界；不确定权威绝不授予 PASS |

首轮 Ruff 发现两处 import 排序与两处需改 raw string 的 regex，均在通过门前修正。pytest 唯一 warning 为既有 Starlette/httpx TestClient 弃用提示。最终专项／完整套件之后未修改源代码。

## 未执行与核查边界

22 项跳过包含 3 项 Windows/POSIX 差异、11 项 Operation PostgreSQL 与 8 项播放证据 PostgreSQL 竞态。可用性检查确认没有 Docker CLI，且未设置 `MEDIA_SYNC_TEST_POSTGRESQL_URL`；当前 Docker/Compose 与真实 PostgreSQL 保持 NOT_RUN。Web 测试只验证响应类型与既有代码，不代表登录前端或真实后端／浏览器组合可用。未运行任何获授权平台、CDN、媒体服务器或播放链路，仓库真人行继续为 NOT_RUN。

静态复核用户基于 `13de3b7` 的意见：当前布局无登录壳，客户端无 CSRF 注入，镜像使用 UID 1000，Compose 使用文件型 secret，入口先 `db init` 后 `serve`。root 所有的 0600 文件不可读属于有条件 Linux 部署风险，不是本轮复现的主机事故。已记录手工运行用户读取预检，但未在本机执行。未独立重查 GitHub Actions 历史；工作站结果不冒充 CI 证据。见[优先级补充计划](../delivery-priorities.zh.md)。

## 发布门

`scripts/check_docs.py` 对 508 份 Markdown 全部通过。系统临时目录全新 `uv build` 生成一个 wheel（125 项）与一个 sdist（824 项）；均包含 query service、repository 与 revision 0008，归档路径／内容检查未发现私有／运行时根目录、实际 .env、数据库／私钥文件或工作站路径。`git diff --check` 通过，八份父级／子级冻结 goal/plan diff 均为空。独立只读代码复核未发现本增量可触发的 P0/P1/P2，不代表尚缺的前端／部署工作已获资格。

包含本记录的实现提交是 Git 发布引用。只显式暂存源码／测试／文档／类型路径，排除凭据、运行时输出和 `.mimosa/`。下一检查点基线记录精确已发布提交及远端对账。本检查点不代表 0055 或产品总目标完成。
