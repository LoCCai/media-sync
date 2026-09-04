[English](verification.md) | **中文**

# 执行 0054 验证

- 状态：阶段 A 已完成并通过冻结验证；执行 0054 继续为阶段 B 保持开启
- 收尾日期：2026-09-05
- 基线：`22b5864`
- 计划与加固提交：`793d33b`、`d913537`
- 实现提交：`554277c`、`efdb27c`、`2ad051c`、`1b34632`
- 数据库 revision：`0007_media_server_operations`

## 自动化证据

| 检查 | 过程 | 结果 |
| --- | --- | --- |
| Git 同步 | 恢复推进前执行 `git fetch origin --prune` 并比较本地 `HEAD` 与 `origin/main` | `PASS`——两者均为 `d913537`；没有合并远端提交，实现工作树得到保留 |
| 首次完整套件诊断 | 测试隔离修正前执行 `uv run --frozen pytest -q -p no:cacheprovider` | 已记录且未丢弃的 `FAIL`——505.38 秒内 1 failed、2617 passed、3 skipped、1 warning；唯一失败是依赖 logger 捕获受测试顺序影响，敏感值始终保持脱敏 |
| Logger 状态回归 | 保存、启用并恢复 logger handlers、filters、level、propagation、disabled 及全局 logging disable 状态后，定向运行依赖 wire logger 测试 | `PASS`——0.39 秒内 1 项通过 |
| Connector 专项与审查 | 媒体服务器 connector 单元模块，加 dispatch、deadline、single-flight 与脱敏边界独立审查 | `PASS`——1.65 秒内 52 项通过；无剩余 P0/P1/P2 |
| 取消/收尾线性化 | 4 个精确 CAS 测试、两个 Operation 集成模块、5 次 final-lock-first 重复及一次独立复核 | `PASS`——4 个精确测试与 62 个模块测试通过；5 次重复全部通过；独立复核的 3 个聚焦测试通过且没有剩余 P0/P1/P2 |
| Web 格式与单测 | `npm --prefix web run format:check`；`npm --prefix web test -- --run` | `PASS`——Prettier 干净；7 个文件、58 项测试通过 |
| Svelte/TypeScript 与 bundle | `npm --prefix web run check`；`npm --prefix web run build` | `PASS`——0 errors、0 warnings；adapter-static 生产构建完成 |
| 本地浏览器交互 | 隔离本地服务/浏览器：Library、Settings、Jobs；未配置媒体服务器控制；资格展示；请求体覆盖拒绝 | `PASS`——路由正常；未配置时 probe/scan 禁用；`NOT_RUN` 与 `NOT_IMPLEMENTED` 保持区分；URL 覆盖请求体返回 422 `extra_forbidden` |
| Python 质量 | `uv run --frozen ruff check src tests scripts`；`uv run --frozen ruff format --check src tests scripts`；`uv run --frozen mypy --strict src` | `PASS`——lint 干净；213 个文件格式正确；101 个源码文件类型检查零问题 |
| 冻结完整 Python 套件 | 全部代码/审查修正后执行 `uv run --frozen pytest -q -p no:cacheprovider` | `PASS`——505.44 秒内 2620 passed、3 skipped、1 个既有 warning；skip 是 3 个 Windows 不适用的 POSIX venv/mode 用例 |
| 编译与发行包 | `uv run --frozen python -m compileall -q src tests`；`uv build` | `PASS`——compileall 无输出；`media_sync-0.1.0` wheel 与 sdist 构建成功且保持忽略 |
| 文档与上游 | `uv run --frozen python scripts/check_docs.py`；`uv run --frozen python scripts/check_upstreams.py` | `PASS`——482 份 Markdown 与两个锁定上游 checkout |
| 跟踪产物与机密性 | 拟跟踪集合、生成/运行时 denylist、工作站路径及 private-key/API-key 模式复核，然后执行 `git diff --check` | `PASS`——773 个跟踪文件；`.mimosa/` 与生成/运行时输出被排除；拟提交 diff 不含真实工作站路径、私钥或实际 API key；空白干净 |
| Git 发布对账 | 逐个推送中英双语实现边界及包含本记录的收尾提交，再比较本地 `HEAD`、`origin/main` 与 GitHub `refs/heads/main` | `PASS`——发布后三者一致；按约定不在收尾提交内嵌其自身 SHA |

聚焦选择存在重叠，不得相加。`.mimosa/`、`.upstream/`、数据库、归档/导出/任务运行数据、XML 报告、`node_modules`、`web/build`、`.svelte-kit`、`dist` 及隔离 smoke 目录均不进入任何提交。

## 需求证据

| 需求 | 已验证证据 |
| --- | --- |
| 安全受管树权威 | 测试要求作者 UUID、唯一成功 `export.emby` 数据库前驱链 head 及其精确严格 manifest 身份；调用方路径与单独磁盘 manifest 均无权威 |
| 有界只读检查 | Existing-only 作者锁、进程 single-flight、最多 128 个文件、已配置字节/截止时间预算及 manifest-bound HMAC cursor 均有覆盖；非零末页保持 page scope；读取不修复、不删除，也不创建目录/锁 |
| 跨平台身份与漂移 | POSIX 描述符相对 no-follow 遍历与 Windows no-delete-share 句柄覆盖祖先、manifest 和文件替换；描述符/名称身份、普通文件及单硬链接检查关闭失败；新鲜度与完整性彼此独立，包括正常 `blocked` 新鲜度 |
| 安全不可变配置 | 全有或全无启动校验只接受一个规范 Emby/Jellyfin 配置；API 投影省略 key、完整 secret reference、Library ID、服务器路径与网络范围；校验错误隐藏被拒绝值 |
| 网络与凭据边界 | 每个 DNS 答案都必须匹配已配置 CIDR；连接 IP 固定并保留原 Host/SNI；代理和重定向被禁用；key 只在请求入口解析，请求作用域脱敏覆盖动态依赖 logger |
| 精确 probe/刷新协议 | Probe 只用 `GET /System/Info` 与 `GET /Library/VirtualFolders`；精确 ID/path 发现后，scan 只用固定 `POST /Items/{ItemId}/Refresh`；不存在全局刷新回退或 POST 重试 |
| Dispatch 与取消真实性 | Transport-entry gate 是 dispatch 边界；dispatch 前取消/截止不发送 POST；dispatch 后任何歧义均不可重试并记 acceptance-unknown；锁定最终持久化给出确定 cancel-first/final-first 结果；重启保守记 `interrupted` |
| 持久 API 与 migration | Revision `0007` 增加两个封闭 kind，downgrade 不删除审计证据；targetless 幂等 Operation、当前配置证据、payload 白名单、API 覆盖拒绝及支持包安全均有覆盖 |
| 资格真实性 | Schema v1 分开自动化证据、实现状态与真人状态；已实现的 probe/discovery/targeted acceptance 继续真人 `NOT_RUN`；缺失的扫描完成/项目查找/播放/自动联动为 `NOT_IMPLEMENTED` 且无真人状态 |
| Web 行为 | 单测与浏览器 smoke 覆盖媒体树分页、安全配置、资格、持久动作、请求代际隔离、Settings 故障隔离及不重叠的 Jobs 轮询 |

## 证据政策与剩余门

本轮没有使用真实平台账户、作者 endpoint、平台 API/CDN、下载的作者媒体、Linux 持久性/备份/进程演练或真实 Emby/Jellyfin 服务器。本地树、mock transport 与浏览器/API smoke 只证明冻结的阶段 A 契约。

真实连接探测、Library 发现和定向刷新接受，在执行 0047 记录获授权服务器证据前继续为 `NOT_RUN`。扫描完成进度与 provider/path 项目查找继续为 `NOT_IMPLEMENTED`，属于需另行冻结的 0054-B。经鉴权播放证据写入与可写/破坏性运维面继续归 0055。导出后自动扫描是 `NOT_IMPLEMENTED`，尚无冻结的后续归属。这些边界防止本地或 mock 成功被写成虚假真人资格。
