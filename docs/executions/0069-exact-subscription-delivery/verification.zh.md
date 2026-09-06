[English](verification.md) | **中文**

# 验证过程

状态：实现门禁尚未执行。

## 计划证据

- 本检查点前 worktree 与 `origin/main`：`f41c6b3ea53a92903c4494daa78c95dc51e828ee`。
- 只读源码追踪确认 `POST .../run-now` 只调用 `DurableSchedulerService.run_now`，两个 bounded worker 都使用全局 `claim_next`。
- 纯内存 B 站模型复现：页边界删除一个元素后，巡检观察到末页，但漏掉一项仍可见内容；既有 coverage 校验仍然接受。这排除了永久 `history_complete` 声明。
- 真实 Windows 进程证据：exporter access `0` 时祖先目录仍可 rename；`FILE_LIST_DIRECTORY` 在句柄持有期间拒绝 rename，释放后允许。
- 既有输出专项检查基线为 `22 passed, 39 deselected`；仅内存替换目录 access 后，exporter/application/pipeline 集合为 `109 passed`。这些只是设计证据，不是对已编辑源码树的验证。

## 必须执行的实现门禁

- SQLite migration 升级/降级保留及拒绝用例；可用时验证 PostgreSQL constraint 路径。
- 精确 scheduler/pipeline 认领、并发、幂等、取消与恢复测试。
- 强类型 Operation payload/result/API/auth/log/诊断测试。
- 无媒体服务器的确定性端到端目录交付与零工作重放。
- B 站逐 feed 扫描进度同事务及漂移负向测试；六平台 unproven 投影测试。
- 真实 Windows rename pin 测试与非 Windows 兼容检查。
- 完整 Python 与 Web 质量、构建及契约套件。

真人扫码、作者、CDN、下载及媒体服务器验收：`NOT_RUN`。

