[English](verification.md) | **中文**

# 执行 0003 验证

- 验证日期：2026-08-30
- 网络与账户策略：仅自动测试，不调用真人平台。

## 最终质量门禁

| 检查 | 命令 | 状态 |
| --- | --- | --- |
| 锁定依赖 | `uv sync --all-groups --locked` | 通过 |
| 代码规范 | `uv run ruff check .` | 通过 |
| 格式 | `uv run ruff format --check .` | 通过 |
| 严格类型 | `uv run mypy src/media_sync` | 通过 |
| 测试 | `uv run pytest` | 通过 |
| 覆盖率 | `uv run pytest --cov=media_sync --cov-report=term` | 通过 |
| 包构建 | `uv build` | 通过 |
| 随包迁移 | pytest 中执行该文件 | 通过源码与解包 wheel 升级 |
| SQLite 仓储 | pytest 中执行该文件 | 通过 12 个集成用例 |
| 同步持久化 | pytest 中执行该文件 | 通过双轮幂等与回滚 |
| CLI 工作流 | pytest 中执行该文件 | 通过完整流程 |
| CLI 发现 | `uv run media-sync --help` | 通过 |
| 数据库检查 | CLI 测试中的隔离状态检查 | 通过 |
| 环境诊断 | `uv run media-sync doctor --json` | 通过 |
| 文档 | `uv run python scripts/check_docs.py` | 通过 |
| 上游锁定 | `uv run python scripts/check_upstreams.py` | 通过 |
| 补丁空白 | `git diff --check` | 通过 |

## 行为证据

- SQLite 集成套件验证外键、唯一性、平台/内容/资产/任务词汇、迁移与 ORM 一致性、并发 upsert 身份一致、单调水位、运行状态 CAS、事件顺序、排他领取、租约过期和 fencing。
- 同步集成套件通过真实 SQLAlchemy 适配器执行两轮 Fake 同步，最终精确得到 1 位作者、4 条内容、4 个资产、2 次运行和 10 条有序事件；每轮发现/资产计数与应用结果一致。
- 在第二条内容写入时注入失败，证明外层事务中止会移除该失败尝试的全部作者/内容/资产/运行/事件写入。
- wheel 测试从解包后的构建产物而非源码树导入 `media_sync`，并把空 SQLite 数据库升级到 `0001_core`。
- CLI 测试验证手机号登录、非法枚举、疑似原始 Cookie 的凭据输入、订阅冲突和注入领域错误都会安全失败，且不会持久化或打印哨兵密钥。

## 线上资格验证

| 平台 | 登录 | 作者扫描 | 媒体 | 状态 |
| --- | --- | --- | --- | --- |
| `xhs` | 未运行 | 未运行 | 未运行 | `NOT_RUN` |
| `dy` | 未运行 | 未运行 | 未运行 | `NOT_RUN` |
| `ks` | 未运行 | 未运行 | 未运行 | `NOT_RUN` |
| `bili` | 未运行 | 未运行 | 未运行 | `NOT_RUN` |
| `wb` | 未运行 | 未运行 | 未运行 | `NOT_RUN` |
| `tieba` | 未运行 | 未运行 | 未运行 | `NOT_RUN` |
| `zhihu` | 未运行 | 未运行 | 未运行 | `NOT_RUN` |

未使用凭据、浏览器配置、平台端点或真实媒体；Fake/夹具自动化结果不会改变该矩阵。
