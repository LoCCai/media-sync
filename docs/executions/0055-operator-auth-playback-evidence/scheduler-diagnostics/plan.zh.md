[English](plan.md) | **中文**

# 冻结调度诊断计划

1. 先提交双语记录再实施。保留历史测试 schema_invalid，不回填猜测原因，不完成残留 running Run，不启动 supervisor 或重试。
2. 仅增加三个固定终止/影响熔断的分类：scheduler_heartbeat_failed、scheduler_heartbeat_storage_busy、scheduler_finalize_failed；保留原 schema_invalid 的失败语义，不改重试策略、busy timeout、租约、熔断记账或事务。
3. 只分类捕获到的心跳普通异常。SQLite busy/locked 必须是 SQLAlchemy OperationalError，orig 为 sqlite3.Error，原生 sqlite_errorcode 是严格整数且基础码为 SQLITE_BUSY/SQLITE_LOCKED；不看异常文字、SQL、路径或任意异常属性。其余为通用 heartbeat_failed。租约丢失、取消保持原控制路径；发布结果前取消并等待 handler 清理。
4. 仅把 run_once 内实际 _finalize 调用与 context/invoke/result 校验分开，普通收尾异常标记 finalize_failed。既有 fail-closed 恢复接受该固定码，保留成功 Run 权威检查及全部租约/清理隔离。持久库不可用时仍可能只留下 fenced Job 而未保存诊断，不能伪造失败 Run 或使用含秘密的兜底。
5. API/CLI 共用的 Job 投影增加可选 last_error_code，CLI worker 输出增加 error_code；只允许 classify_failure 精确识别的码及失败/等待/重试/fenced 状态。缺失、未知或与成功状态矛盾时为 null，不映射未知原文。不输出 SQL/异常/请求正文/lease，不新增查询、不改 batch Operation schema 或数据库。旧客户端可忽略新增字段，新 Web 兼容旧 API 缺字段。
6. Web 在 Job 列表/详情使用固定白名单和中文解释，新字段不走原始字段迭代。说明失败阶段和检查方向；schema_invalid 仍是历史模糊原因，SQLite busy 不代表库损坏，均不能证明 Cookie 无效。保留既有 Worker/业务结果分离及其他流程。
7. 测试：精确失败组合、真实类型/伪造 busy 异常、第二连接持写锁的文件 SQLite 实际争用（仅测试缩短 busy timeout），收尾前释放锁并证明 handler 取消/等待且无假成功。覆盖已提交成功 Run、暂时/持续收尾失败、租约/取消/清理优先级、未知/秘密哨兵投影、新旧 API UI 形状及重试语义不变。
8. 运行专项及更广调度/API/CLI/Python 回归、串行 Web、静态/文档/上游门禁，独立复核、双语提交/推送核验。真人采集保持 FAILED，新诊断在生产仍 NOT_RUN，待用户部署及另行授权测试。后续：有界 B 站作者采集、粘贴 Cookie 校验/保存/复用，再继续其他平台/归档/播放验收。

