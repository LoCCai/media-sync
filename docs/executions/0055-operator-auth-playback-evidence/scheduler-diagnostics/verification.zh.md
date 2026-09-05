[English](verification.md) | **中文**

# 验证记录

基线：已发布 8b80460；计划 9ec7d8d 及补充 79c2168 在实施前提交。Git 不保存私密部署地址、账户/运行/登录标识或浏览器快照。原始 XML 产物已忽略，实际命令和测量结果记录于此。

## Python 验证

- 主代理投影/API/CLI/Operation/安全联合：`.venv/Scripts/python.exe -m pytest -q tests/unit/test_scheduler_diagnostic_projection.py tests/unit/test_cli.py tests/unit/test_api_server.py tests/unit/test_api_operations.py tests/unit/test_operation_payloads.py tests/integration/test_scheduler_secret_sinks.py tests/integration/test_mediacrawler_security_matrix.py --junitxml=artifacts/scheduler-diagnostics-projection.xml` — **368 项通过**，1 项既有 Starlette/httpx 弃用警告，**68.01 秒**。
- 主代理最终调度联合：`.venv/Scripts/python.exe -m pytest -q tests/unit/test_scheduler_policy.py tests/unit/test_scheduler_handlers.py tests/unit/test_scheduler_supervisor.py tests/integration/test_scheduler_repository.py tests/integration/test_scheduler_worker.py tests/integration/test_scheduler_heartbeat_diagnostics.py tests/integration/test_scheduler_handler_safety.py tests/integration/test_scheduler_supervisor.py tests/integration/test_mediacrawler_scheduler_handler.py --junitxml=artifacts/scheduler-diagnostics-worker.xml` — **269 项通过、1 项跳过，55.75 秒**。跳过为 Windows 不适用的 POSIX venv 符号链接测试，不算平台验证通过。
- 子代理 worker/policy/真实 SQLite 专项：**118 项通过，8.48 秒**。主代理 worker 单文件：**73 项通过，7.37 秒**。独立真实竞争/投影联合：**141 项通过，1.73 秒**。这些重复覆盖，不与主代理数量累加。
- 真实竞争使用文件 WAL 数据库与第二条物理 SQLite 连接持有 BEGIN IMMEDIATE；只有该测试引擎缩短 busy timeout 为 100ms，生产仍为 5000ms。实际 SQLAlchemy 异常具有原生整数 SQLITE_BUSY，心跳在线程执行；handler 取消/等待释放锁后才进行唯一一次收尾。断言失败 Job/running Run/零内容/authenticated 账户以及不保存秘密原文。最终测试连续五次独立通过：**1.40、1.22、1.43、1.32、1.47 秒**。
- 注入用例单独覆盖普通心跳异常、原生扩展 BUSY/LOCKED、错误类型/伪造码/仅文字相似异常、成功 Run 权威、收尾前与实际收尾异常、持续存储故障、租约丢失、普通/清理取消、已完成任务及同时结束。清理隔离异常仍等待进行中的心跳，不取得收尾权威。

## 验证中修正

首次投影子集 233 项通过/1 项失败，因为旧 CLI 断言连新增契约允许的固定许可证码也禁止展示；更新为断言该精确码，保留全部原始秘密/payload 排除，最终 368 项联合通过。新 worker 夹具初期错误使用清理异常构造参数、依赖未排序 RunEvent 行顺序，两处测试假设均修正；修正前已收集的广回归为 266 项通过/1 项失败/1 项跳过，上述最终重跑通过且收集了新增两项取消测试。

真实争用重复运行暴露 Windows monotonic 时钟约 15.625ms 精度导致 100ms 等待测成 93ms；测试改用 perf_counter，未弱化实际持锁/超时断言。独立审查还发现清理隔离异常传播可能跳过 finally 中的心跳等待，现用嵌套 finally 保留等待，并以两项外部取消/进行中心跳组合回归关闭问题。这些中间失败不冒充通过。

## Web 与静态验证

Web 验证于 **UTC+8 19:39:20–19:40:42** 串行运行：专项 `pnpm exec vitest run src/lib/utils/scheduler-job-diagnostics.test.ts src/lib/api/scheduler-job-detail.test.ts src/lib/utils/scheduler-worker-display.test.ts` 通过 **135 项/3 文件**；完整 `pnpm test` 通过 **343 项/15 文件**；`pnpm check` 为 **0 errors/0 warnings**；`pnpm format:check` 和 `pnpm build` 通过。Vite 报告 client 3.15 秒/整体 8.07 秒，仅有插件耗时性能提示。Web 差异空白检查通过，无 Web 失败或重跑。这些属于 helper/请求代际/构建检查，不是渲染页面或已部署浏览器证据。

Python 最终 Ruff check、Ruff format（**259 文件**）、mypy（**110 源码文件**）及 compileall 已通过；两个锁定上游确认未变。文档/链接检查在最终结果文字更新前通过 **572 篇 Markdown**，提交前再运行。新 fetch 确认两项冻结文档提交领先远端/落后为零。独立 service/policy/投影审查已关闭清理等待问题，主代理复核有界 Web 改动及历史错误文案；本诊断切片没有未解决审查发现。

## 证据边界与发布

本有界增量不声明全量 Python、Docker 构建、真实 PostgreSQL、重新打包或渲染浏览器验证通过。生产测试仍 **FAILED**，新部署诊断仍 **NOT_RUN**；真实离线 SQLite 争用和注入复现都不能证明历史生产根因。未修复历史 Run、未执行生产任务、部署、新登录、下载、导出或恢复 supervisor。

实现 **b5b6fd4dd1bc3522e6ce8416371fda988db4db5b** 与两项冻结计划提交已推送 origin/main；重新 fetch 确认两端哈希一致、分歧 **0/0**、工作区干净。该提交前最终 Ruff/format/mypy/compileall、**572 篇文档**链接、两个锁定上游和差异空白检查均通过。此后续纯文档收尾记录发布，不改变运行证据或部署状态。
