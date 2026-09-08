[English](verification.md) | **中文**

# 验证

实现 revision：`d6db86a`。计划 revision：`dadd198`。

## 最终结果

| 门禁 | 结果 | 证据与边界 |
| --- | --- | --- |
| 来源/API/CLI 专项 | `PASS` | 完整来源测试文件加精确 deep-readiness API 投影得到 `13 passed, 1 warning in 2.35s`。最终 doctor 专项选择通过 `18`；通过与阻塞两种 deep CLI 路径都输出共享报告、传递显式许可证确认，并返回预期退出状态。 |
| Python 完整套件 | `PASS` | `7140 passed, 42 skipped, 1 warning in 1379.51s (0:22:59)`。跳过项是已记录的 Windows/POSIX 差异及未配置真实 PostgreSQL 的资格测试；警告是既有 Starlette/httpx 弃用提示。 |
| media-sync Web 完整套件 | `PASS` | `28 files / 825 tests` 通过；新增部署证据投影单独通过 `1 file / 5 tests`。 |
| Svelte 与生产 Web 构建 | `PASS` | `svelte-check` 为 0 错误、0 警告；Vite 转换 4,088 个服务端模块与 4,097 个客户端模块，并写出静态构建。 |
| 前端格式 | `PASS` | 仓库 Web Prettier 检查通过，覆盖 Svelte 页面、TypeScript 投影及测试。 |
| Python lint/format/type/compile | `PASS` | Ruff lint 通过；Ruff format 报告 1,186 个文件已格式化；strict mypy 通过 160 个源码文件；`src`、`tests`、`scripts` compileall 通过。 |
| 锁文件与上游 | `PASS` | `uv lock --check` 保持 62 个包不变；`scripts/check_upstreams.py` 验证两个锁定 checkout。 |
| Python 制品 | `PASS` | 新建 798,181 字节 wheel（185 个成员）及 3,197,365 字节 sdist（1,316 个成员）成功。二者都包含 migration `0015` 与当前 CLI，且不含项目 Git 元数据、`.mimosa`、运行时 archive/export/job/log 根、数据库或 partial 文件。 |
| Docker/Compose 契约 | `PASS` / `NOT_RUN` | 单元/静态检查覆盖源码参数、封闭校验、清单行、OCI 标签、Compose 透传及根 `.git` 排除；Prettier 已解析 Compose YAML。当前工作站未安装 Docker，因此 Dockerfile 执行、构建后标签读取与 Linux runtime 行为仍为 `NOT_RUN`。 |
| 文档链接/空白 | `PASS` | `scripts/check_docs.py` 成功检查 774 个 Markdown 文件；最终 `git diff --check` 通过。 |
| 部署、PostgreSQL 与真人服务 | `NOT_RUN` | 未修改服务器/容器，未使用真实 PostgreSQL，未发平台请求，未执行 Subscription、媒体下载、宿主媒体库读取、重启或 supervisor 控制。 |

## 收尾期间修正的问题

1. 最初本地实现缺少计划中 API/supervisor 比较的 CLI 一半。`doctor --deep` 现在直接调用 `collect_deep_readiness_report`；专项测试证明相同载荷及成功/阻塞两种退出状态。
2. 第一版 CLI 补丁复用了普通 `report` 变量，使推断类型过宽；strict mypy 拒绝了后续五处访问。改用独立 `deep_report` 后修正类型，不改变旧 `doctor --json`。
3. 发现 CLI 缺口后主动中止第一轮 Python 完整套件；类型修正后又立即中止下一轮。两个部分运行均不计作最终证据，只有上表中的最终源码干净运行控制状态。

## 资格边界

- 先前线上观察只证明公开 health/readiness，以及字段不符合 0076 的已认证界面；它不能识别运行提交。本次离线实现不会提升任何线上状态。
- 有效源码 SHA 只识别构建输入；它不证明 checkout 干净、持久挂载正确、数据库当前、上游 runtime 合格或平台流量成功。这些仍是独立检查。
- `live_qualification` 继续为 `NOT_RUN`。任何 XHS 金丝雀前，先在 supervisor 停止状态按[部署交接](deployment-handoff.zh.md)执行。
