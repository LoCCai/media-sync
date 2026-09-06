[English](verification.md) | **中文**

# 验证记录

实现 revision：`165516a`（`feat(crawler): 接通原生会话与订阅`）。计划基线：`0b90aaa`。

## 最终结果

| 门禁 | 结果 | 证据与边界 |
| --- | --- | --- |
| 认领/WebUI/API 专项 | `PASS` | 六文件联合：`83 passed, 1 warning in 19.37s`。覆盖严格 API schema、操作者认证/CSRF、安全公开错误、WebUI busy gate、复制/探针/替换/回滚、repository CAS、来源保留及知乎 child 兼容。warning 是既有 Starlette TestClient/httpx 弃用提示。 |
| 已认领 profile → scheduler | `PASS` | `1 passed, 59 deselected in 1.57s`。精确 Account profile 以 `saved_session` 进入 BridgeRequest 与 process spec；未解析 Cookie；同步 Job 与规范化摄取成功。 |
| 既有交付/NFO 回归 | `PASS` | 精确订阅交付、平台输出目录与 Emby export contract 联合 `83 passed, 1 warning in 40.78s`；这些测试不要求配置媒体服务器 provider。 |
| Python 完整 unit 套件 | `PASS` | 最终运行：`4683 passed, 3 skipped, 1 warning in 587.55s`。三个跳过是既有 Windows/POSIX 资格分支；warning 是既有 TestClient 弃用提示。 |
| 已修正的测试失败 | `FIXED` | 第一次完整运行得到 `4682 passed, 3 skipped` 和一个失败，原因是默认拒绝鉴权测试仍断言 77 条路由。新增受保护认领路由后实际为 78；更新精确数量/名称后，鉴权联合 49 项及上面的完整套件均通过。 |
| media-sync Web 完整套件 | `PASS` | `26 files / 799 tests` 全部通过。 |
| Svelte/生产 Web 构建 | `PASS` | `svelte-check` 为 0 error、0 warning；Vite 转换 4,086 个 server module 与 4,095 个 client module，并产出静态构建。 |
| 前端格式 | `PASS` | 全仓 Prettier 检查报告全部文件已格式化。 |
| Python lint/format/type | `PASS` | `src tests` Ruff check 通过；Ruff format 报告 396 个文件已格式化；strict mypy 对 154 个源码文件无问题。 |
| 锁定上游 | `PASS` | `scripts/check_upstreams.py` 验证两个锁定 checkout。MediaCrawler 重新 `git fetch origin main` 后仍解析到相同锁定/最新 SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`；未修改 `.upstream`。 |
| Python 打包 | `PASS` | `uv build` 在临时目录从 sdist 构建 `media_sync-0.1.0.tar.gz` 与 `media_sync-0.1.0-py3-none-any.whl`；两个新增认领模块都存在于制品中。 |
| 文档链接/空白 | `PASS` | `scripts/check_docs.py`：`Documentation links OK (738 Markdown files checked).` 文档提交前的 `git diff --check` 也通过。 |
| `165516a` Docker 镜像 | `NOT_RUN` | 本工作站无 Docker，不声明本地镜像/运行时结果。 |
| 历史线上 0072 `/crawler/` | 已观察配置门 | 部署 `165516a` 之前，操作者在既有镜像观察到 `license_acknowledgement_required`。这证明该 API 许可证门关闭，不表示原生控制台或平台登录失败；它不能赋予 0073 镜像资格，修正配置后的访问仍为 `NOT_RUN`。 |
| 真人 QR/Cookie 认领与平台采集 | `NOT_RUN` | 本地实现验证没有使用平台凭据或真人 crawler。 |
| 真人 CDN 字节、历史完整性、后续增量 | `NOT_RUN` | 离线 fixture 不能赋予这些行为资格。 |
| Emby/Jellyfin 服务器扫描/播放 | `NOT_RUN` / 可选 | 目录/NFO 生成独立于服务器连接；本轮未连接服务器。 |

## 已执行命令

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_api_mediacrawler_webui.py tests/unit/test_mediacrawler_webui_license_gate.py tests/unit/test_mediacrawler_webui.py tests/unit/test_mediacrawler_webui_child.py tests/unit/test_mediacrawler_profile_adoption_contract.py tests/integration/test_mediacrawler_profile_adoption.py -q
.\.venv\Scripts\python.exe -m pytest tests/integration/test_mediacrawler_scheduler_handler.py -k "adopted_webui_profile_is_the_exact_profile_used_by_scheduler" -q
.\.venv\Scripts\python.exe -m pytest tests/integration/test_exact_subscription_delivery.py tests/integration/test_pipeline_output_directories.py tests/contract/test_emby_export_contract.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/unit/test_operator_auth_api.py tests/unit/test_api_mediacrawler_webui.py -q

pnpm --dir web test
pnpm --dir web run check
pnpm --dir web run build
pnpm --dir web run format:check

.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m mypy --strict src/media_sync
.\.venv\Scripts\python.exe scripts/check_upstreams.py
.\.venv\Scripts\python.exe scripts/check_docs.py
git diff --check
uv build --out-dir <temporary-directory>
```

## 资格结论

确定性实现接缝已经通过：原生 WebUI profile 快照 → saved-session 验证 → Account 发布 → scheduler 选择精确 profile。这不等于真人平台登录或下载通过。下一份权威证据必须来自重新构建的 Linux 部署，先修正 API 许可证环境，再执行一个有界 Subscription 金丝雀。
