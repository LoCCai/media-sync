[English](plan.md) | **中文**

# 计划：SQLite 暂态凭据残留加固

状态：**已冻结**。本计划不授权任何部署、平台请求或驻留进程重启。

## 1. 先复现，再改任何东西

- 单独复现失败断言：`0003` 改写历史签名 URL 后，哨兵必须从文件字节中消失。
- 确认机制而非症状：用带 `secure_delete=ON` 连接的监听器重跑同一次升级。若哨兵消失，则成因是空闲页保留，而不是擦除逻辑缺陷。
- 记录两种结果，包括对临时路径长度的依赖，使执行日志写清实际观察到的事实。

## 2. 改连接策略，不改迁移

- 在 `src/media_sync/infrastructure/db/database.py` 的 SQLite 连接配置里，于既有 `foreign_keys`、`journal_mode`、`busy_timeout` 之侧加入 `PRAGMA secure_delete=ON`，并写明"凭据保留"这条理由。
- pragma 取值保持字面量，与既有 `busy_timeout` 纪律一致；以命名常量导出，使测试断言同一段文本。
- 不触碰 `0003`、其他任何迁移、schema 修订号或降级护栏。迁移必须继续对早期版本创建的数据库有效。

## 3. 测试策略与结果

1. 在 `tests/integration/test_database.py` 既有 pragma 断言旁，断言共享引擎的 `PRAGMA secure_delete` 等于 `1`。
2. 保留 `0003` 端到端断言作为结果测试；验证它在默认短临时路径与此前能复现泄漏的长临时路径上都通过。
3. 确认该 pragma 不影响 WAL、嵌套 savepoint 或 `BEGIN IMMEDIATE` 写者协调：跑 database、scheduler 与 pipeline 的集成切片。

## 4. 门禁

- 全仓 Ruff lint 与 format、strict mypy、`compileall`。
- 仓库根运行完整 Python 套件。
- Web `check`、`test`、`format:check`（源码未受影响，仍必须通过）。
- `scripts/check_docs.py`、`scripts/check_upstreams.py`、`git diff --check`。
- 以双语记录精确命令、计数与两种复现结果。

## 5. 不在范围内

- 升级时执行 vacuum、对既有生产文件做追溯擦除，或声明历史部署已擦掉其空闲页。操作者若想清除既有残留，需在本执行之后对在线数据库运行 `VACUUM`；这一点只做记录，不在本执行中自动化。
