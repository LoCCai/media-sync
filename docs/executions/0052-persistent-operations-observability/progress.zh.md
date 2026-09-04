[English](progress.md) | **中文**

# 执行 0052 推进结果

- 状态：规划与基线已完成；尚未开始实现
- 日期：2026-09-04
- 基线：`d64b97b`

## 已完成

1. 已收尾并推送执行 0051；0052 启动前，本地 `HEAD`、`origin/main` 与 GitHub `refs/heads/main` 均为 `d64b97bcec96e182d64685bea951281559a96743`。
2. 重新阅读权威 status/roadmap 与持久队列、日志、可观测性后续设计，原始产品总目标不变。
3. 盘点五类当前进程内后台 Operation，确认历史、活动范围互斥与取消均不能跨越 API 进程或重启边界。
4. 审计既有 Job、SyncRun、LoginSession 与 RunEvent 持久化，使新的 Operation/Event 层补充而不是替代领域事实。
5. 选择 migration revision `0006_operations_observability`，并将控制面持久化与破坏性订阅删除、鉴权、分布式队列及自动恢复 callable 明确分界。
6. 保留唯一既存未跟踪路径 `.mimosa/`，两个锁定上游 checkout 均未触碰。

## 进行中

- Operation/Event schema、repository 状态机与安全 payload 契约。
- API 生命周期、取消/协调与 SSE 设计。
- 持久任务中心 Web 设计与测试矩阵。

## 尚未实现

- Migration `0006`、持久 repository/application service 与重启协调。
- 持久 API 接线、SSE、取消与支持包。
- 任务中心 UI、新聚焦/完整验证及最终文档收尾。

## 外部门仍开启

执行 0047 仍是 P0。Linux 持久性/备份/进程证据、Bilibili/XHS 金丝雀、其他真人平台及真实 Emby/Jellyfin 重扫/播放继续保持 `NOT_RUN`，0052 不会模拟这些证据。
