[English](verification.md) | **中文**

# 执行 0053 验证

- 状态：已完成；冻结实现、仓库与发布证据均通过
- 收尾日期：2026-09-05
- 基线：`be26cc7`
- 计划提交：`66e18ff`
- 数据库 migration：无

## 自动化证据

| 检查 | 过程 | 结果 |
| --- | --- | --- |
| Git 同步 | 实现核对前执行 `git fetch --prune origin` 与 `git pull --ff-only origin main` | `PASS` — 远端无待合入提交；本地 `main` 只领先一个计划提交 |
| Explorer/归档/API 专项 | 安全路径、归档预览、内容/资产 explorer、API explorer 与既有 API server 测试 | `PASS` — 228 项通过；一项既有 Starlette/httpx 弃用 warning |
| 后端独立审查 | 复现 Windows 改写探针并复核首轮全部 P1/P2 修复 | `PASS` — 六项 P1 与四项 P2 已关闭；第二轮未发现剩余 P0/P1/P2 |
| Web 独立审查 | 检查同路由导航、弹窗无障碍与服务端授权动作，再复核修复 | `PASS` — 两项 P1 与一项 P2 已修复，并吸收 canonical-link 导航加固 |
| Web 单测 | `npm --prefix web test -- --run` | `PASS` — 5 个文件、50 项测试 |
| Web 格式 | `npm --prefix web run format:check` | `PASS` |
| Svelte/TypeScript | `npm --prefix web run check` | `PASS` — 0 error、0 warning |
| 静态生产构建 | `npm --prefix web run build` | `PASS` — adapter-static 构建完成 |
| 本地浏览器交互 | 静态构建预览：Assets/Contents scoped URL、同路由链接、Back、导出 Modal、Shift+Tab/Tab 与 Escape | `PASS` — query 状态正确清理/恢复；弹窗焦点进入、环绕并返回，背景进入 inert；该 UI-only smoke 刻意未启动 API |
| Python 质量 | 全仓 Ruff、Ruff format 与 strict mypy | `PASS` — 199 个 Python 文件格式通过；96 个类型化源码文件通过 |
| 完整 Python 套件 | `uv run --frozen pytest -q -p no:cacheprovider` | `PASS` — 2456 项通过、3 项跳过、1 项既有 warning，耗时 479.63 秒 |
| 编译与分发 | `uv run --frozen python -m compileall -q src tests` 加 `uv build` | `PASS` — compileall 静默通过；构建 `media_sync-0.1.0` wheel 与 sdist |
| 文档与上游 | 收尾编辑后运行 `uv run python scripts/check_docs.py` 与 `uv run python scripts/check_upstreams.py` | `PASS` — 474 份 Markdown 与 2 个锁定 checkout |
| tracked 产物与空白 | 生成/本地状态 denylist、宿主路径扫描与 `git diff --check` | `PASS` — 750 个 tracked 文件，禁入产物与 tracked XML 均为零；真实本机路径为零；保留 11 个有意 provenance/脱敏夹具；diff 干净 |
| Git 推送核对 | 推送包含收尾记录的提交后比较本地 `HEAD`、`origin/main` 与 GitHub `refs/heads/main` | `PASS` — 三方一致；不在文档中嵌入自身 SHA |

专项选择存在重叠，不得相加。每次提交均排除 `.mimosa/`、`.upstream/`、数据库、archive/export/job 运行数据、XML 报告、`node_modules`、`web/build`、`.svelte-kit` 与 `dist`。

## 需求证据

| 需求 | 已验证证据 |
| --- | --- |
| 兼容有界列表 | 测试保留数组响应形状、旧筛选和之前的默认资产排序，同时覆盖可选平台/类型/状态/作者/内容/归档/导出与转义字面搜索筛选 |
| 安全精确详情 | 哨兵测试扫描组合后的列表/详情/媒体库 JSON，证明 raw、locator、源 URL、本地/导出路径、validator、错误正文及签名 query 值均缺失；canonical 链接不含 query/fragment/userinfo、拒绝本地/私网目标并要求与平台匹配的官方域名边界；正文保持纯 JSON 文本 |
| 规范归档权威 | 单元与 HTTP 测试要求 Asset UUID 查询、verified/exported 状态、精确摘要路径、size/SHA 匹配、普通/非链接/单硬链接/只读状态及安全 MIME 回退 |
| 同描述符完整性 | hash、身份验证、Range seek 和流式读取共用一个描述符。测试覆盖描述符/命名身份、size/mtime/ctime 漂移、替换、hash/read/seek 失败、消费者中止及描述符关闭 |
| Windows 不可变读取 | 此前会在旧 ETag 下返回新字节的同长度改写复现现由原生拒绝写/删除共享句柄拦截；预存 writer 会使打开失败，时间戳变更会在首个 yield 前失败 |
| 只读 GET/HEAD | existing-root 路径 helper 绝不调用 `mkdir`；归档根移除竞态不会重建目录。HTTP 测试证明目录/归档读取前后 Asset 元数据不变且 Operation 数量保持零 |
| HTTP Range 正确性 | 完整、前缀、开放尾部与后缀 GET 覆盖 200/206；畸形、多范围与不可满足覆盖 416。先验证资源再评估 Range，强 `If-Range` 门控 206，过期/弱/日期 validator 返回完整 200，HEAD 按 RFC 9110 忽略 Range |
| 安全恢复 | 未就绪、缺失、损坏和不安全情况返回固定 409 代码，且只提供既有持久 `asset-download` POST 链接；路径/错误哨兵不进入响应正文或头 |
| ASGI 生命周期 | 原始 ASGI 测试证明 HEAD 404/409/422 正文为空；注入 response-start 与 body-send 失败证明即使 Starlette 跳过 background，响应层 `finally` 仍会关闭描述符 |
| Web 目录 | 工具、静态与浏览器门覆盖有界确定查询、同路由/后退导航、严格动作派生、精确浏览器安全内联 MIME、详情/恢复行为、键盘焦点约束/恢复弹窗及不依赖 settings/export path；路由源码只用文本插值且不插入 raw HTML |

## 证据口径与剩余外部门

这些门禁未使用真人浏览器账户、作者端点、平台 API/CDN、下载的作者媒体、Linux 持久性/备份/进程演练或 Emby/Jellyfin 服务。全部相关行继续在执行 0047 下保持 `NOT_RUN`。本地归档字节和生产 Web 构建只证明冻结的离线/API/UI 契约。

执行 0054 保留媒体库树及真实 Emby/Jellyfin 连接/扫描/资格；执行 0055 保留鉴权、破坏性动作、保留和孤儿清理；0056 保留最终迁移与发布。
