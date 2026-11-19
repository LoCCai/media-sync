[English](qualification.md) | **中文**

# 资格记录：逐平台有界金丝雀

## 当前事实

下表每一行都是 `NOT_RUN`。本工作站未进行任何部署、原生登录、平台请求或 CDN 字节抓取，因此没有任何平台可以被称作已支持。

| 平台 | 耐久链 | 本地代码门禁 | 真人金丝雀 | 真实媒体字节 | 零工作重放 | 重启续跑 |
| --- | --- | --- | --- | --- | --- | --- |
| B 站 | 0074，迁移 `0014` | `PASS` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| 小红书 | 0076，迁移 `0015` | `PASS` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| 抖音 | 0080，迁移 `0016` | `PASS` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| 快手 | 0081，迁移 `0017` | `PASS` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| 微博 | 0084，迁移 `0018` | `PASS` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| 贴吧 | 0085，迁移 `0019` | `PASS` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| 知乎 | 0086，迁移 `0020` | `PASS` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

`本地代码门禁` 表示该执行的仓库套件与静态门禁通过。它不说明真人平台。

## 变成 `PASS` 需要什么

要让某一行改变，操作者必须从真实主机的一次会话提供：

1. 确切的源码修订、镜像标签与 `MEDIA_SYNC_SOURCE_REVISION`；
2. 观察到的数据库修订 `0020_zhihu_creator_answers`；
3. 一个已认领原生会话的 Account id、author id 与 `auth_revision`；
4. `run_id` 序列，以及每次运行的 `phase`、`stop_reason`、页见证、`batch_count`、`cursor_step_count`、已交付与已验证资产数；
5. 真实 CDN 字节数与结果媒体库路径及其 NFO；
6. 第二次零工作重放结果；
7. 一次 supervisor 重启，且表现为续跑而非游标重启。

在上述每一项都齐备之前，该行保持 `NOT_RUN`，而本文件是记录该事实的唯一位置。

## 为什么本地测试无法移动任何一行

仓库套件针对钉定上游源码证明确定性行为：游标往返、固定停止原因、页尾回放、窗口位移检测、受限≠源末，以及只凭封闭回执交付。它无法证明平台接受该请求 header、真人登录能产出可用会话、或 CDN 会提供声明的流。这些正是金丝雀存在的意义。
