[English](next-delivery.md) | **中文**

# 下一交付：剩余创作者作品交付，然后是操作者门

## 状态

**仅为计划。** 本文档不授权任何部署、平台请求或驻留进程重启。它记录顺序，以及未来执行必须自行重新推导的上游事实，使每一步都从证据开始，而不是从复制的模板开始。

## 项目实际位置

四个平台现在携带同一条耐久创作者作品链，且各自从自己的钉定上游语义推导：

| 平台 | 执行 | 游标 / 分页信号 | 停止原因 |
| --- | --- | --- | --- |
| B 站 | 0074 | 页码，每页 30 | 源末、单元上限、受限 |
| 小红书 | 0076 | 不透明 `cursor` + `has_more` | 源末、空页停滞、受限、单元上限 |
| 抖音 | 0080 | 不透明 `max_cursor` + 整数 `has_more`，每页 18 | `has_more_false`、`empty_page_stalled`、`access_restricted`、`unit_cap_reached` |
| 快手 | 0081 | 回显 `pcursor` + 字符串哨兵 `no_more` | `no_more_echoed`、`empty_page_end`、`access_restricted`、`unit_cap_reached` |

微博、贴吧与知乎仍有媒体捕获、详情刷新与单次有界上限，但**没有耐久游标、没有交付进度表、没有按 Content 发布**。它们的创作者路径仍是产品最薄的一环：长历史无法续跑，部分运行对"已交付什么"没有耐久陈述。

## 每个未来执行必须重新推导的上游事实

以下是本次收尾期间从钉定 checkout 读到的；每个执行必须重读并引用，而不是信任这段摘要。

- **微博**（`.upstream/MediaCrawler/media_platform/weibo/client.py:346-412`、`core.py:326-331`）：`since_id` 是唯一游标；页大小硬编码为 10（`crawler_total_count += 10`），终止条件是算术推断 `cardlistInfo.total > crawler_total_count`，而不是 `has_more` 标记。`core.py` 传 `crawl_interval=0` 且无条数上限，因此上游循环无界。耐久层必须自带单元上限，并且必须把 `total` 当作**有时间边界的**源末候选，绝不是历史完整的证明。
- **贴吧**（`media_platform/tieba/client.py:684-710`、`:727`、`:857-860`）：使用 `pn`/`rn=20` 页码；终止是空 `thread_id_list` 或 `has_more == 0`；创作者身份是从主页 URL 解析出的 `portrait`，主题身份是 `thread_id`。
- **知乎**（`media_platform/zhihu/client.py:399-419`、`:462-490`）：`offset` 是整数 page×limit 乘积，不是不透明游标，因此插入或删除会使窗口位移；终止是 `paging.is_end`。耐久层必须按 `content_id` 去重并保留页见证，否则位移会静默跳过内容。

## 顺序

1. **0084 — 微博创作者作品耐久交付。** 迁移 `0018`，`weibo_subscription_progress` 表沿用同样的约束纪律，`since_id` 在不透明命名空间下逐字保留，单元在推断 `total` 上绝不推进，并明确区分 `total_inferred_end`、`access_restricted`、`unit_cap_reached`。验收：有界单元绝不以 `total` 声明完整；`max_items` 下的页尾保留；进入增量前完成头部对账；一条 IMAGE/VIDEO 作品经归档 → Emby 发布且零工作重放。
2. **0085 — 贴吧创作者作品耐久交付。** 迁移 `0019`，页码游标，`has_more == 0` 与空页结束码保持分离，portrait 身份绑定进游标指纹。验收与 0084 同构，并复用 0020–0022 shim 已证明的 `20 + 3` 页序。
3. **0086 — 知乎创作者作品耐久交付。** 迁移 `0020`，整数 offset 游标配显式页见证与 `content_id` 去重，使位移被检出而不是静默跳过。验收：两个单元之间的插入要么被交付、要么被标记，绝不丢失。
4. **0087 — 每平台一次有界操作者金丝雀。** 仅操作者。需要部署交接、已认领的原生会话，以及每平台一个暂停的单作者订阅。产出一份带明确 `PASS`/`FAIL`/`NOT_RUN` 行的资格记录；在此之前任何平台都不得称为 Supported。

## 明确不在本计划中

- 任何部署、真人登录、平台请求或 CDN 字节获取。
- 任何对 0074/0076/0080/0081 语义、迁移或进度表的改动。
- 任何"推断的结束（微博 `total`、位移后的知乎 `is_end`）证明历史完整"的声明。
