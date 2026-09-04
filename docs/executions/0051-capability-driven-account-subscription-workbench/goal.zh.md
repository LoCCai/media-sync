[English](goal.md) | **中文**

# 执行 0051 目标

- 状态：已实现并通过离线验证；真人资格仍为 `NOT_RUN`
- 日期：2026-09-04
- 前驱：`38e0ebe`（Console v2 之后 Linux 运行时预检全绿）
- 范围：能力契约驱动的账户登录与创作者订阅工作台
- 数据库迁移：无
- 实现提交：后端 `6ed7ab3`；Web `178e557`
- 收尾提交：包含最终记录的提交（不嵌入自身 SHA）

## 结果

1. 交付一份固定、有界、有版本的 MediaCrawler 七平台能力契约，统一描述稳定平台顺序、登录方式、QR 可用性、作者输入提示、secret reference 资格、全历史确认、已通过离线资格的媒体形状、限制和如实的 `NOT_RUN` 真人状态。
2. 把账户/订阅校验和幂等创建收口到 CLI 与 REST 共用的 application workbench。无效或未确认的 MediaCrawler 草稿会在 Account、Author 或 Subscription 变更前失败；安全预览和结果绝不返回凭据或作者权限引用。
3. 新增只覆盖登录前提的账户级预检。数据库、账户资格、许可证、checkout、Python 运行时、浏览器、profile 可写性和账户锁失败会在新建进程内 Operation 或启动 child 前停止；ffmpeg 与 ffprobe 明确不属于登录前提。
4. 把二维码读取绑定到精确的活动 QR `LoginSession`；账户路由仅作为兼容解析器；发布新 session 前在账户锁内移除旧二维码材料；保留 `202` 等待、`200` 图片、`410` 终态和 `404` 未知/不合格生命周期。
5. 把账户和订阅页面升级为能力驱动工作台：账户组合状态与预检诊断控制登录，账户选择、作者/策略输入、服务端预览和显式确认控制订阅创建。
6. 暴露白名单化的订阅策略与 checkpoint 摘要，不返回原始 cursor、签名作者 URL、凭据引用、二维码材料、profile 路径或运行时路径。

## 验收结果

- 后端拥有的 v1 能力端点以稳定顺序覆盖 `xhs`、`dy`、`ks`、`bili`、`wb`、`tieba`、`zhihu`。只有 XHS 允许不透明作者 secret reference；Bilibili 与微博只建议 numeric ID，不收窄兼容校验器。
- MediaCrawler 作者 ID 共用保守的 `[A-Za-z0-9._-]{1,255}` 校验器。Bilibili、抖音、快手和微博必须在写入任何 Author 或 Subscription 前提供 `allow_full_history=true`；等价 CLI/API 草稿共用同一 policy builder。
- SQLite 同草稿并发创建通过 workbench 范围的 immediate writer reservation 收敛为唯一 Account 或 Subscription；schema 与 migration 均未变化。
- 登录启动在分配进程内 Operation 前立即调用同一预检 evaluator。强制检查失败不会新建 Operation、LoginSession 或 child。
- 精确 session QR 测试覆盖活动 session 所有权、非 QR 拒绝、废弃 session 协调、有界普通文件读取、读取后 session 复验和终态不泄露。
- Python 完整套件通过：`2135 passed, 3 skipped`；全部前端与静态/打包门通过。任何离线测试都不作为真人平台资格证据。

## 已接受偏差与延期边界

通过的预检快照与随后创建的进程内 Operation/后台登录 service 并非一个跨进程原子事务。因此两个 API 进程仍可能同时通过预检，再由持久登录边界选出赢家。既有 `LoginSession` compare-and-set 规则和账户 OS 锁保持权威，并使落败尝试关闭失败；这属于不阻塞 0051 的协调/UX 残余，不是凭据或二维码权限绕过。持久 Operation、跨进程幂等、Event 存储、SSE、结构化日志、取消、重启后历史、订阅审计/删除与支持包仍归 Execution 0052。

丰富内容恢复归 0053，媒体服务器控制/资格归 0054，操作者鉴权归 0055，最终迁移/发布归 0056。Execution 0047 继续负责 Linux 持久性/备份/进程证据、七平台全部真人账户行和真实 Emby/Jellyfin 重扫/播放。
