[English](progress.md) | **中文**

# 推进结果

状态：计划已冻结，实现待开始。

- 在基线 `f41c6b3` 确认当前订阅 `run-now` 路由只改变调度状态，而全局 scheduler/pipeline worker 可能认领无关订阅。
- 确认既有下游 selector 覆盖作者全部有效资产快照，并在 worker 边界丢弃 pipeline 详细结果。
- 已审计七个平台历史路径：当前没有任何平台具备永久历史完成证据；只有 B 站具备可信单元续跑和末页观察，但仍受跨页列表漂移影响。
- 已复现 Windows exporter pin 缺陷：DesiredAccess 为零时，持有句柄仍可 rename 祖先目录；`FILE_LIST_DIRECTORY` 会阻止 rename，并在关闭后释放。
- 本计划检查点没有修改源码、数据库、部署、账户、supervisor 或生产媒体状态。

