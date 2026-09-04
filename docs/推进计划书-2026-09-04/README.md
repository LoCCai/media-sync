# media-sync 后续推进计划书合集

- 编制日期：2026-09-04
- 评审边界：原稿基于执行 0050 收尾；0053 已基于 `be26cc7` 与计划 `66e18ff` 完成交付和冻结验证，完整套件为 2456 passed、3 skipped；下一产品切片是 0054
- 现场状态：
  - Web/API 服务正常，`health` 与数据库 `ready` 正常；
  - Chromium 在运行容器内可由 `mediasync` 用户启动，版本 `151.0.7922.34`；
  - `license_digest_mismatch` 根因已修复为跨平台 canonical-LF 资格摘要；修复版镜像的 doctor 与深度预检均已通过；
  - Bilibili 与小红书真人登录仍保持 `NOT_RUN`，不得用离线或旧镜像证据替代真人结论；
  - SvelteKit 5 Web Console v2 基础已实现，旧单文件控制台仅保留在 `/legacy` 作为迁移回退；
  - 容器内服务监听 `0.0.0.0:8632`，仓库 compose 模板只发布到宿主回环；操作者现场宿主绑定仍待阶段 B 上报，应用当前没有自身鉴权。

## 总体判断

项目核心领域模型、下载/归档/Emby 输出和调度基础已经远超“原型”水平。后续不应继续优先扩充更多媒体形状，而应沿两条主线推进：

1. **先完成真实运行闭环**：`checkout_invalid` 与深度预检已经闭环；当前 P0 是阶段 B 的 Linux 持久性/恢复/进程证据和阶段 C 真人金丝雀。
2. **并行建设 Web Console v2**：0050 基础、0051 七平台账户/订阅工作台、0052 持久 Operation/Event 与任务中心，以及 0053 内容/资产/安全归档浏览器已经交付；下一切片推进 0054 媒体库树与 Emby/Jellyfin 联动，不复制 bili-sync-up 的单平台领域模型。

## 文件索引

1. [00-总体路线图与版本边界.md](00-总体路线图与版本边界.md)
2. [01-0047-d1-checkout-invalid缺陷闭环计划.md](01-0047-d1-checkout-invalid缺陷闭环计划.md)
3. [02-Web管理后台产品规划.md](02-Web管理后台产品规划.md)
4. [03-Web技术架构与迁移计划.md](03-Web技术架构与迁移计划.md)
5. [04-账户登录与订阅工作台计划.md](04-账户登录与订阅工作台计划.md)
6. [05-持久任务队列日志与可观测性计划.md](05-持久任务队列日志与可观测性计划.md)
7. [06-内容资产媒体库与Emby联动计划.md](06-内容资产媒体库与Emby联动计划.md)
8. [07-安全部署配置与运维计划.md](07-安全部署配置与运维计划.md)
9. [08-测试真人验收与发布计划.md](08-测试真人验收与发布计划.md)
10. [diagnose_mediacrawler_checkout.sh](diagnose_mediacrawler_checkout.sh)

## 推荐执行顺序

```text
0047-d1  checkout_invalid 精确定位与修复（已完成）
    ↓
0047-d2  深度就绪检查、构建/运行时事实统一（已完成）
    ↓
阶段 B   Linux 完整门禁、持久性、备份恢复（进行中，P0）
    ↓
阶段 C   Bilibili + 小红书真人金丝雀（阶段 B 后，NOT_RUN）
    ↓
0050     Web Console v2 基础设施（已完成，可与阶段 B 独立交付）
    ↓
0051     能力驱动的账户登录与订阅工作台（已实现并完成离线/API/前端验证）
    ↓
0052     持久操作、任务队列、安全事件流与窄化支持包（已交付，2315 passed、3 skipped）
    ↓
0053     内容、资产与安全归档浏览（已完成，2456 passed、3 skipped）
    ↓
0054     Emby/Jellyfin 联动与资格视图
    ↓
0055     单操作者访问控制、设置与运维中心
    ↓
0.2 RC   七平台分级、迁移和发布收尾
```

完整 Web v2 不应成为 `v0.1.0-rc1` 的前置条件。`v0.1` 应以真实运行闭环、两金丝雀资格和最低可用诊断后台为目标；完整后台归入 `0.2`，避免再次推迟现网验证。

## 研究依据

- media-sync：<https://github.com/LoCCai/media-sync>
- MediaCrawler：<https://github.com/NanmiCoder/MediaCrawler>
- bili-sync-up 锁定研究版本：<https://github.com/NeeYoonc/bili-sync-up/tree/dcb5bb73b56ac45b2525da14b389e185b0ea6dbd>
- bili-sync-up Web 侧栏：<https://github.com/NeeYoonc/bili-sync-up/blob/dcb5bb73b56ac45b2525da14b389e185b0ea6dbd/web/src/lib/components/app-sidebar.svelte>
- bili-sync-up 实时任务队列：<https://github.com/NeeYoonc/bili-sync-up/blob/dcb5bb73b56ac45b2525da14b389e185b0ea6dbd/web/src/routes/queue/%2Bpage.svelte>
- bili-sync-up 日志页：<https://github.com/NeeYoonc/bili-sync-up/blob/dcb5bb73b56ac45b2525da14b389e185b0ea6dbd/web/src/routes/logs/%2Bpage.svelte>

0052 只借鉴任务队列的信息层级，没有复制通用日志文件页。已交付面是五类 API Operation 的安全结构化事件、Jobs 路由任务中心及 16 KiB 仅聚合 JSON 支持响应；不暴露 raw idempotency key、requester、lease、revision 或请求指纹。独立 Logs 页面、统一 supervisor 接入、订阅 pause/resume/delete 审计与宽泛支持归档均继续后移。当前 Web 单元覆盖状态/reducer/重连/轮询回退，真实浏览器路由交互测试列为后续质量债。
