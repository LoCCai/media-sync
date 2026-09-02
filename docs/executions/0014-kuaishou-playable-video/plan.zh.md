[English](plan.md) | **中文**

# 执行 0014 计划

- 状态：已在冻结的离线边界内执行完成
- 计划日期：2026-08-31
- 完成日期：2026-08-31
- 前置：Execution 0013 closeout commit `be979d6`
- 计划提交：`95c7082`
- 实现提交：`c4ab537`

## 交付顺序

1. **冻结范围与基线**
   - 在源码/测试编辑前记录四份双语执行文档、索引/路线图、精确排除项及真人 `NOT_RUN` 行。
   - 保持两个上游提交锁定及外部 runtime/许可证边界；不修改或内嵌 MediaCrawler checkout。
   - 运行既有导入/detail/refresh/runtime/下载器/网络/layout/应用 pipeline 测试作为前置基线。

2. **证明发现与锁定 detail 形状**
   - 增加使用已知与未知 query-key 哨兵的真实“归一化→SQLite”红测，再从持久快手播放/封面 raw 字段中结构化移除 query/fragment，同时为 Asset 发现与 detail refresh 保留完整瞬态 URL；强化精确 video/cover remote ID、position、MIME hint、source hint 及重放/generation 断言。
   - 增加快手 fake checkout，用纯视频 ID 运行实际 process runner，覆盖精确配置开关、签名 JSONL 输出、结果 framing 及正常成功清理。
   - 增加缺失/漂移/重复候选身份的固定负例，并验证 request/result 表示不会披露签名哨兵。

3. **组合平台 runtime 与可播放流水线**
   - 在真实 SQLite 中写入 Account/Author/Subscription，导入一个快手普通视频及可选封面，并断言精确 AssetRefreshSource 来源与稳定 adapter locator。
   - 通过惰性 MediaCrawler runtime 从精确 Subscription 解析视频与封面；使用确定性签名 URL、公网 DNS mock transport、受控 MP4 probe 与图片 magic 下载两项 Asset。
   - 断言无 Cookie/Authorization/调用方 header、既有重定向/续传与一次 401/403 行为、SHA-256 归档身份、持久 Asset/Job 状态、Emby 主 `.mp4`/海报/NFO/source 元数据及幂等重放。

4. **封闭数据落点与身份行为**
   - 扫描 ORM raw/source/locator 值、已 dispose SQLite/sidecar、正常成功 detail runtime、下载/导出工作根、归档、Emby library、对象表示及 Git 可见文件中的已知 key 与未知 key 动态签名哨兵。
   - 证明仅 query 轮换保留 generation 与已验证捷径；把同 ID/同 path 字节替换及清理失败留存记录为明确限制，不冒充通过。

5. **验证、记录并提交**
   - 运行执行专项、完整 pytest、Ruff lint/格式、mypy、文档/上游检查、构建、补丁检查及最终 retained/Git 扫描。
   - 用准确命令、结果、实现提交及剩余工作更新 goal/plan/progress/verification、平台真值、架构与 README；全部真人行保持 `NOT_RUN`。
   - 分别创建双语实现与文档收尾提交，推送 `main`，并核对本地/tracking/远端 SHA 一致。

## 风险与回退点

- 精确一个合法播放 URL 是已接受夹具形状；逗号扩展/多 URL、缺少播放 URL 及 locator-only 快手发现不属于本执行，不能静默提升。
- 快手使用 `MediaRequestProfile.DEFAULT`；没有锁定源码或真人证据时增加 header 可能破坏 CDN 行为，本切片禁止这样做。
- 成功 detail 清理会删除 UUID attempt 根；文件系统拒绝清理及持久账户阻断需要单独强化设计，固定失败不能描述为零留存。
- 若新测试暴露产品缺陷，只修复最小共享契约并重跑既有平台测试；若现有组合已经通过，仅测试的平台验收仍是有效交付，不得为制造改动而扩张无关功能。
