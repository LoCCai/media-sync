[English](goal.md) | **中文**

# 目标：SQLite 暂态凭据残留加固

## 结果

让 SQLite 连接策略本身保证：被迁移或擦除式 `UPDATE` 移除的含凭据取值，不会继续留在数据库文件的空闲页里。

## 为什么需要这个执行

0081 收尾门禁在 Windows 工作站上失败了一个长期存在的耐久性测试：`0003_media_download_emby` 把一条历史签名媒体 URL 改写成只能刷新定位器之后，`tests/integration/test_packaged_migrations.py` 写入的凭据哨兵仍能从数据库文件里读出。这个测试在 Linux 部署主机与较短路径上一直通过，而这正好掩盖了真实缺口：SQLite 只有在连接启用 `secure_delete` 时才会覆写被释放的 cell，而该开关属于连接，不属于文件。

表重建（`batch_alter_table`）会把行复制到新表再删除旧表。若删除发生在未启用 `secure_delete` 的连接上，旧页只是被挂进 freelist，于是数据库文件字节里仍留着原先的 `source_url`——一条产品明确承诺绝不保留的签名平台媒体 URL。任何将来"就地擦除"的迁移都面临同一个问题。

## 验收

- `media_sync.infrastructure.db` 创建的每一条连接都启用 `PRAGMA secure_delete=ON`，并由共享引擎上的测试断言。
- `0003` 升级测试证明凭据哨兵不出现在数据库文件字节中，包括此前能稳定复现泄漏的长临时路径。
- 磁盘格式、schema 修订号、事务策略与 `WAL` 行为均不改变；降级路径不受影响。
- "签名媒体 URL 从不落盘"的承诺在存储层成立，而不只是在行值上成立。
