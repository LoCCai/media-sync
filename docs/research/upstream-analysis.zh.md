[English](upstream-analysis.md) | **中文**

# 上游源码分析

本报告记录 [`upstreams.lock.json`](../../upstreams.lock.json) 所锁定提交的设计证据。路径相对于本地忽略的上游检出，可按 [`docs/upstreams.zh.md`](../upstreams.zh.md) 复现。

## MediaCrawler 结论

### 许可证与形态

定制许可证把使用、复制、修改和合并限制为非商业学习，禁止大规模抓取与商业使用，也没有清晰授予再分发/再许可权。因此新项目不得复制源代码，桥接也不会消除用户遵守该许可证的义务。

### 耦合与进程行为

- CLI 会修改全局配置（`cmd_arg/arg.py:344-402`）。
- 平台客户端依赖 Playwright page、Cookie 与相对项目文件。
- WebUI 只是围绕 `main.py` 的内存态、单子进程封装（`api/services/crawler_manager.py:30-41,93-151,205-239`）。
- 它把 Cookie 机密放进命令行参数并记录完整命令（`api/services/crawler_manager.py:113-118,234-235`）。
- 它在 `0.0.0.0:8080` 上无鉴权监听（`api/main.py:40-66,204-205`）。
- 浏览器状态默认按平台而非按账户使用 profile（`config/base_config.py:52-59,95-96`；代表性路径使用见 `media_platform/xhs/core.py:423-438`）。

这些约束说明：每个账户任务需要独立子进程、私有密钥通道、脱敏事件捕获和独立数据库；如果直接导入主服务，全局配置和浏览器生命周期会在任务间泄漏。

### 数据限制

MediaCrawler 使用平台专属表（`database/models.py:33-303`），刻意移除大部分作者资料与原始用户 ID（`database/models.py:19-25`），并用截断的无盐哈希/掩码名替代（`tools/user_hash.py:11-36`）。多数 `save_creator()` 路径是空操作。它没有订阅、运行、cursor 或下载任务模型。

文件输出支持 CSV/JSON/JSONL/数据库变体，但 JSONL 追加到按日期派生的文件名，JSON 则重写整个列表（`tools/async_file_writer.py:37-80`）。SQL 更新路径采用先查后写，而不是单条原子 upsert（`database/db_session.py:31-84`）。

因此上游数据库不能承担 `media-sync` 的订阅真相源；新项目必须独立保存用户主动订阅的远端 ID、作者标签、内容唯一键、运行水位与资产状态。

### 测试

代码树约有 21 个 `test_*.py` 文件、约 115 个 test/test-class 声明，但唯一的 GitHub 工作流只构建文档，不运行 Python 测试（`.github/workflows/deploy.yml:26-64`）。没有七平台登录/作者/媒体端到端套件，也没有 Emby 覆盖。

## bili-sync-up 结论

该仓库使用 MIT 许可证，是 Rust 应用而非可直接调用的库。更适合借鉴或在保留声明后提炼模块，不适合成为长期子进程依赖。

### 相关模式

- 丰富的 NFO 变体建模 Movie、TVShow、创作者/UP 主、Episode 与 Season（`crates/bili_sync/src/utils/nfo.rs:14-147`）。
- XML 生成带缩进、UTF-8、字段可配置，并过滤非法 XML 字符（`crates/bili_sync/src/utils/nfo.rs:149-238`）。
- 工作流创建创作者、剧集、季与集的边车（`crates/bili_sync/src/workflow.rs:10413-10663`）。
- 重复扫描与凭据刷新是长驻任务（`crates/bili_sync/src/main.rs:28-165`；`crates/bili_sync/src/task/video_downloader.rs:278-287,1374-1417`）。
- 重试延迟与风控处理被分类处理，而不是当作通用失败（`crates/bili_sync/src/error.rs:194-335`；`crates/bili_sync/src/task/video_downloader.rs:126-201`）。
- 下载与工作流状态被持久化并可独立恢复，而不是用一个布尔值表示。

这些模式直接影响自有 NFO 写入器、分类状态机、可重启调度以及内容/资产/导出分表；不会继承 BVID 中心身份或单一全局扫描间隔等 B 站专属假设。

## 复用决策

| 领域 | MediaCrawler | bili-sync-up | 方案 |
| --- | --- | --- | --- |
| 平台浏览器与签名 | 按其许可证可选外部桥接 | 仅 B 站 | 适配端口，逐步原生实现 |
| 作者订阅 | 缺失 | B 站特定 | 独立统一模型 |
| 增量状态 | 缺失 | 成熟模式 | 已知 ID、水位、cursor、持久任务 |
| 下载 | 部分且整体读内存 | 可恢复工作流思想 | 流式暂存、校验、探测、重试 |
| Emby / Jellyfin | 缺失 | 丰富 NFO 与命名 | 独立平台无关导出器 |
| Web/API 安全 | 无鉴权广泛监听 | 本地自托管 UI | 默认回环，远程绑定前鉴权 |

## 主要风险

1. **许可证** — 外部进程是工程边界，不是许可证豁免。商业分发需要书面授权或独立适配器。
2. **平台易变** — 浏览器选择器、签名与非官方 API 会无预警变化；适配器能力必须有版本且可观察。
3. **账户/风控** — 交互验证与临时封锁无法消除；运行需要显式的 `awaiting_auth` 与风控状态。
4. **虚假增量** — 忽略旧输出记录并不能限制上游请求；桥接需要看门狗与显式的全历史确认。
5. **媒体歧义** — 过期 URL、DASH/多段视频与图文帖子需要爬虫元数据之外的刷新、合并与幻灯片策略。
6. **隐私** — 订阅归档有意把内容关联到作者；采集必须限于用户选择的公开创作者，并保存在受访问控制的本地存储中。
