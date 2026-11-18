[English](progress.md) | **中文**

# 进展：SQLite 暂态凭据残留加固

状态：本地已实现并验证。未做任何部署，未使用任何平台账户。

## 结果

`media_sync.infrastructure.db` 拥有的每条 SQLite 连接现在都启用 `PRAGMA secure_delete=ON`。行被删除或更新时会覆写已释放的 cell，因此 `0003` 的表重建不再可能把历史签名媒体 URL 留在数据库文件里可读的位置。

## 观察到的事实

1. 本工作站上的 0081 收尾门禁以 `2 failed, 7196 passed, 63 skipped` 结束。其中一个失败是 `test_0003_upgrade_preserves_only_complete_verified_legacy_asset`：凭据哨兵 `migration-path-credential-sentinel-0003` 仍存在于字节偏移 132972，落在第 32 页——正是重建前 `assets` 行所在的那一页。
2. 失败依赖路径长度。同一测试在把 `--basetemp` 指向短目录时通过，在默认长临时路径上失败，这正是 Linux 门禁与更早的本地运行从未暴露它的原因。
3. 一次复现把升级前的文件复制出来，用带 `secure_delete=ON` 连接监听器的同一次 Alembic 升级执行，文件字节里不再有哨兵；不带该 pragma 的同一升级则留有哨兵。这把成因定位到空闲页保留，而不是 `0003` 中的擦除逻辑。升级后执行 `VACUUM` 同样能清除哨兵，进一步确认残留位于空闲页。

## 改动内容

- `src/media_sync/infrastructure/db/database.py`：新增 `SQLITE_SECURE_DELETE_PRAGMA` 常量，并在 `_configure_sqlite_connection` 中于 `foreign_keys`、`journal_mode`、`busy_timeout` 之侧应用，注释写明凭据理由。该常量已加入 `__all__`。
- `tests/integration/test_database.py`：pragma 测试现在同时断言 `PRAGMA secure_delete` 为 `1`，使将来的连接策略改动无法悄悄丢掉这条保证。
- `tests/integration/test_kuaishou_creator_work_delivery.py` 与 `tests/integration/test_kuaishou_creator_work_migration.py`：对两个 0081 提交时为未格式化状态的测试文件应用了格式化器，使全仓 format 门禁干净。

没有改动任何迁移、schema 修订号、事务策略、WAL 设置或降级护栏。

## 未完成

- 未对既有部署做追溯擦除。操作者若要清除既有空闲页，需对在线数据库运行 `VACUUM`；该步骤在计划中作为显式操作者步骤记录，不在本执行中自动化。
- 部署、Linux 主机门禁与全部真人平台行仍为 `NOT_RUN`。
