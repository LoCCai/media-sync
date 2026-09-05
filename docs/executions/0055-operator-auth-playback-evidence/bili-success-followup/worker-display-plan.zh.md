[English](worker-display-plan.md) | **中文**

# 补充计划：区分 Worker 完成与采集结果

- 日期：2026-09-05
- 状态：本补充实施前冻结
- 上级：[原计划](plan.zh.md)，已提交 b018979

获授权的生产测试运行约 236 秒：Job 为 failed_terminal，没有内容入库，但 scheduler-run Operation 为 succeeded，其摘要是 processed_count=1、status_counts.failed_terminal=1。订阅现已暂停；supervisor 由用户停止。未启动重试、下载或导出。这一观察要求小范围修正控制台，而非改变持久 Operation 语义。

仅对 scheduler-run，把成功的 Operation 呈现为“Worker 已完成”，并从已有有界 status_counts 单独推导固定业务结果提示。失败、等待、空结果或未知结果均不能暗示采集成功。只接受已知摘要键、已知状态和总数一致的非负安全整数计数；异常摘要使用固定不可用文案，不回显其值。操作表、详情与相关完成 toast 共用逻辑。不改 API、数据库、重放、取消和其他操作类型。

覆盖单项终止失败、可重试/混合/等待、成功、idle/空结果及畸形摘要，并保证既有登录诊断不变。重新串行运行 Web 门禁并更新上级推进/验证记录。真实采集失败诊断仍独立等待安全错误码；粘贴 Cookie 实施与七平台目标继续保留。
