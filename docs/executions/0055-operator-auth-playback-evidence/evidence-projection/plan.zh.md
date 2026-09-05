[English](plan.md) | **中文**

# 播放证据投影计划

- 日期：2026-09-05
- 基线：`13de3b7`
- 状态：实现前冻结

1. 实现前单独提交本次双语 goal/plan/progress/verification 基线。
2. 增加只读仓储方法：精确 observation 查询最多一行；作者历史按确认时间及 ID 倒序，最多读 limit + 1 行。历史默认 20、最大 50，排除已独立验证的当前行。账本不执行 COUNT，最多物化 limit + 2 行。
3. 增加查询 service，使用最长 120 秒的单一绝对 deadline。依次 resolve A、读取不可变 profile A、一次完整 lookup、resolve B、读取 profile B，要求 target/profile 不变并重算 observation 身份一致。全部外部工作完成后才打开短读取事务。未知权威返回安全的未知历史状态，不能授予 PASS。
4. 冻结截断语义：远端遍历截断／不完整阻止 current 权威及 PASS。历史页截断单独报告，但不否定独立验证的精确当前行。这细化父级进展中的截断说明：旧的当前行不能仅因较新历史超过页上限就消失或产生假阴性。
5. 增加 `GET /api/v1/media-server/playback-evidence/by-author/{author_id}?limit=20`，沿用 Cookie/Bearer 读取鉴权。Service 工作前拒绝非规范 UUID、未知／重复 query 参数、非规范／越界 limit。只返回手工构造的安全投影；存储失败统一固定错误，远端失败返回当前不可用与未知历史。
6. 将 `/api/v1/qualifications` 升级至 v3，只允许一个可选规范 `author_id`。未指定作者时证据 scope 为 `not_requested`，不查询证据或远端；指定时只评估该作者，复用查询 service，并明确 playback PASS 的作者范围。无当前证据时 playback 为 IMPLEMENTED/NOT_RUN，provider completion 与自动扫描不变。保留既有自动化计数／操作字段。
7. 同步 Web 响应类型及当前状态／路线图／架构／API 文档。行为测试覆盖身份变化、失败／不完整 lookup、历史页外的旧 current、存储失败、读取边界、无写入、工作前鉴权、严格 query、安全响应及资格范围。执行必需的专项／完整 Python、串行 Web、质量、docs／上游与制品门，如实记录环境不可用项。
8. 记录结果、显式暂存、检查父级冻结文档差异与留存输出、中英双语提交并推送／核对 GitHub。下一检查点继续 Web 登录及确认。
