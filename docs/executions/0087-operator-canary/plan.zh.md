[English](plan.md) | **中文**

# 计划：逐平台操作者金丝雀

状态：**流程已冻结；每一行都是 `NOT_RUN`。** 本文档未在真实主机上执行任何步骤，本执行不改动产品行为。

## 1. 一次只做一个平台

每个会话只跑一个平台金丝雀，以便证据可归属。顺序：B 站（历史最长）、小红书、抖音、快手、微博、贴吧、知乎。

## 2. 触碰平台前先证明身份

遵循既有的[部署交接](../0077-deployment-provenance-preflight/deployment-handoff.zh.md)：

- `git rev-parse HEAD` 必须等于镜像的 `org.opencontainers.image.revision` 标签与记录的 `MEDIA_SYNC_SOURCE_REVISION` 构建参数。
- `scripts/check_upstreams.py` 必须报告两个钉定检出均已验证。
- `media-sync doctor --deep` 必须报告预期数据库修订（`0020_zhihu_creator_answers`）与各平台续跑延迟。
- `media-sync` 与 `supervisor` 必须携带**相同**的 `MEDIA_SYNC_<PLATFORM>_SCAN_CONTINUATION_DELAY_SECONDS` 值；不一致即本次运行无效。

## 3. 认领一个真人会话并暂停其他一切

- 经 `/crawler/` 用真实账户登录一次，并把会话认领到该平台**恰好一个** Account。
- 暂停所有其他 Subscription，避免金丝雀与无关流量或下载混杂。
- 记录 Account id、author id 与 `auth_revision`。

## 4. 运行一次有界、单作者金丝雀

- 为一个创作者创建一个 Subscription，`max_items` 取小值（最小但仍能强制出现页尾的值，例如每页 20 的 feed 取 25）。
- 驱动调度直到耐久进度行进入 `incremental`，并为每次运行记录：`run_id`、`phase`、`stop_reason`、消耗的页见证、`batch_count`、`cursor_step_count` 与已交付/已验证资产数。
- 每个平台必须观察到的事项（来自它自己的执行记录）：

| 平台 | 必须观察到 | 绝不能观察到 |
| --- | --- | --- |
| B 站 | 源末开启对账 | 用页数宣称完整性 |
| 小红书 | 空页停滞与源末区分 | 把停滞当作结束 |
| 抖音 | `has_more_false` 结束 | 把推断的结束当作完整 |
| 快手 | `no_more_echoed` 结束 | 忽略回显的哨兵 |
| 微博 | `total_inferred_end` 记为推断 | 把 `total` 呈现为完整性 |
| 贴吧 | `has_more_false` 结束，若发生则重复页停滞 | 把 `error_code != 0` 当作结束 |
| 知乎 | `is_end` 结束，若发生位移则 `zhihu_window_shifted` | 位移窗口静默跳过回答 |

## 5. 下载、发布与重放

- 确认已从平台 CDN 取得真实媒体字节、写出确定性 NFO，且文件落到媒体库。
- 重放同一金丝雀：第二次运行必须交付**零**新内容、下载**零**新字节，而耐久行仍然推进计数器。
- 重启常驻 supervisor 一次，确认该行继续而非从 offset/页码零重新开始。

## 6. 记录资格

- 在 [`qualification.md`](qualification.md) 为每个平台写一行，取 `PASS`、`FAIL` 或 `NOT_RUN`，附确切源码修订、迁移头、run id 与观察到的迁移。
- 只有真实登录与真实请求产出的证据才能把一行变成非 `NOT_RUN`。本地测试运行是代码证据，绝不是真人平台证据。

## 7. 明确不在范围

- 从本执行改动产品代码。若金丝雀失败，修复属于新的编号执行，且必须先重新推导该平台事实。
- 在没有上述证据的情况下宣称平台已支持，或移除 `NOT_RUN` 行。
