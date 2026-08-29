# Execution 0002 plan / 执行 0002 计划

1. Trace MediaCrawler CLI enums and configuration mutation. / 跟踪 MediaCrawler CLI 枚举与配置变更。
2. Inspect all platform login and creator workflows. / 检查所有平台的登录与创作者流程。
3. Inspect JSONL writers, media download switches and output paths. / 检查 JSONL 写入、媒体下载开关和输出路径。
4. Trace bili-sync-up database, scheduler, download-state and NFO generation patterns. / 跟踪 bili-sync-up 数据库、调度、下载状态和 NFO 生成模式。
5. Produce requirements, capability matrix and component architecture. / 形成需求、能力矩阵和组件架构。
6. Validate citations and create the second bilingual commit. / 验证引用并创建第二个双语提交。

## Risks and assumptions / 风险与假设

- Upstream behavior changes frequently; every assertion is scoped to the locked SHA. / 上游变化频繁；全部结论只适用于锁定 SHA。
- A method name or CLI enum is not proof that the workflow works; placeholder bodies are marked unsupported. / 方法名或 CLI 枚举不能证明流程可用；占位实现按不支持记录。
- No live platform account is used during source analysis. / 源码分析阶段不使用真人平台账户。
