# Execution 0017 plan / 执行 0017 计划

- Status / 状态：Executed and closed offline / 已执行并完成离线收口
- Plan date / 计划日期：2026-09-01
- Predecessor / 前置：Execution 0016 closeout commit `4774c34`
- Plan commit / 计划提交：`9d19e7e`
- Implementation commit / 实现提交：`2f8dbaa`
- Database migration / 数据库迁移：None / 无

## Baseline / 前置基线

Before source edits, the six-file gate passed `136 passed in 13.50s`: ingestion, refresh, database ingestion, download runtime, pipeline runtime and packaged migrations. The branch was clean at `4774c34`, with local `main`, `origin/main` and GitHub reconciled. / 源码修改前，导入、刷新、数据库导入、下载运行时、pipeline 运行时及打包 migration 六文件门禁通过 `136 passed in 13.50s`。分支在 `4774c34` 干净，本地 `main`、`origin/main` 与 GitHub 已核对一致。

## Executed delivery sequence / 已执行交付顺序

1. **Authority protocol / 权限协议 — complete / 已完成**：shared strict XHS note/creator validation, decoded value checks, XOR repr-safe inputs and child schema v3. / 共享严格小红书 note/creator 校验、解码值检查、互斥 repr-safe 输入及 child schema v3。
2. **Exact Subscription authority / 精确 Subscription 权限 — complete / 已完成**：explicit detail override first; otherwise resolve only exact provenance creator secret and project bounded `subscription.max_items`. / 显式 detail 覆盖优先；否则只解析精确来源 creator secret 并投影有界 `subscription.max_items`。
3. **Bounded creator lookup / 有界 creator 查找 — complete / 已完成**：clear all creator/detail lists, configure one XHS path, concurrency one, bounded notes and disabled comments/media. / 清空全部 creator/detail 列表，只配置一条小红书路径，单并发、有界 note，并关闭评论/媒体。
4. **Contracts and composition / 合约与组合 — complete / 已完成**：authority/frame/provenance/preflight tests plus ordinary static IMAGE/GALLERY archive/Emby composition and zero-work replay. / 权限/frame/来源/preflight 测试，以及普通静态 IMAGE/GALLERY 归档/Emby 组合与零工作重放。
5. **Independent review repairs / 独立审查修复 — complete / 已完成**：unique ordinary-static result gate, duplicate-target rejection, VERIFIED archive repair preflight, pipeline error taxonomy, durable raw shape preservation and non-XHS CLI rejection. / 唯一普通静态结果门、重复目标拒绝、VERIFIED 归档修复 preflight、pipeline 错误分类、持久 raw 形状保持及非小红书 CLI 拒绝。
6. **Verification and closeout / 验证与收尾**：all implementation gates and the post-edit 84-file documentation check pass; only the closeout commit/push remains for the main thread. / 全部实现门禁及编辑后 84 文件文档检查均通过；只剩主线程创建并推送收尾提交。

## Commit sequence / 提交序列

1. `9d19e7e` — `docs: 启动小红书作者权限闭环 / start XHS creator authority pipeline` — pushed / 已推送
2. `2f8dbaa` — `feat: 闭环小红书作者权限查找 / close XHS creator authority lookup` — pushed / 已推送
3. `docs: 收尾小红书作者权限闭环 / close XHS creator authority pipeline` — ready to commit/push; its SHA cannot be self-referenced / 已可提交/推送；其 SHA 不能自引用

`.upstream` remains excluded and both pinned checkouts remain clean. / `.upstream` 继续排除在跟踪外，两个锁定 checkout 均保持干净。
