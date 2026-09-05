[English](verification.md) | **中文**

# 粘贴 Cookie 登录审计与验证

- 日期：2026-09-05
- 状态：只读源码审计完成；新增功能验证为 `NOT_RUN`
- 源码背景：记录文档时 HEAD 为 `7268352`，工作树存在并行登录修复。这不是干净工作树的发布验收。
- 锁定 MediaCrawler 检出：`d6f7c5bb906b6dac40ddf343ef9e26438a3de092`，只读版本检查与 `upstreams.lock.json` 一致。没有编辑或推进上游检出。

## 项目源码发现

以下仓库相对引用标识所检查的符号，不承诺未来 API 契约。

| 检查源码 | 只读发现 |
| --- | --- |
| `src/media_sync/application/workbench.py`，`AccountWorkbenchService` | Cookie 账户要求不透明凭据引用。同名已有账户若登录配置不同会冲突；创建账户不等于认证 Cookie。 |
| `src/media_sync/interfaces/api.py`，`AccountCreate` 及账户登录资格 | 创建账户接收 `credential_ref`，不接收原始 Cookie。现有二维码登录资格排除 Cookie 账户。 |
| `src/media_sync/infrastructure/db/repositories.py`，`AccountRepository`；`src/media_sync/domain/transitions.py` | 账户认证写入使用观察状态的比较并交换及固定转换规则。所审计路径没有通用的已验证 Cookie 替换事务。 |
| `src/media_sync/security/secrets.py`，`SecretResolver` 及 provider | 环境变量、受限文件和 keyring 引用可以解析秘密；provider 只读。这不构成自管私密写入存储。 |
| `src/media_sync/scheduler/mediacrawler_handler.py`，`MediaCrawlerScheduledHandler.run`；`src/media_sync/application/mediacrawler_download.py` | Cookie 采集/下载解析账户凭据引用。候选验证成功前不得发布给这些消费者。 |
| `src/media_sync/scheduler/service.py`，handler 上下文构建 | handler 的 `AccountRef` 携带凭据引用，没有认证状态门。现有已配置 Cookie 可以在没有本提案验证流程的情况下被尝试使用。 |
| `src/media_sync/integrations/mediacrawler/login.py` 和 `login_runner.py`，`_configure_upstream` / `_install_client_guard` | 登录模式为二维码和已保存会话探测。`update_cookies` 完成后没有新的远程认证检查就抛出已认证结果，不能用于验证导入候选。 |
| `src/media_sync/integrations/mediacrawler/bridge.py`，`BridgeRequest` / 私密输入 | Cookie 已有有界私密子进程输入路径，不是公开 manifest 字段。新导入必须保留此秘密边界。 |

部署中的操作者秘密挂载可能只读。新自管存储必须独立于 `/run/secrets`；本审计未批准把该挂载改成可写，也未选定新 secret scheme。Linux 仅所有者访问和 Windows ACL/DPAPI 留待下个冻结计划决定。

## 锁定平台发现

所有上游引用都相对于锁定的 `.upstream/MediaCrawler` 检出。这些是源码发现，不是已观察到的真实响应。

| 平台 / 源码 | 当前检查及其限制 |
| --- | --- |
| B 站，`media_platform/bilibili/client.py`，`pong` | 调用 `/x/web-interface/nav` 并检查 `isLogin`。最适合作为首个切片依据；需冻结严格布尔值和规范化当前用户身份校验，不能沿用宽松真值判断。 |
| 小红书，`media_platform/xhs/client.py`，`query_self` / `pong` | 调用 `/api/sns/web/v1/user/selfinfo`，检查嵌套的 `data.result.success`。存在自身端点，但准确身份/响应语义及签名客户端行为仍需验收。 |
| 知乎，`media_platform/zhihu/client.py`，`get_current_user_info` / `pong` | 调用 `/api/v4/me` 并检查 `uid` 和 `name`。需定义严格身份证明，避免邮箱等完整响应中的个人字段进入诊断。 |
| 微博，`media_platform/weibo/client.py`，`pong` | 调用 `/api/config` 并检查 `login`。存在远程登录标志，但准确已认证用户身份契约仍未定义。 |
| 快手，`media_platform/kuaishou/client.py`，`pong` | 使用 `ftype=1` 检查 GraphQL `visionProfileUserList` 的 result 为 `1`。审计未证明它是权威已登录自身身份证据。 |
| 抖音，`media_platform/douyin/client.py`，`pong` | 检查 local storage `HasUserLogin` 或 Cookie `LOGIN_STATUS`。粘贴标记即可在无远程证明时满足条件；此检查不得认证候选。 |
| 贴吧，`media_platform/tieba/client.py`，`pong` | 检查 `STOKEN`、`PTOKEN` 或 `BDUSS` 存在。Cookie 存在不等于有效；此检查不得认证候选。 |

锁定 `login_by_cookies` 实现也只是导入 Cookie 值，小红书专门导入 `web_session`。浏览器导入或 header 更新成功绝不能被记成远程验证成功。旧的有效 profile 会污染判断，因此必须隔离候选。

## 审计方法与结果

使用只读 `rg -n`、`Get-Content` 和有界行选择检查所列项目/上游符号；读取 `upstreams.lock.json`，运行 `git rev-parse --short HEAD` 与 `git -C .upstream/MediaCrawler rev-parse HEAD`。最初一次搜索包含猜测但不存在的 scheduler/adapter 路径，没有产生依据，随后通过真实源码搜索纠正。没有执行上游网络认证请求、平台浏览器会话、凭据解析或 Cookie 写入。

本文档增量仅增加八个中英双语 Markdown 文件。不交付 Cookie 实现、测试 fixture、端点、秘密 provider、迁移或账户变更。`.venv/Scripts/python.exe scripts/check_docs.py` 通过，检查 552 个 Markdown 文件。符号交叉检查将草案中的 handler 类名纠正为 `MediaCrawlerScheduledHandler`。文档验证不改变功能状态。

## 功能证据状态

| 验证门 | 状态 |
| --- | --- |
| 粘贴/解析/校验/保存实现及自动化测试 | `NOT_RUN` — 尚未实现 |
| 私密存储权限、原子替换及崩溃恢复 | `NOT_RUN` — 设计待定 |
| B 站真实自身认证、持久化与复用 | `NOT_RUN` |
| 其余六个平台的权威验证器及真实验收 | `NOT_RUN` — 尚未实现 |
| 本新增流程的 Cookie 作者抓取及 Emby/Jellyfin 播放 | `NOT_RUN` |

独立登录运行时/诊断测试结果及操作者提供的空白浏览器冒烟不构成 Cookie 认证验收。本审计不会创建任何平台或播放 PASS。
