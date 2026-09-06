[English](downgrade-guardrails.md) | **中文**

# Migration 0013 降级护栏

降级 `0013_exact_subscription_delivery` 是破坏性的数据库结构维护，不是在线回滚。它会删除 `subscription_scan_progress` 表，并收窄 Operation kind 的允许范围。

## 必须执行的维护流程

开始降级前：

1. 停止所有 media-sync API 进程。
2. 停止所有 scheduler、worker 和 supervisor 进程，并确认 supervisor 在维护期间不会将它们重新拉起。
3. 确认没有其他进程或操作者能够写入数据库。
4. 备份数据库及其关联的媒体/状态元数据，并验证备份可以恢复。

降级完成或失败后，必须先检查数据库 revision 与完整性，之后才能重新启动 API 或 supervisor。

## SQLite

此 migration 替换约束时会跨越 autocommit 边界，因此 SQLite 无法在全过程中持有一个数据库锁。降级默认关闭，只有操作者显式作出以下维护证明时才会继续：

```bash
alembic -x exclusive-maintenance=true downgrade 0012_library_output_policy
```

`exclusive-maintenance=true` 是操作者证明，不是锁。它不会停止 API、supervisor、scheduler、worker 或任何其他写入方。缺失、值为 false 或重复的维护参数都会被拒绝。

## PostgreSQL

读取任一历史表之前，降级会在 `operations` 与 `subscription_scan_progress` 上取得 `ACCESS EXCLUSIVE` 锁。如果存在活动事务，等待锁可能阻塞。锁超时或取消不代表数据库已经可以安全降级；应停止写入方、排查竞争会话，然后从头重试完整维护流程。

## 默认拒绝条件

存在以下任一情况时，降级都会被拒绝：

- `operations` 中存在任何 kind 为 `subscription-delivery` 的记录；
- `subscription_scan_progress` 中存在任何记录，无论其 state 是什么。

离线 SQL 降级不受支持，因为历史审计必须针对在线数据库执行。此降级也不支持其他数据库方言。

切勿在没有经过批准的保留与恢复方案时，仅为强制降级而删除历史。之后重新升级只会重建数据库结构，无法恢复已删除的 Operation 或扫描进度历史。完成降级版本的全部验证前，请保留备份。
