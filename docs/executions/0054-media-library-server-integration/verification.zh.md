[English](verification.md) | **中文**

# 执行 0054 验证

- 状态：阶段 A 与阶段 B 均已完成并通过本地验证；真人资格保持 `NOT_RUN`
- 收尾日期：2026-09-05
- 基线：`22b5864`
- 计划与加固提交：`793d33b`、`d913537`
- 阶段 A 实现提交：`554277c`、`efdb27c`、`2ad051c`、`1b34632`
- 阶段 B 规划与实现/验证提交：`d7e14c9`；`b4af46d`、`ff5da07`、`88f5ed0`、`22bd9ef`、`48ecbe9`、`d8bbdf7`
- 数据库 revision：`0007_media_server_operations`

## 自动化证据

阶段 A：

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

阶段 B：

| 检查 | 过程 | 结果 |
| --- | --- | --- |
| 实现历史 | 对照冻结计划 `d7e14c9` 审查 `b4af46d`、`ff5da07`、`88f5ed0`、`22bd9ef`、`48ecbe9` 与 `d8bbdf7` | `PASS`——精确 lookup、持久观察 checkpoint、作者编排/API、qualification schema v2、Web 表面与真实 PostgreSQL 竞态加固按中英双语边界分别落地 |
| 冻结完整 Python 套件 | 启用隔离真实 PostgreSQL 服务后运行 `uv run --frozen pytest -q -p no:cacheprovider` | `PASS`——`2763 passed, 3 skipped, 1 warning in 544.08s`；11 项 PostgreSQL 用例均实际运行，skip 是 Windows 不适用的 POSIX 用例，warning 是既有 Starlette/httpx 弃用提示 |
| 真实 PostgreSQL 竞态专项 | `uv run --frozen pytest -q -p no:cacheprovider tests/integration/test_operation_postgresql_races.py` | `PASS`——11 passed，并通过 `pg_stat_activity.wait_event_type='Lock'` 观察到真实行锁等待 |
| PostgreSQL + SQLite Operation 联合 | 真实 PostgreSQL 竞态专项加 `tests/integration/test_operation_coordinator.py` 与 `tests/integration/test_operation_repository.py` | `PASS`——84 passed in 9.22s |
| Python 质量 | `uv run --frozen ruff check src tests scripts`；`uv run --frozen ruff format --check src tests scripts`；`uv run --frozen mypy --strict src`；`uv run --frozen python -m compileall -q src tests` | `PASS`——lint、格式、严格类型与字节编译均完成 |
| 发行包 | `uv build` | `PASS`——wheel 与 sdist 构建成功 |
| 首次 Web 尝试 | 从 `web/` 将 `pnpm build` 与其他 Web 门禁命令并发启动 | 已记录的诊断 `FAIL`——只有生产 build 因命令争用 `.svelte-kit` 中间产物而失败；本行不声明单元测试失败 |
| Web 串行门禁 | 从 `web/` 不重叠运行 `pnpm test`、`pnpm format:check`、`pnpm check` 与 `pnpm build` | `PASS`——69 项测试通过；格式通过；Svelte check 为 0 errors、0 warnings；生产构建完成 |
| 锁定上游 | `uv run --frozen python scripts/check_upstreams.py` | `PASS`——两个固定 upstream checkout 与记录 revision 一致 |
| 收尾仓库门禁 | 文档、tracked-output、拟提交 diff 敏感模式、冻结阶段 B goal/plan 与空白检查 | `PASS`——490 份 Markdown；787 个 tracked 文件且零禁入 generated/runtime output；没有工作站路径、private-key 或赋值形式 secret 命中；冻结 goal/plan 未变化；`git diff --check` 干净 |
| 数据库兼容 | Migration、fixture 范围与实现审查 | `PASS`——阶段 B 不新增 migration；Alembic 保持 `0007_media_server_operations`，复用既有 author target、author/Job subject、`result_summary` 与 `operation_phase_changed` vocabulary。PostgreSQL fixture 只创建生产 Operation/Event/Subject/StreamState 四张 metadata 表，不声明全 schema 或部署支持 |
| Git 发布 | 本次收尾修改前比较本地 `HEAD` 与 `origin/main` | `PASS`——两者均为 `d8bbdf7971e879f48f9e2dc57dd2973fd42ed260`；`.mimosa/` 保持未跟踪并被排除 |
| 真实媒体服务器资格 | 获授权 Emby/Jellyfin 执行 | `NOT_RUN`——没有使用真实媒体服务器 origin、Library、credential、精确 item lookup 或刷新后 observation；本地/mock 证据不授予真人 PASS |

阶段 B 的 focused selection 与完整 2763 项套件有重叠，不得相加。PostgreSQL 首次开发诊断 10 项为 7 PASS/3 FAIL，暴露普通取消与 shutdown 在等待锁前读取旧 revision；加入权威 `require_for_update()` 读取后，扩展矩阵最终 11/11 PASS。首次生产 build 失败与串行 PASS 是两个独立事实：前端命令共享 `.svelte-kit` 状态，有效门禁是无重叠重跑。本轮没有单独执行阶段 B 浏览器 smoke，因此阶段 B 不声明浏览器交互证据。

## 需求证据

| 需求 | 已验证证据 |
| --- | --- |
| 安全受管树权威 | 测试要求作者 UUID、唯一成功 `export.emby` 数据库前驱链 head 及其精确严格 manifest 身份；调用方路径与单独磁盘 manifest 均无权威 |
| 有界只读检查 | Existing-only 作者锁、进程 single-flight、最多 128 个文件、已配置字节/截止时间预算及 manifest-bound HMAC cursor 均有覆盖；非零末页保持 page scope；读取不修复、不删除，也不创建目录/锁 |
| 跨平台身份与漂移 | POSIX 描述符相对 no-follow 遍历与 Windows no-delete-share 句柄覆盖祖先、manifest 和文件替换；描述符/名称身份、普通文件及单硬链接检查关闭失败；新鲜度与完整性彼此独立，包括正常 `blocked` 新鲜度 |
| 安全不可变配置 | 全有或全无启动校验只接受一个规范 Emby/Jellyfin 配置；API 投影省略 key、完整 secret reference、Library ID、服务器路径与网络范围；校验错误隐藏被拒绝值 |
| 网络与凭据边界 | 每个 DNS 答案都必须匹配已配置 CIDR；连接 IP 固定并保留原 Host/SNI；代理和重定向被禁用；key 只在请求入口解析，请求作用域脱敏覆盖动态依赖 logger |
| 精确 probe/刷新协议 | Probe 只用 `GET /System/Info` 与 `GET /Library/VirtualFolders`；精确 ID/path 发现后，scan 只用固定 `POST /Items/{ItemId}/Refresh`；不存在全局刷新回退或 POST 重试 |
| Dispatch 与取消真实性 | Transport-entry gate 是 dispatch 边界；dispatch 前取消/截止不发送 POST；entry 后、可信 2xx 前的歧义不可重试并记 acceptance-unknown。author 模式在可信 2xx 后持久保存 accepted 证据，后续观察歧义不可重试并记 completion-unknown；锁定的 accepted/observed checkpoint 给出确定 cancel/final 结果。author row 按 phase 重启恢复，legacy targetless `{}` 保留历史保守对账 |
| 持久 API 与 migration | Revision `0007` 增加两个封闭 kind，downgrade 不删除审计证据；targetless 幂等 Operation、当前配置证据、payload 白名单、API 覆盖拒绝及支持包安全均有覆盖 |
| 精确作者 item lookup | 当前唯一成功 publication head 与严格 manifest 是唯一 selector 权威；Emby 有文档过滤与 Jellyfin 有界完整分页最终都执行本地 provider/path 精确相等与唯一性核验，未完成遍历绝不成为 `not_found` |
| 刷新后 observation | Legacy `{}` 保持 targetless acceptance-only；严格作者模式只在 absent baseline 后至多发送一次 provider-specific POST，持久保存 accepted/observed checkpoint，并且只有间隔后连续两次观察到同一唯一 item 才成功；重启、取消与最终竞态保留最后一个权威事实 |
| 资格真实性 | Schema v2 分开自动化证据、实现状态与真人状态；probe、discovery、targeted acceptance、item lookup 与 post-refresh observation 为 `IMPLEMENTED`、真人 `NOT_RUN`；provider task completion 为 `NOT_IMPLEMENTED / provider_api_unsupported`；playback 与自动联动保持 `NOT_IMPLEMENTED`、真人状态为空 |
| Web 行为 | 单测覆盖媒体树分页、安全配置、资格、持久动作、请求代际隔离、Settings 故障隔离、不重叠 Jobs 轮询、严格 `{}`/作者请求、安全 lookup、固定真值文案及作者观察无百分比 |

## 证据政策与剩余门

本轮没有使用真实平台账户、作者 endpoint、平台 API/CDN、下载的作者媒体、Linux 持久性/备份/进程演练或真实 Emby/Jellyfin 服务器。本地树、mock transport 与 API/Web 测试只证明冻结的实现契约。

真实连接探测、Library 发现、定向刷新接受、item lookup 与刷新后 item observation，在执行 0047 记录获授权服务器证据前继续为 `NOT_RUN`。Provider task completion 因 `provider_api_unsupported` 保持 `NOT_IMPLEMENTED`；刷新已接受或 item 已观察都不改变该事实。经鉴权播放证据写入与可写/破坏性运维面继续归 0055。导出后自动扫描是 `NOT_IMPLEMENTED`，尚无冻结的后续归属。这些边界防止本地或 mock 成功被写成虚假真人资格。
