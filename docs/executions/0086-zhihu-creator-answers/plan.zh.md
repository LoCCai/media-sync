[English](plan.md) | **中文**

# 计划：知乎创作者回答耐久交付

状态：**已冻结；本轮即实现。**

## 1. 写代码前重新推导钉定事实

- 重读 `.upstream/MediaCrawler/media_platform/zhihu/client.py:399-419`、`:462-490`、`media_platform/zhihu/core.py:256-300` 与 `media_platform/zhihu/help.py:354-366`，并在验证记录中引用确切行号。
- 记录必须保持不变的内容：其他六个有界契约（0074/0076/0080/0081/0084/0085）、0033 图库 shim，以及本执行前的迁移头 `0019_tieba_creator_notes`。

## 2. 耐久游标与停止原因

- 迁移 `0020_zhihu_creator_answers` 创建 `zhihu_subscription_progress`，纪律与 0015–0019 相同：封闭 `phase` 白名单、四个固定停止原因（`is_end`、`empty_page_end`、`access_restricted`、`unit_cap_reached`）、计数范围、全有或全无证据三元组、`last_offset` 范围、`blocked_code` 当且仅当 `blocked`，以及受护栏下线。
- `zh-work-v1:` 不透明游标携带：整数 `offset`、页见证（offset、limit、`is_end`、身份元组）、单元索引、已完成 `content_id`、上一页身份元组、头部边界、上一单元摘要，以及停滞/位移计数器。绝不携带回答载荷、标题、正文或媒体 URL。

## 3. 有栅栏的有界续跑

- 每步一个按页界定的单元；上限就是 `max_items`，且请求的 `limit` 为 `min(20, remaining)`，因为知乎页大小由客户端选择。
- 无法走完当前页的单元保留同一 offset 与见证，使下一单元重发同一请求并跳过已交付回答。
- 续跑延迟经 `MEDIA_SYNC_ZHIHU_SCAN_CONTINUATION_DELAY_SECONDS`（默认 300，两服务必须一致）。

## 4. 窗口位移检测

- 一页完成后，比较下一页身份元组与上一页的。非空交集意味着整数 offset 乘积在脚下移动了；offset 原样重放，位移计数器推进。
- `zhihu_window_shifted` 在有界次数的位移单元后阻塞，因为继续会静默重复或跳过回答。

## 5. 对账与增量头部检查

- 保留的 `is_end` 结束开启对账；从 offset 0 做一次有界头部重列，必须复现记录的边界，才进入增量轮询。
- 在头部通道中，id 与列表摘要都未变的回答记为 `unchanged`，这正是边界可复现的原因。

## 6. 按 Content 交付

- 只有完整媒体形状在场的回答才发布；失败回答按固定码计数，绝不阻塞无关回答。
- 重启与零工作重放保留内容寻址字节与确定性 NFO 输出。

## 7. 操作者界面

- 订阅详情暴露阶段、offset 步数、最近 `offset` 与最近结束/对账证据。绝不暴露 `url_token`、创作者 URL、回答载荷或媒体 URL。

## 8. 验证序列

1. 单元：游标往返与绑定拒绝、四种停止原因、小上限单元行为、offset 重放、位移阻塞、头部边界复现、覆盖 JSON 往返、失败详情隔离、有界形状。
2. 契约：页解析隐私、六种漂移形状、覆盖封印、受限 ≠ 源末。
3. 集成：`is_end` → 对账 → 增量并记录 `last_offset`、受限阻塞码、终态失败阻塞码。
4. 把所有头修订钉定测试推进到 `0020_zhihu_creator_answers`。
5. 完整 Python 与 Web 套件、Ruff、strict mypy、docs/upstreams、`git diff --check`；记录精确双语结果。
6. Linux 构建、真人知乎登录与真人金丝雀在操作者执行前保持 `NOT_RUN`。
