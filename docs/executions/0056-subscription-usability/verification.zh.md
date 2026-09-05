[English](verification.md) | **中文**

# 验证记录

日期：2026-09-05。源码基线为干净且已发布的 `0eefea7`，冻结计划为 `fe54aba`。下列测试均用隔离本地数据库和合成记录，不是生产环境。

## 已完成检查

下列命令使用 `.venv/Scripts/python.exe`；删除代理使用同一锁定环境中等价的 `uv run pytest`。

| 检查 | 命令 / 选集 | 结果 |
| --- | --- | --- |
| 本地输出不依赖 connector | `-m pytest tests/unit/test_api_local_export_without_media_server.py -q` | 2 项通过；真实鉴权 API 和导出器，connector 构造陷阱未触发，仍要求 verified 文件 |
| 导出回归 | 新本地导出测试及 API library inspection、library application、Emby application 测试 | 64 项通过，19.15 秒 |
| 精确报告 | `-m pytest tests/unit/test_job_diagnostics.py -q` | 修正后首次 14 项通过；后加四项真实 revision/phase/code 用例包含在下面 175 项联合中 |
| API/CLI/auth/report/support | `-m pytest tests/unit/test_job_diagnostics.py tests/unit/test_api_subscription_removal.py tests/unit/test_operator_auth_api.py tests/unit/test_api_server.py tests/unit/test_api_workbench.py tests/unit/test_cli.py tests/unit/test_api_support_bundle.py tests/unit/test_support_bundle.py -q --tb=short` | 175 项通过，56.61 秒；62 个路由对象全部按精确匿名白名单检查 |
| 删除和迁移 | `tests/integration/test_subscription_removal.py tests/integration/test_subscription_removal_migration.py` | 50 项通过，6.10 秒：46 项生命周期/锁测试和四项迁移 |
| 后端回归 | `tests/unit/test_workbench.py tests/integration/test_scheduler_worker.py tests/integration/test_scheduler_repository.py tests/integration/test_pipeline_worker.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_subscription_removal.py tests/integration/test_subscription_removal_migration.py tests/integration/test_playback_evidence_migration.py` | 250 项通过，24.35 秒 |
| 最终串行 Web 门 | 在 `web/`：`pnpm test`、`pnpm check`、`pnpm format:check`、`pnpm build` | 440 项 / 18 文件；Svelte 零错误/警告；格式和静态构建通过。最后 Library 文案改动后，`pnpm test -- src/lib/utils/local-export-independence.test.ts` 实际重跑了全部 440 项（20:41:15 UTC+8）；格式/check/build 再次通过 |
| Python 静态 | `-m ruff check .`、`-m ruff format --check .`、`-m mypy src/media_sync`、`-m compileall -q src tests` | 通过；847 个格式文件，112 个类型检查源码文件 |
| 文档/上游 | `scripts/check_docs.py`、`scripts/check_upstreams.py`、`git diff --check` | 本检查点 580 份 Markdown、两个锁定上游通过，无空白错误 |
| 打包 | `uv build --out-dir <新系统临时目录>` | wheel 131 项 / sdist 948 项；包含新服务、迁移和 Web 源码。文件名检查未发现私密 .env、SQLite 数据库、密钥文件、上游 checkout 或 node_modules；不冒称穷尽的秘密内容扫描 |

首次完整离线套件（`-m pytest -q --tb=short`）完成：**2 项失败、3800 项通过、29 项跳过**，一项既有警告，749.87 秒。发现新增墓碑预读引入的真实 SQLite 检查点读转写升级竞争，以及旧 schema 迁移 fixture 错用最新版 Subscription ORM。两项已按下文修正并复验，但不能把首次全量称为通过。警告为既有 Starlette/httpx TestClient 弃用提示；跳过为三项 Windows/POSIX 差异、19 项未配置 PostgreSQL 用例、七项缺隔离上游 Pillow 依赖的二维码图像测试。

修后检查点恢复原首条 CAS，将 `deleted_at IS NULL` 纳入同一 UPDATE，仅 CAS 未命中后读取版本/删除状态。旧迁移 fixture 使用历史列，不给旧 schema 增加新列。精确 Job 领取与有订阅作用域的入队，在新增生命周期读取前用无行 UPDATE 获取 SQLite 写者位置。增加六项真实双连接领取/入队并发、两项检查点首写/墓碑测试。最终 database/checkpoint/打包迁移/删除联合 **97 项通过，25.59 秒**，覆盖两项原失败和已构建 wheel 的迁移检查。新并发 fixture 首次漏填必需显示名（两项 fixture 失败 / 十项通过），修正种子后最终通过。

最终修后联合使用 `-m pytest -q --tb=short` 加 [post-fix-tests.txt](post-fix-tests.txt) 中的精确参数，包含全部 unit 及受影响 database/checkpoint/scheduler/pipeline/入库/下载/迁移 integration 测试。结果：**2849 项通过、八项跳过、一项既有警告，287.24 秒**。跳过为七项隔离 Pillow 用例和一项 Windows/POSIX handler 用例。这不是第二次完整套件，局部仓储/fixture 修正后未重跑未改动的上游 contract。修后最终静态检查已通过：Ruff、format（849 文件）、mypy（112 源码文件）、compileall、文档（582 份 Markdown）、上游与空白检查。

## 浏览器冒烟与边界

使用 computer-use 技能及其推荐的浏览器接口，在回环端口 8767 以真实鉴权 API 提供构建后的前端。新建临时数据集，基于 `_console_smoke_fixture.py` 增加一个合成 failed Job/running Run/succeeded Worker 关联和另一个已删除订阅；未使用真实凭据、绕过鉴权，也未请求平台或媒体服务器。

- 正常测试登录和仅浏览引导后进入私有控制台。
- 当前/已删除订阅列表正常加载，已启用与运行中明确区分。删除确认列出保留文件/历史、取消未开始任务、忙碌拒绝；恢复确认说明暂停恢复且不复活任务。两处均取消确认，未提交破坏性 UI 操作；实际生命周期写入由鉴权 API/CLI 测试覆盖。
- Jobs 实际点击获取报告，显示失败 Job、运行中 Run、零计数、一条 Worker 及两类矛盾说明，并目视检查布局。关闭重开后报告清空，需再次主动获取。
- 点击了 JSON 下载按钮，但未验证浏览器下载完成/磁盘字节，也未写剪贴板。序列化、大小/白名单及请求隔离在离线测试中验证，不能称完整剪贴板/下载浏览器验收。
- Library 实际显示独立本地输出与未配置的可选联动。浏览器复核发现仪表盘启用数、Library 英文术语文案问题，均已修正并重建。没有在浏览器提交本地媒体导出。
- 已关闭所建标签页、停止临时服务，并以新监听查询确认 8767 无监听。合成临时数据和打包产物保留在仓库外，未提交。

## 复核与修正过程

- 最初报告测试存在 fixture 专用的错误订阅关键字、重复账户名、缺失 OperationSubject role，已修正；只读断言允许正常 `BEGIN`。未涉及生产数据。
- 独立复核发现旧迁移标识、实际 Worker 阶段及 `scheduler_run_failed` 固定码遗漏，补精确已知值和回归。未知错误/版本继续标未知，不猜测或反射原文。
- 首次 API/CLI 联合为 171 项通过、四项新增 `deleted_at` 闭字段断言失败；更新精确字段集并断言 null 后，最终 175 项通过。
- 首次 Web 401 项通过，但报告 suite 因运行时 alias 导入失败；改相对导入。移除未用 CSS 警告，随后完整门均通过。另补取消文案测试，不以 cancelled 记录证明进程清理。
- 新迁移 fixture 最初遗漏 author 必需时间戳（一项失败 / 66 项通过），修正后四项迁移通过；两处初始后端类型问题已修正。一次错误测试路径命令收集零项，不计验证。
- 独立并发审查发现 PostgreSQL 风格维护路径的 Subscription/Job/Lane 反向锁等待。删除现以 NOWAIT 预锁已有 Job/lane，不懒创建缺失 lane，把精确已锁作用域传入取消/协调；仅精确 SQLSTATE 55P03 在回滚后转固定 `subscription_busy`。SQL 编译和故障注入回滚为离线证据，不是真实 PostgreSQL 并发资格。SQLite 使用 `BEGIN IMMEDIATE`，并有实际竞争线程测试。

## 未跑门与发布

本机没有 Docker CLI，也未配置 PostgreSQL 测试 URL。当前 Docker 构建/部署、真实 PostgreSQL 迁移/并发、生产删除/恢复、真人资料查询/登录/采集/下载/导出/播放均 NOT_RUN。自动昵称/头像仍 NOT_IMPLEMENTED，0056 和总目标保持开放。未改写生产历史，也未恢复 supervisor。

首次 HTTPS fetch 遇 TLS unexpected EOF；改用 Git 的 Schannel TLS 后端与 HTTP/1.1 重试成功，未放宽证书校验。新读取远端 main 仍为 `0eefea7`。包含本记录的实现提交接续计划 `fe54aba`，使用非强制推送并另记远端一致性。上述包检查早于最终文档更新；修后 97 项联合已重建并执行修正版 wheel 的迁移。
