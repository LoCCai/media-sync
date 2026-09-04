# media-sync 后续推进计划书合集

- 编制日期：2026-09-04
- 评审边界：`LoCCai/media-sync` 当前 `main`，阶段 B 容器已启动但 MediaCrawler checkout 资格检查失败
- 现场状态：
  - Web/API 服务正常，`health` 与数据库 `ready` 正常；
  - Chromium 在运行容器内可由 `mediasync` 用户启动，版本 `151.0.7922.34`；
  - `mediacrawler doctor` 返回 `checkout_invalid`；
  - Bilibili 与小红书登录均收敛为 `account_login_configuration_invalid`，二维码未生成；
  - 当前控制台仍是单文件运维控制台，尚不是完整的媒体归档管理后台；
  - 当前端口发布为 `0.0.0.0:8632`，而应用没有自身鉴权。

## 总体判断

项目核心领域模型、下载/归档/Emby 输出和调度基础已经远超“原型”水平。后续不应继续优先扩充更多媒体形状，而应沿两条主线推进：

1. **先恢复真实运行闭环**：解决 `checkout_invalid`，建立可解释的深度预检、持久任务和阶段 B/C 验收。
2. **再建设 Web Console v2**：参考 bili-sync-up 的信息架构与交互方式，但围绕 media-sync 的七平台账户、订阅、内容、资产、归档和 Emby 模型重新设计，不能只把当前 HTML 换皮。

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
0047-d1  checkout_invalid 精确定位与修复
    ↓
0047-d2  深度就绪检查、构建/运行时事实统一
    ↓
阶段 B   Linux 完整门禁、持久性、备份恢复
    ↓
阶段 C   Bilibili + 小红书真人金丝雀
    ↓
0050     Web Console v2 基础设施
    ↓
0051     账户登录与订阅工作台
    ↓
0052     持久操作、任务队列、日志与事件流
    ↓
0053     内容、资产、归档与媒体库浏览
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
