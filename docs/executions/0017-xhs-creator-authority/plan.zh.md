[English](plan.md) | **中文**

# 执行 0017 计划

- 状态：已执行并完成离线收口
- 计划日期：2026-09-01
- 前置：Execution 0016 closeout commit `4774c34`
- 计划提交：`9d19e7e`
- 实现提交：`2f8dbaa`
- 数据库迁移：无

## 前置基线

源码修改前，导入、刷新、数据库导入、下载运行时、pipeline 运行时及打包 migration 六文件门禁通过 `136 passed in 13.50s`。分支在 `4774c34` 干净，本地 `main`、`origin/main` 与 GitHub 已核对一致。

## 已执行交付顺序

1. **权限协议 — complete / 已完成** 共享严格小红书 note/creator 校验、解码值检查、互斥 repr-safe 输入及 child schema v3。
2. **精确 Subscription 权限 — complete / 已完成** 显式 detail 覆盖优先；否则只解析精确来源 creator secret 并投影有界 `subscription.max_items`。
3. **有界 creator 查找 — complete / 已完成** 清空全部 creator/detail 列表，只配置一条小红书路径，单并发、有界 note，并关闭评论/媒体。
4. **合约与组合 — complete / 已完成** 权限/frame/来源/preflight 测试，以及普通静态 IMAGE/GALLERY 归档/Emby 组合与零工作重放。
5. **独立审查修复 — complete / 已完成** 唯一普通静态结果门、重复目标拒绝、VERIFIED 归档修复 preflight、pipeline 错误分类、持久 raw 形状保持及非小红书 CLI 拒绝。
6. **验证与收尾** 全部实现门禁及编辑后 84 文件文档检查均通过；只剩主线程创建并推送收尾提交。

## 提交序列

1. 已推送
2. 已推送
3. 已可提交/推送；其 SHA 不能自引用

`.upstream` 继续排除在跟踪外，两个锁定 checkout 均保持干净。
