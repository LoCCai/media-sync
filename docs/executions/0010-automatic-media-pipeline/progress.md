# Execution 0010 progress / 执行 0010 推进结果

- Status / 状态：In progress — planning baseline / 推进中——计划基线
- Started / 开始时间：2026-08-31 00:43 +08:00
- Implementation / 实现：`NOT_RUN`
- Verification / 验证：`NOT_RUN`

## Planning evidence / 计划证据

- Read-only review confirmed the existing `jobs` table already has job type, natural key, Subscription/Account/platform/Run scope, payload, attempts and lease fields. The `(job_type, natural_key)` uniqueness is sufficient for one coordinator per successful sync Job. / 只读复核确认既有 `jobs` 表已具备 job type、natural key、Subscription/Account/platform/Run 范围、payload、attempt 与租约字段；唯一约束足以保证每个成功 sync Job 只有一个协调器。
- Existing `AssetDownloadService` already recovers generation-bound partial/archive state, and `EmbyExportService` already recovers publication intent/result. The coordinator can re-enumerate rather than persist a large asset list. / 既有下载服务已恢复 generation-bound partial/archive，Emby 服务已恢复发布 intent/result；协调器可重新枚举，无需持久化大体量 Asset 列表。
- Correct scope is exact Subscription author plus current provenance, not a global Asset scan and not only `last_run_id == triggering_run`. / 正确范围是精确 Subscription 作者加当前来源，而不是全局 Asset 扫描，也不是只看触发 run 的 `last_run_id`。
- No code, migration, worker, CLI or runtime operation has run for execution 0010 yet. / 执行 0010 尚未运行代码、migration、worker、CLI 或运行时操作。

## Next / 下一步

Implement the idempotent coordinator Job and atomic enqueue tests first, then the application selector/worker. / 先实现幂等协调 Job 与原子 enqueue 测试，再实现应用 selector/worker。
