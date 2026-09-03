[English](goal.md) | **中文**

# 执行 0047 目标

- 状态：等待操作者——这是原始合并计划的最终门，在真人行记录完成前保持开启
- 日期：2026-09-03
- 前置：执行 0046（安全审查与发布清单）；roadmap 阶段 5 已由执行 0042 收敛至此
- 范围：在 Linux 部署主机上对全部七个平台做操作者协助的真人验收——每平台 QR/Cookie 登录、一个创作者订阅、增量重跑、媒体下载与 Emby 重扫——仅使用用户授权账户

## 目标结果（由操作者记录）

1. 每平台（`xhs`、`dy`、`ks`、`bili`、`wb`、`tieba`、`zhihu`）在本目录留一份可复现 smoke-test 记录——使用的登录方式、遇到的挑战、扫描的创作者、条数、归档媒体字节、Emby 目录输出——缺少凭据时如实记 `BLOCKED_EXTERNAL`。
2. 平台能力矩阵（[`docs/platform-capabilities.zh.md`](../../platform-capabilities.zh.md)）从源码推断更新为真人事实。
3. 完成度归档（[`docs/archive/upstream-replication-review.zh.md`](../../archive/upstream-replication-review.zh.md)）的真人行从 `NOT_RUN` 翻转为已记录结果。
4. 部署主机上的离线完整套件数字记录一次，适用于全部平台记录。

## 验收边界

- 每行按实际运行记录；`NOT_RUN`/`BLOCKED_EXTERNAL` 绝不静默变成通过。任何模拟/夹具结果不得顶替真人行。
- 账户为操作者本人；抓取量保持有界（小 `max_items`、克制延迟），遵守 SAFE 需求。
- 不做本机部署验证：全部行在 Linux 主机执行。

## 明确延期

多账户矩阵、长时间浸泡测试、超出基础扫描/播放检查的媒体服务器调优。
