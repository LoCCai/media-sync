[English](progress.md) | **中文**

# 推进结果

状态：已实现并完成离线验证，实施提交 `b22e938` 已发布到 `origin/main`；本收尾记录随后的文档提交发布。

- 新增 `POST /api/v1/subscriptions/{id}/execute`。它创建或重放一个耐久 `subscription-delivery` Operation，只物化和认领指定订阅，驱动其精确 scheduler/pipeline Job，并返回封闭的本地目录交付结果；连接 Emby/Jellyfin 服务器仍是可选项。
- 新增封闭 pipeline receipt v2。回执与 pipeline 成功状态在同一事务提交，同时兼容历史 v1 行。API 应答丢失、supervisor 抢占、worker 重试、Operation 过期或进程重启时，从精确 Job/Run/receipt 耐久链恢复，不创建第二条链。
- 封住独立审查发现的发布与恢复竞态。全局到期调度跳过存在活动精确交付 Operation 的订阅；精确物化和 pipeline 入队采用一致的 writer/行锁顺序，并拒绝活动前驱/后继工作；`retry_wait` 继续绑定同一个精确 Job 直到终态。观察 supervisor 持有的 `claimed` 或 `running` 工作时，API 现在持续重试同一个精确认领：未过期租约保持不变，过期租约才被回收，且不创建第二条链。只要 sync 或 pipeline Job 仍活动，就不释放 Operation 独占键。
- 创建工作前检查 MediaCrawler 启用及许可证确认。交付 Operation 不虚假声明不支持的取消能力，而以固定 `subscription_delivery_cancel_unsupported` 冲突返回。
- 新增 B 站 uploads/dynamics 耐久扫描观察。各 feed 的源末尾证据会保留，但它和 item limit 都不会升级为永久历史完成；其余六平台历史仍明确为未证明。
- 通过请求 `FILE_LIST_DIRECTORY` 修复 Windows exporter 目录 pin，在验证和写入导出目标时阻止祖先目录被重命名。
- 新增迁移 `0013_exact_subscription_delivery`。SQLite 降级要求唯一显式 exclusive-maintenance 连接，并拒绝仍保留交付/扫描历史的数据库；PostgreSQL 在审计前锁定两张历史表；未知方言关闭失败。双语降级手册要求同时停止 API 与 supervisor。
- 本轮没有部署、执行生产订阅、恢复 supervisor、发起真人平台请求、下载或媒体服务器操作。
