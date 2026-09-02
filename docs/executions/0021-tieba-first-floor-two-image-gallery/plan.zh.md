[English](plan.md) | **中文**

# 执行 0021 计划

- 状态：冻结离线范围已执行
- 计划日期：2026-09-02
- 前置：`e5d871050cdf25da1a51e2f057ba317dea2cffb1`
- 计划提交：`5095ed6e803a8a2f0a3134e756dd3e101fef10bd`
- 实现提交：`e0fb8d572c8f5535a5495c2dfbf5b9cdf78461e7`
- 数据库迁移：计划无

## 前置基线

Execution 0020 已在 `e5d8710` 推送并核对。其实现专项回归通过 `368 passed in 41.18s`；完整套件通过 `1650 passed, 1 skipped in 310.82s`；Ruff、格式、严格 mypy、compileall、构建、文档、两个上游锁与保留 marker 审计均通过。此前有界只读审计已观察到真实双图首楼，且未保留正文或 query 值。

## 交付顺序

1. 增加独立版本化的精确双图私有捕获，同时保留 v1 单图字段与安装 marker；冻结有序、互异 source-hint 语义与冲突拒绝。
2. 扩展源码/单元/进程合约，覆盖精确双图捕获、gather-child → parent-store 携带、并发、递归字段移除及单图兼容。
3. 归一化 ARTICLE 加两项有序 IMAGE Asset；只在完整有序 gallery 匹配时，把惰性/detail 刷新扩展到 position 0 与 1；拒绝双重私有声明、重复、重排、替换及形状漂移。
4. 增加确定性双图 SQLite → detail → mock DNS/HTTP → 静态门 → SHA-256 归档 → Emby 组合及 query 零工作重放，并执行整树瞬态 marker 审计。
5. 运行专项与完整测试，以及 Ruff、格式、严格 mypy、compileall、构建、文档、上游、diff 与保留产物审计；更新真值文档，创建双语实现/收尾提交，推送并核对 GitHub。

## 提交序列

1. `5095ed6` — `docs: 启动贴吧首楼双图闭环 / start Tieba first-floor two-image pipeline`
2. `e0fb8d5` — `feat: 闭环贴吧首楼双图 / close Tieba first-floor two-image pipeline`
3. 本文档收尾提交；有意不嵌入自身 SHA — `docs: 收尾贴吧首楼双图闭环 / close Tieba first-floor two-image pipeline`

`.upstream` 继续排除在跟踪外、保持未修改且干净。
