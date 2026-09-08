[English](verification.md) | **中文**

# 验证

实现 revision：`47ca107`。计划基线：`295fa2c`。

## 最终结果

| 门禁 | 结果 | 证据与边界 |
| --- | --- | --- |
| XHS cursor/capture/ingestion/delivery 专项 | `PASS` | 初始 XHS 专项通过 `47`；API workbench/精确交付基线通过 `42`，补充固定失败态后为 `49`；间隔/进度为 `26`；capture/delivery/media 为 `14`；全部变更 Python 测试文件为 `462 passed, 2 skipped, 1 warning in 322.43s`；旧 runner 兼容回归为 `45`。这些选择有重叠，不相加。 |
| 已修正 B 站与通用 pipeline 回归 | `PASS` | 最终 B 站续跑文件通过 `106`；真实输出目录 worker 场景通过 `1`，并有一项既有 warning。 |
| Python 完整套件 | `PASS` | `7128 passed, 42 skipped, 1 warning in 1657.69s (0:27:37)`。跳过项为已记录的 Windows/POSIX 差异及未配置真实 PostgreSQL 的验收；warning 为既有 Starlette/httpx 弃用提示。 |
| media-sync Web 完整套件 | `PASS` | `27 files / 820 tests` 通过。 |
| Svelte 与 Web 生产构建 | `PASS` | `svelte-check` 为 0 errors、0 warnings；Vite 转换 4,087 个服务端和 4,096 个客户端模块并写出静态构建。 |
| 前端格式 | `PASS` | Web 全仓 Prettier 检查通过。 |
| Python lint/format/type/compile | `PASS` | Ruff lint 通过；两处机械排版修正后 Ruff format 报告 417 个文件已格式化；strict mypy 通过 160 个源码文件；`src`、`tests`、`scripts` compileall 通过。 |
| 锁文件与上游 | `PASS` | `uv lock --check` 保持 62 个包不变；`scripts/check_upstreams.py` 验证两个锁定 checkout。MediaCrawler 仍钉定为 `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`。 |
| Python 制品 | `PASS` | 新建 797,475 字节 wheel（185 个成员）及 3,184,476 字节 sdist（1,309 个成员）成功。两者均包含 migration `0015` 以及 XHS capture、note、delivery-progress 模块，不含数据库、QA/截图路径或真实 `.env` 文件；已提交的 `.env.example` 按设计保留在 sdist 中。 |
| 文档链接/空白 | `PASS` | `scripts/check_docs.py` 成功检查 764 个 Markdown 文件；最终 `git diff --check` 通过。 |
| Docker/Linux、PostgreSQL 与真人服务 | `NOT_RUN` | 未使用 Linux 镜像/容器、真实 PostgreSQL、真人 XHS 登录/API/CDN、宿主归档/媒体库/NFO、进程重启、supervisor 或媒体服务器。 |

## 已修正问题

1. 一次早期完整套件发现旧结构 runner fixture 没有定义 `xhs_scan`；改为可选属性读取后，兼容回归通过 `45`。
2. 后续完整运行得到 `7104 passed, 42 skipped, 23 failed, 1 warning in 1616.63s`。其中 22 项共用同一个过期 B 站测试 manifest，缺少新持久化的作者指纹；另一项输出目录失败源于为非 MediaCrawler adapter 无条件解析 MediaCrawler 策略。生产解析已收窄到正确 adapter，来源 fixture 已补精确字段及篡改覆盖。
3. 最终完整套件前，两组针对性重跑分别通过 `106` 和 `1`。任何失败运行都没有被写成通过。
4. 完整运行前的复核还修正了精确 API 成功误报、零间隔语义及 child 侧部分归一化。

## 执行命令

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_bili_scan_continuation.py -q
.\.venv\Scripts\python.exe -m pytest tests/integration/test_pipeline_output_directories.py::test_api_save_is_seen_by_existing_and_independent_workers_and_library_inspection -q

pnpm --dir web run format:check
pnpm --dir web test
pnpm --dir web run check
pnpm --dir web run build

.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m ruff format --check src tests scripts
.\.venv\Scripts\python.exe -m mypy --strict src/media_sync
.\.venv\Scripts\python.exe -m compileall -q src tests scripts
uv lock --check
.\.venv\Scripts\python.exe scripts/check_upstreams.py
.\.venv\Scripts\python.exe scripts/check_docs.py
git diff --check
uv build --out-dir <temporary-directory>
```

## 资格结论

本地 XHS 创作者笔记路径已对页尾保留、不透明 cursor 回放、新 token 详情门禁、独立阻塞/部分状态、精确 Run 内容交付、源末尾对账、增量零工作重放及封闭公开投影取得资格。这仍是确定性离线证据。源末尾证据是有时间边界的观察，不是永久历史完整性；任何真人或部署结果都不能从旧版本继承。
