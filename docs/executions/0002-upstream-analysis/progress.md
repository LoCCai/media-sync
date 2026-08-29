# Execution 0002 progress / 执行 0002 推进结果

- Status / 状态：Complete / 已完成
- Started / 开始时间：2026-08-30 03:25 +08:00

## Completed / 已完成

- Confirmed the CLI platform, login, crawler-type and storage enums.
- Confirmed creator-ID CLI routing for six platforms and identified missing Zhihu routing.
- Confirmed media download is controlled by the non-CLI `ENABLE_GET_MEIDAS` switch.
- Began tracing platform-specific login methods and Emby NFO structures.
- Completed independent reviews of both upstream architectures and license boundaries.
- Published product requirements, a seven-platform truth matrix, component architecture and ADR-0002.
- Added reproducible documentation-link and upstream-lock validation scripts.

- 确认 CLI 的平台、登录、爬虫类型和存储枚举。
- 确认六个平台的创作者 ID CLI 路由，并发现知乎路由缺失。
- 确认媒体下载由未暴露到 CLI 的 `ENABLE_GET_MEIDAS` 开关控制。
- 已开始跟踪平台登录方法和 Emby NFO 结构。
- 完成两个上游的独立架构与许可证边界审查。
- 发布产品需求、七平台真实能力矩阵、组件架构和 ADR-0002。
- 增加可复现的文档链接与上游锁定验证脚本。

## Decisions and deviations / 决策与偏差

- Python 3.11+ is used instead of requiring 3.12 because the verified local runtime is 3.11.8 and both the planned stack and pinned MediaCrawler support it.
- Upstream's global phone-login enum is not exposed by the research bridge because no platform has a working end-to-end phone path through its main entry.
- MediaCrawler remains an optional, license-gated research bridge; the default core and tests are independently implemented.
- Emby output is generated from a normalized immutable archive, not directly from crawler folders.

- 采用 Python 3.11+ 而非强制 3.12，因为已验证本地运行时为 3.11.8，规划技术栈和锁定版 MediaCrawler 均支持它。
- 研究桥接器不开放上游全局手机号枚举，因为没有平台能通过其主入口完成可用的手机号闭环。
- MediaCrawler 只作为可选、受许可证门禁的研究桥接；默认核心和测试独立实现。
- Emby 输出从归一化不可变档案生成，而不是直接整理爬虫目录。

## Remaining / 待完成

None for this execution. / 本次执行无剩余项。
