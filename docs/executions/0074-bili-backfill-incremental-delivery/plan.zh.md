[English](plan.md) | **中文**

# 计划

状态：**已离线执行**，实现提交为 `9c81c4b`。实现与确定性本地验证已经完成；部署、平台请求及恢复 supervisor 仍不属于本次执行。

## 1. 重新确认并简化既有主链

- 从已认领 Account profile 开始，追踪当前 B 站投稿的 `BiliMultiFeedState`、`subscription_scan_progress`、scheduler 完成、`pipeline.subscription`、资产下载、归档与媒体库发布。
- 复用既有稳定 ID、锁、Job、Run、receipt、重试策略与输出设置。只有测试证明安全时才删除或调整重复状态，不建设并行 coordinator。
- 在执行验证中记录精确锁定 MediaCrawler SHA 及现有逐单元 HTTP/详情上限。

## 2. 增加耐久基线状态机

- 为初始回填、头部对账、增量轮询及阻塞/需重建状态定义封闭 phase。
- 状态绑定 Subscription、Account/auth revision、作者、B 站 `uploads` scope、策略 generation 及上游身份。
- 先确认现有 schema 无法表达这些不变量，再扩展 progress 表或增加最小迁移。升级/降级必须保护既有部署，绝不推测已有历史已经完成。
- 只保存有界计数、cursor/边界身份和时间；不保存原始响应、签名 locator 或 Cookie。

## 3. 把有界发现串到已验证交付

- 只有上一历史单元的发现与 pipeline receipt 耐久一致后，才继续至多一个精确历史单元。
- 遵守 `min(max_items, 30)`、既有请求上限、配置续跑间隔、订阅周期、暂停/移除及认证/退避状态。
- API 精确执行与常驻 supervisor 通过同一耐久所有权 fence 竞争；重复提交返回或复用权威单元，不建立另一条链。
- 不能因 crawler 进程或同步 Job 成功退出就声明批次已交付；必须要求精确内容、下载与发布证据。

## 4. 转入增量前完成对账

- 历史 lane 证明到达源末尾时保存边界，并安排一次有界头部对账。
- 如果头部身份或分页 generation 漂移，保留已交付数据，但使完成状态失效并重新执行有界对账。
- 只有稳定对账后才发布 `baseline_snapshot_complete`。之后定时周期使用有文档说明的重叠窗口和稳定 ID 去重检查头部。
- 身份、认证、scope、上游或策略变化时使基线失效；绝不静默转换不兼容 cursor。

## 5. 按完整 Content 单元发布

- 按 Content 分组选中 Asset，并保持必需组件完整性；同一多 P 视频/图集内部继续原子发布。
- 一个 Content 失败或不支持时，其他独立且完整的 Content 仍可完成并发布。
- 失败工作以精确安全计数与错误码保留重试。Operation 可显示 partial/失败并保留已验证 publication，但绝不能把缺媒体写成完成。
- 证明重启和零工作重放保持内容寻址字节及确定性 NFO 不变。

## 6. 提供小而直接的操作者界面

- 在订阅详情增加 phase、已完成/待处理批次证据、最近对账、下次可续跑时间与部分 Content 失败数。
- 复用任务页及轮转日志中心做精确下钻；不增加第二个 dashboard 或原始依赖日志流。
- 明确“基线完成”只是已对账时间点快照，不是永久全历史保证；Emby/Jellyfin 连接仍为可选。

## 7. 验证顺序

1. 单测状态校验、失效、节奏控制及封闭公开投影。
2. 集成测试 65+ 投稿跨三个以上批次、确定性重启屏障、源末尾/头部漂移及进入增量。
3. 使用受控 fixture 让“一条新投稿”和零工作重跑通过真实下载/归档/NFO 代码。
4. 验证一条坏旧 Content 与两条有效 Content 共存，以及多分段全有或全无。
5. 验证暂停、移除、认证过期/认领恢复、lease 丢失、API/supervisor 重复所有权和迁移往返。
6. 运行专项、Python/Web 完整套件、Ruff、strict mypy、Prettier/Svelte/build、文档/上游检查、制品构建及 `git diff --check`；把精确结果写入双语 progress/verification。
7. 只有发布且操作者同意后，才部署精确 revision，并以 UID `252671524` 执行有界 B 站金丝雀。记录镜像 SHA、Account/会话认领、内容/媒体计数、宿主最终目录/NFO 及之后一次增量周期；未观察项一律保持 `NOT_RUN`。

## 0074 之后

实现带 `expected_schedule_revision` CAS 的暂停态订阅策略编辑，使操作者无需删除历史即可安全调整周期、`max_items`、请求间隔、headless 模式与 B 站 scope。随后分别审计其他六个平台自己的有界分页、源末尾与增量证据，不能复制 B 站假设。
