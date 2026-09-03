[English](goal.md) | **中文**

# 执行 0045 目标

- 状态：文档范围已完成
- 日期：2026-09-03
- 前置：执行 0042（完成度归档）
- 范围：已部署 media-sync 实例（执行 0041 的 Docker compose 布局）的备份、恢复与升级运维文档

## 目标结果

1. `docs/operations.md`（+ `.zh.md`）：存在哪些状态及其位置（SQLite 数据库、归档、Emby 媒体库、jobs/runtime）、在线与离线备份流程、恢复流程，以及升级流程（pull → build → up，schema 迁移在容器启动时幂等执行）。
2. 验收：文档命令与实际配置面一致（卷布局、`media-sync db init`、entrypoint 行为）；干净 clone 主机可照做无需临场发挥。

## 验收边界

- 仅文档；代码与 schema 零变化。
- 恢复/升级演练在部署主机执行（操作者）；此处如实记录为 `NOT_RUN`——不做本机部署验证。

## 明确延期

自动定时备份、异地复制、时间点恢复（PITR）。
