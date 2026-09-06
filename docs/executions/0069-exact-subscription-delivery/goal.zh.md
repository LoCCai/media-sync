[English](goal.md) | **中文**

# 目标：精确订阅交付

把操作者对一个选中订阅的操作变成一条持久且可观察的真实链路：只发现该订阅、只认领其精确 scheduler Job、继续执行该 Job 的精确 Run 所派生的 pipeline Job、验证全部必需归档结果，并在无需连接 Emby/Jellyfin 服务器的情况下写出兼容本地媒体库目录。

本执行同时记录诚实的逐内容流历史扫描事实，并修复已复现的 Windows 目录 pin 弱点。它不把一次批次成功改名为历史完成，不会静默处理另一个订阅，也不声称四个平台的真人扫码失败已经修复。

## 验收标准

1. 新增持久 `subscription-delivery` Operation，以一个订阅为 target，由 `POST /api/v1/subscriptions/{id}/execute` 启动。请求身份采用封闭脱敏契约，subjects 持久关联精确 scheduler Job、SyncRun 与 pipeline Job。
2. scheduler 可以物化并认领一个精确订阅周期，同时保留 enabled/deleted 状态、schedule revision、全局容量、账户/平台 lane 限流、lease、重试及既有 ownership reconciliation；不能退而领取队列里的其他订阅。
3. pipeline 只能认领从该精确成功 scheduler Job 和 Run 派生的 coordinator；既有全局 scheduler/pipeline 命令保持兼容。
4. Operation 返回有界、强类型回执，计数明确表达：发现行、资产身份、作者当前有效资产快照、此次完成或复用的已验证归档、发布 disposition、受管文件数及已验证本地目录结果。Worker 完成不能冒充交付成功。
5. 并发重复请求按每订阅 exclusive key 幂等返回或冲突。与 supervisor 竞争不能创建第二条链，也不能让请求处理无关任务。取消只能在下一阶段前生效，或等待已经进入的 fencing 工作真实收尾后再声明。
6. 订阅 UI 区分“提前下次调度”和“执行采集→归档→目录”，跟踪返回的精确 Operation，显示阶段并链接其精确 Jobs/日志。确认文案说明当前 pipeline 覆盖作者有效资产快照，且不会调用媒体服务器 API。
7. migration `0013` 扩展 Operation kind 约束，并新增逐订阅、逐内容流扫描进度事实。既有数据默认 `unproven`；不得根据 `last_success_at`、空 cursor 或历史 Run 回填完成。
8. B 站投稿与动态只有在已校验 coverage 与成功 Run/checkpoint 同事务提交时，才能持久化 `scanning` 或 `source_end_observed`。后者只表示“本次可见巡检观察到末页”，仍需漂移复扫，绝不对外表示永久 `history_complete`。另外六个平台在具备真实续跑证据前保持 `unproven`。
9. Windows exporter 以 `FILE_LIST_DIRECTORY` 打开受保护目录链，并保留既有不共享 delete 的策略。真实 Windows 回归证明 pin 持有期间祖先目录不能 rename，释放后可以；Linux 行为不变。
10. 专项 repository、migration、operation、API、Web 与真实文件系统测试通过。确定性离线端到端用例证明精确订阅→发现→归档验证→兼容文件，包含零工作重放且无需配置媒体服务器。除非取得新的授权证据，真人平台/CDN/服务器行继续标为 `NOT_RUN`。

## 延后但不改变的产品要求

- 按完整内容单位发布，避免一个无关的历史失败资产阻塞完整新作品。
- 为小红书、抖音、快手、微博、贴吧、知乎实现可信、有界且可中断续跑的历史回填。
- 在设置永久历史完成前，为 B 站实现更强的稳定覆盖或漂移对账协议。
- 部署执行 0068 后，使用新日志对一个失败扫码平台做受控诊断；不会自动恢复此前已停止的 supervisor。

