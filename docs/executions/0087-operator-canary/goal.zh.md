[English](goal.md) | **中文**

# 目标：逐平台操作者金丝雀

执行 0084、0085、0086 已补齐最后三条创作者作品交付，因此七个创作者平台现在共享同一条耐久链：

| 平台 | 执行 | 迁移 | 游标/分页信号 | 固定停止原因 |
| --- | --- | --- | --- | --- |
| B 站 | 0074 | `0014` | 页码，每页 30 | `source_end`、`head_boundary`、`item_limit`、`list_limit`、`restarted` |
| 小红书 | 0076 | `0015` | 不透明 `cursor` + `has_more` | `has_more_false`、`empty_page_stalled`、`access_restricted`、`unit_cap_reached` |
| 抖音 | 0080 | `0016` | 不透明 `max_cursor` + 整数 `has_more` | `has_more_false`、`empty_page_stalled`、`access_restricted`、`unit_cap_reached` |
| 快手 | 0081 | `0017` | 回显 `pcursor` + `no_more` | `no_more_echoed`、`empty_page_end`、`access_restricted`、`unit_cap_reached` |
| 微博 | 0084 | `0018` | `since_id` + 算术 `total` 推断 | `total_inferred_end`、`empty_page_end`、`access_restricted`、`unit_cap_reached` |
| 贴吧 | 0085 | `0019` | 1 起 `pn` + `rn=20` 的 `has_more` | `has_more_false`、`empty_page_end`、`access_restricted`、`unit_cap_reached` |
| 知乎 | 0086 | `0020` | 整数 `offset` + `paging.is_end` | `is_end`、`empty_page_end`、`access_restricted`、`unit_cap_reached` |

剩下的**不是代码**。每一项剩余工作都需要 Linux 主机、真人原生登录、真实平台请求与真实 CDN 字节，而这台工作站无法提供。这些项目的诚实状态就是 `NOT_RUN`，任何代码改动都无法把它们变成 `PASS`。

## 交付物

一份操作者流程，每次只针对一个平台：

1. 证明运行中的镜像就是已推送的确切源码修订；
2. 证明数据库已迁移到 `0020_zhihu_creator_answers`（按其部署形态是 PostgreSQL 或 SQLite）；
3. 把一个真人原生会话认领到一个 Account，并暂停所有无关 Subscription；
4. 运行一次有界、单作者金丝雀，并记录它观察到的耐久阶段迁移（`backfill` → `reconciling` → `incremental`）；
5. 下载真实媒体字节，生成确定性 NFO，并把结果落到媒体库；
6. 第二次重放同一金丝雀并证明**零**新增工作；
7. 为每个平台记录一行明确的 `PASS` / `FAIL` / `NOT_RUN`，附确切修订、迁移头与观察到的 run id。

## 明确不在范围

- 在某个平台自己的行为 `PASS` 之前宣称它"已支持"。
- 把推断的结束（微博 `total`，或知乎位移后观察到的 `is_end`）当作完整历史的证明。
- 本次文档执行中的任何部署、重启、登录或平台调用。本记录只固定流程与当前 `NOT_RUN` 事实。
