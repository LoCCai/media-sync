[English](plan.md) | **中文**

# 计划：贴吧创作者主题耐久交付

状态：**已冻结；本轮即实现。**

## 1. 写代码前重新推导钉定事实

- 重读 `.upstream/MediaCrawler/media_platform/tieba/client.py:172-186`、`:684-710`、`:772-830` 与 `media_platform/tieba/help.py:240-250`，并在验证记录中引用确切行号。
- 记录必须保持不变的内容：其他五个有界契约（0074/0076/0080/0081/0084）、0020–0022 首楼图片 shim，以及本执行前的迁移头 `0018_weibo_creator_notes`。

## 2. 耐久游标与停止原因

- 迁移 `0019_tieba_creator_notes` 创建 `tieba_subscription_progress`，约束纪律与 0015–0018 相同：封闭 `phase` 白名单、四个固定停止原因（`has_more_false`、`empty_page_end`、`access_restricted`、`unit_cap_reached`）、计数范围、全有或全无证据三元组、`last_page_number` 范围、`blocked_code` 当且仅当 `blocked`，以及受护栏下线。
- `tb-work-v1:` 不透明游标携带：1 起页码、页见证、单元索引、已完成 thread id、上一页身份元组、头部边界与上一单元摘要。不携带其他内容——绝不携带主题载荷、标题或媒体 URL。

## 3. 有栅栏的有界续跑

- 每步至多一个按页界定的单元；上限就是 `max_items` 本身。
- 被截断的页绝不推进页码：重发同一请求，并按稳定 `thread_id` 跳过已交付主题。
- 续跑延迟经 `MEDIA_SYNC_TIEBA_SCAN_CONTINUATION_DELAY_SECONDS`（默认 300，两个服务必须一致）。

## 4. 对账与增量头部检查

- 保留的 `has_more_false` 结束后，从第 1 页做一次有界头部重列，必须复现记录的边界，才进入增量轮询。
- 由于页码总是递增，重复的页身份元组是唯一可用的停滞信号；此类单元累计到有界次数后以 `tieba_page_stalled` 阻塞。

## 5. 按 Content 交付

- 只有完整媒体形状在场的主题才发布；失败主题按固定码计数，绝不阻塞无关主题。
- 重启与零工作重放保留内容寻址字节与确定性 NFO 输出。

## 6. 操作者界面

- 订阅详情暴露阶段、页步数、最近页码与最近结束/对账证据。绝不暴露 portrait、创作者 URL、主题载荷或媒体 URL。

## 7. 验证序列

1. 单元：游标往返、四种停止原因、页尾回放、停滞阻塞、绑定变更拒绝。
2. 契约：页解析隐私、漂移拒绝、覆盖封印、受限 feed ≠ 源末。
3. 集成：跨重启页步、服务端结束、头部漂移与对账、进入增量、部分交付、零工作重放、单事务摄取、迁移往返。
4. 把所有头修订钉定测试推进到 `0019_tieba_creator_notes`。
5. 完整 Python 与 Web 套件、Ruff、strict mypy、docs/upstreams、`git diff --check`；记录精确双语结果。
6. Linux 构建、真人贴吧登录与真人金丝雀在操作者执行前保持 `NOT_RUN`。
