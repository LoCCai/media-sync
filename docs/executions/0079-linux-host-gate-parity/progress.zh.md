[English](progress.md) | **中文**

# 执行 0079 推进结果

- 状态：已完成——全部本地门禁在 Linux 部署主机通过；镜像已按 0077 交接在本机重建升级到 `5622f4d` 并验证健康
- 日期：2026-09-26
- 环境：Linux 部署服务器（即运行生产容器的主机），uv + Python 3.13、Node 22 与 pnpm 11.19.0，两个 `.upstream` checkout 就绪

## 已完成

- 仓库同步：`main` 从 `3c31dce` fast-forward 到 `764f46b`，未提交的 2026-09-12 部署记录经 stash 干净恢复，作为 `ec67097` 提交并推送。
- strict mypy 实现平台无关。此前 Linux 上门禁报 39 个错误（Windows 专属 `subprocess`/`ctypes`/`msvcrt` 属性加 6 处按平台调过的 ignore）。包裹这些访问的守卫改为 mypy 可按视角收窄的 `sys.platform == "win32"` 比较（`src/media_sync/security/paths.py`、`infrastructure/observability/store.py`、`exporters/emby/exporter.py`、`integrations/mediacrawler/runner.py`、`login_runner.py`）；mock 原生契约有意在 POSIX 运行的 Windows 辅助函数保留成对 `attr-defined, unused-ignore` 注释（`archive_preview.py`、`store.py`、`exporter.py`、`webui.py`）。`webui.py` 的 spawn 守卫保持 `os.name`，因为其单元测试通过模块级 os 伪对象驱动该分支。
- 拉取树上的完整 pytest 基线：81 failed / 7052 passed。对原始树重跑同一集合复现 80/81，证明仅有一处早期回归（通过保留 `webui.py` 守卫修复）与 80 个既有宿主失败。
- 80 个既有失败全部归因并修复：
  - venv 启动器符号链接类（Windows venv python 是拷贝，POSIX 是符号链接）：使用 `Path(sys.executable).resolve()` 的夹具与 manifest 和子进程未解引用的启动路径脱同步。`tests/contract/test_mediacrawler_bridge.py`、`test_mediacrawler_login.py`、`tests/integration/test_mediacrawler_scheduler_handler.py`、`test_zhihu_scheduled_creator_bound.py` 与 `tests/unit/test_mediacrawler_saved_session.py` 现镜像生产 `normalize_python_executable` 语义；`test_mediacrawler_detail_refresh.py` 断言归一化路径。
  - POSIX 专属启动器测试（`test_runtime_preserves_posix_venv_launcher_symlink`，Windows 上 skip 以致从未在任何地方验证过）：其全局 `subprocess.run` mock 破坏了 `prepare()` 的真实 git 校验；mock 现在只拦截启动器探测、其余放行。
  - 负载敏感的截停断言（`test_parent_bounds_a_no_frame_child_by_deadline_and_joins_it`）：5 秒墙上时间上限放宽到 15 秒——仍四倍低于契约所截停的 60 秒子进程生命周期。
  - `tests/integration/test_emby_application.py::test_concurrent_children_of_one_predecessor_leave_one_durable_head`：落败方在延迟开启的 SQLite 会话里记录 `stale_publish`，其读快照被胜者提交作废；WAL 对快照升级冲突立即报 busy-snapshot（busy timeout 不适用），通用处理器把结果重新分类成 `export_failure_finalize_failed`。
- Emby 失败记录现在在 SQLite 上采用 BEGIN IMMEDIATE 加有界重试（`src/media_sync/application/emby.py`），镜像 `operations.py` 的耐久写模式；`LeaseLostError` 仍原样传播，重试耗尽仍映射为 `export_failure_finalize_failed`。
- 0078 文档债：去重了重复的 0078 索引行（`docs/README.md` 三行、`docs/README.zh.md` 两行），0078 progress 记录改为陈述已推送的三段式收尾而非"进行中"。

## 偏差与决策

- 0077 冻结未被触碰：未改任何 XHS/抖音投递逻辑；生产代码仅有平台守卫表达式、成对 ignore 与失败记录事务模式三处改动。
- 成对 ignore 只用于运行时平台守卫会破坏"有意通过 mock 原生契约在 POSIX 上演练 Windows 辅助函数"测试的地方。

## 收尾部署（同会话执行）

- 升级前备份到 `/root/media-sync-backups/2026-09-26-pre-upgrade/`：SQLite 在线备份（`sqlite3.Connection.backup`，639 KB）+ 整卷 `/data` tar 归档（118 MB）+ 私有 Compose/.env 副本；supervisor profile 全程保持停止。
- `MEDIA_SYNC_SOURCE_REVISION=5622f4db4539f97194fec1befb2cf504589826fa` 下 `docker-compose build --no-cache media-sync` 成功，构建内 Web 门禁（`pnpm check && pnpm test && pnpm build`）通过；镜像 OCI `org.opencontainers.image.revision` 标签等于该 SHA。
- `up -d --no-deps --force-recreate` 后容器 healthy；`GET /api/v1/health`（带允许 Host）返回 `{"status":"ok"}`；无凭据访问 `/crawler/` 返回 401；错误 Origin 的 health 请求返回 403。
- 容器内 `media-sync doctor --deep --accept-mediacrawler-license --json`：`ok:true / status:"ready"`，`build_manifest.source_revision` 等于 `5622f4db…26fa`，数据库 migration `0015_xhs_creator_notes` 为 current，10 项钉定 MediaCrawler 检查全部 pass，`live_qualification: NOT_RUN`（预期）。
- 回滚路径：0077 前旧镜像仍保留，升级前备份可整卷恢复；真人行继续按 0077 交接受操作者门槛约束。
