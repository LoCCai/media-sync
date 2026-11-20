[English](plan.md) | **中文**

# 计划：补齐 0088 遗留的操作者可见缺口

状态：**已执行。**

## 1. 续跑延迟：让对照变得完整

`/api/v1/settings` 与 `doctor --deep` 是操作者对照 supervisor 环境的两个界面。现在两者都报告全部七个延迟字段，前端 `Settings` 类型也声明了它们，使控制台无法悄悄丢掉其中一个。

钉住这一点的测试是枚举式的，不是抽样：它断言每个平台的延迟，而不是当初写断言时恰好存在的那两个。

## 2. 概览：保留数字，修正说法

KPI 卡片仍读同样的有界数组——新增服务端聚合端点会是新的 API 面，不在范围内——但标签现在写明每个数字来自哪个窗口（`最近 12 条任务中的…`、`最近 200 个资产中的…`）。账户与订阅的数组**确实是全量**，所以这两个写"全量"。这个差别正是重点：操作者必须能分辨四个数字里哪个回答的是"有多少"。

## 3. 任务表：说出结果是什么

单个 `operationResultLabel(operation)` helper 从已经白名单化的 `safeOperationResult` 投影推导出简短、封闭的标签。它从不读原始 `operation.result`，因此任务页保持其既有保证：未知远字段被丢弃。

## 4. 每处改动都用测试钉住

- API 断言枚举全部七个延迟。
- 三个新增前端用例覆盖标签 helper：资产下载的 verified/exported/空投影、导出的"再次导出 vs 新导出"、以及登录的 auth status。
- Web 测试计数必须正好增加这些用例；不增加断言改动就是未验证的改动。

## 5. 验证并记录

完整 Web 门禁集，加 Ruff、`ruff format --check`、strict mypy 与 `check_docs.py`。确切计数写入 [verification.zh.md](verification.zh.md)。
