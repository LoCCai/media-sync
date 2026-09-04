[English](verification.md) | **中文**

# 执行 0005 验证

- 验证日期：2026-08-30 10:45 +08:00
- 网络与账户策略：仅离线 mock transport 与生成文件
- 结果：完整离线范围通过

## 行为证据

根任务收尾实际运行了全量测试及下列全部专项门禁。所有行为范围均通过；准确总数与耗时记录在质量门禁表中。

| 范围 | 命令或证据 | 最终状态 |
| --- | --- | --- |
| 资产身份、重放与数据库生命周期 | `tests/integration/test_database.py`, `tests/integration/test_sync_pipeline.py`, `tests/integration/test_mediacrawler_db_ingestion.py` | 通过 |
| legacy 迁移回填与降级/再升级身份清理 | `tests/integration/test_packaged_migrations.py` | 通过 |
| locator 与网络边界 | `tests/unit/test_media_locator.py tests/unit/test_media_network.py` | 通过 |
| 续传、限制、探测与归档 | `tests/unit/test_media_downloader.py tests/unit/test_media_probe.py` | 通过 |
| 下载锁与 scope、租约回收及收尾恢复 | `tests/unit/test_download_application.py tests/integration/test_asset_download_orchestration.py` | 通过 |
| Emby 布局、可信 predecessor 与文件事务 | `tests/unit/test_emby_layout.py tests/contract/test_emby_export_contract.py` | 通过 |
| 数据库发布链、intent/result 与空快照/并发恢复 | `tests/integration/test_emby_application.py` | 通过 |
| 统一离线流水线 | `tests/integration/test_offline_media_pipeline.py` | 通过 |
| CLI 行为 | `tests/unit/test_cli.py` | 通过 |
| 组合密钥键与凭据路径落点 | 测试及最终哨兵扫描 | 通过 |

## 最终质量门禁

| 检查 | 最终准确命令 | 状态与证据 |
| --- | --- | --- |
| 锁定依赖 | `uv sync --all-groups --locked` | 通过 — 解析 58、审计 43 |
| 代码规范 | `uv run ruff check .` | 通过 |
| 格式 | `uv run ruff format --check .` | 通过 — 127 个文件 |
| 严格类型 | `uv run mypy src/media_sync` | 通过 — 57 个源码文件 |
| 全量测试与覆盖率 | `uv run pytest --cov=media_sync --cov-report=term` | 通过 — 540 项，126.44 秒；分支感知总覆盖率 79% |
| 资产与下载器专项 | `uv run pytest tests/integration/test_database.py tests/integration/test_sync_pipeline.py tests/integration/test_mediacrawler_db_ingestion.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_media_downloader.py tests/unit/test_media_probe.py tests/unit/test_download_application.py tests/integration/test_asset_download_orchestration.py -q` | 通过 — 165 项，15.12 秒 |
| Emby 与导出专项 | `uv run pytest tests/unit/test_emby_layout.py tests/contract/test_emby_export_contract.py tests/integration/test_emby_application.py tests/integration/test_offline_media_pipeline.py -q` | 通过 — 88 项，34.44 秒 |
| CLI 与密钥专项 | `uv run pytest tests/unit/test_cli.py tests/unit/test_security.py tests/integration/test_secret_sinks.py -q` | 通过 — 132 项，7.06 秒 |
| 构建 | `uv build` | 通过 — 源码包与 wheel |
| 随包迁移 | 包含源码与解包 wheel 检查) | 通过 — 5 项，6.21 秒 |
| 文档链接 | `uv run python scripts/check_docs.py` | 通过 — 36 个 Markdown 文件 |
| 锁定上游 | `uv run python scripts/check_upstreams.py` | 通过 — 2 个锁定 checkout |
| 补丁空白 | `git diff --check` | 通过 — 无输出 |
| 定向密钥哨兵行为 | `uv run pytest tests/integration/test_secret_sinks.py tests/integration/test_emby_application.py::test_export_omits_raw_locator_and_signed_url_sentinel tests/integration/test_asset_download_orchestration.py::test_transport_exception_sentinel_never_reaches_error_or_persistence -q` | 通过 — 8 项，1.37 秒 |
| 最终产物密钥哨兵 | 下方可复现保留产物门禁 | 通过 — 7 项；两次字节扫描均零匹配 |
| 运行产物未跟踪 | `git ls-files -- archive exports jobs .media-sync dist` and `git status --short -- archive exports jobs .media-sync dist` | 通过 — 均无跟踪或限定状态输出；保留门禁根目录已忽略 |

## 保留产物哨兵门禁

根任务收尾把全部生成证据保留在 `.media-sync/verification/0005-final-sentinel-root` 下，其中包含 6 个 SQLite、1 个不可变归档树、1 个 Emby `library` 导出树及捕获的 pytest/运维输出，共 21 个文件、29 个目录、1,326,956 字节。未访问真实平台、CDN 或 Emby 服务。

```powershell
$verificationRoot = Join-Path $PWD '.media-sync\verification\0005-final-sentinel-root'
$pytestRoot = Join-Path $verificationRoot 'pytest-artifacts'
$outputPath = Join-Path $verificationRoot 'pytest-output.txt'
if (Test-Path -LiteralPath $verificationRoot) { throw "Verification root unexpectedly exists: $verificationRoot" }
New-Item -ItemType Directory -Path $verificationRoot | Out-Null
$started = Get-Date
uv run pytest tests/integration/test_secret_sinks.py tests/integration/test_offline_media_pipeline.py -q --basetemp $pytestRoot 2>&1 | Tee-Object -FilePath $outputPath
$pytestExit = $LASTEXITCODE
$elapsed = (Get-Date) - $started
if ($pytestExit -ne 0) { throw 'Sentinel tests failed' }
rg -a -F -- 'SENTINEL-runtime-signed-query-0005' $verificationRoot
$runtimeScanExit = $LASTEXITCODE
rg -a -F -- 'sentinel-secret-value' $verificationRoot
$secretSinkScanExit = $LASTEXITCODE
if ($runtimeScanExit -ne 1 -or $secretSinkScanExit -ne 1) { throw 'Sentinel scan matched or failed' }
git check-ignore -v -- .media-sync/verification/0005-final-sentinel-root
git status --short --untracked-files=all -- .media-sync/verification/0005-final-sentinel-root
git ls-files -- .media-sync/verification/0005-final-sentinel-root
```

实测结果：

```text
7 passed in 1.60s
pytest_exit=0
elapsed_seconds=2.49
runtime_scan_exit=1
secret_sink_scan_exit=1
.gitignore:31:.media-sync/  .media-sync/verification/0005-final-sentinel-root
```

对 `rg` 而言，退出码 `1` 表示扫描成功且零匹配；`0` 才表示发生泄漏，`2+` 表示扫描失败。限定目录的 `git status` 与 `git ls-files` 均无输出。因此保留的 SQLite/归档/导出根目录及捕获输出不含任一精确哨兵，也未被 Git 跟踪。

## 必须得到的行为结论

- 发现重放保留下载器拥有的已验证字节；语义替换只执行一次显式且带 fencing 的 generation reset。
- 字段完整的 legacy verified 行在 `0003` 后继续可用；瞬时或不完整的 legacy 下载器状态会安全重置，并记录 `legacy_asset_reset`。
- `0003` downgrade 会清空所有资产下载 FK 及 generation-bound `asset_download` Job，再 upgrade 后可以重新创建相同 generation 的 natural identity。已成功 Emby 链状态与结构严格有效的封闭发布 intent 恢复状态会保留；其他未成功 Emby Job/record 不得污染下一次导出。
- 同一 work-root 的资产锁从数据库变更前持有到收尾。锁竞争和 I/O scope 不匹配不消耗 attempt，也不改变 job 或资产；持久 scope 指纹不泄露本地路径。
- 网络工作不持有 SQLite 事务；旧租约/generation 所有者不能验证资产。精确且已到期但未被 reclaim 的 token 可以续期，但 renew 与 reclaim 只有一个 CAS 胜者。
- 每次重定向和解析地址都被验证；续传/重启不会追加不兼容字节。
- 音视频缺少有界 `ffprobe` 结构证据时不能进入 verified。
- 归档所有权 guard 位于复制/fsync/重哈希之后及提交前，复用既有 blob 也必须执行。归档 blob 不可变且按内容寻址；操作时已存在的路径/链接违规及可检测的叶节点身份替换默认拒绝。运行根目录及祖先是操作员控制的可信边界；同权限恶意进程替换父目录不在 0.x 威胁模型内。
- 文件系统已提交、数据库收尾失败时，可以凭精确的 generation-bound 证据恢复，不访问网络、不增加 attempt。`.part` 只在原子验证成功后清理，且清理不能反转成功。
- succeeded `export.emby` Job result，而非仅从磁盘发现的 manifest，锚定 publication scope、source/tree/manifest 哈希、受管数量及精确 predecessor。唯一 Job 链拒绝分叉/环/断裂祖先，并支持 `A → B → A`。
- 首次发布拒绝意外 managed manifest；自洽伪造 manifest 不能认领非受管用户文件。already-exported 重放会复核数据库锚定的 manifest 身份与每个受管字节。
- 发布前 Job intent 支持精确的“文件系统发布成功、数据库收尾失败”恢复。空快照即使没有 ExportRecord 仍有锚点；并发 sibling 发布只留下一个胜者和一个可重试 stale loser。
- 重复 Emby 导出逐字节确定；返回成功前，journaled 发布会在作者锁与恢复证据仍保留时复核全部 desired 受管文件及 manifest。中断事务的 roll-forward 采用同样的完整树规则；不匹配时保留 journal 与 `RECOVERY_REQUIRED`。并发或用户修改的目标/manifest 文件不会被静默覆盖或删除，回滚路径同样如此。
- 组合 API/access-key 映射名会在 snake_case、kebab-case、camelCase 及带提供商前缀的形式下脱敏，但不会删除普通 `key`、`public_key` 或 `key_id` 值。带凭据标记的 URL 路径会以原始、编码及双重编码形式被移除，且会被 `direct` 与 source-hint 派生拒绝；当前导入与 `0003` legacy 回填均把它转换为不含密钥的 `adapter_refresh` 状态。注入值不会残留在 SQLite 字节、归档/导出树或运维错误中。经过脱敏的非机密 raw envelope 会按设计保存在 SQLite 供重新归一化，但 raw envelope 与 locator 绝不进入导出树。
- refresh 不支持或缺少强制 probe 时，CLI preflight 返回 `blocked`/`not_started` 与未改变的 `persisted_status`，不创建 Job、不修改 Asset。

## 线上资格验证

| 目标 | 状态 | 原因 |
| --- | --- | --- |
| 七平台二维码、Cookie、保存会话登录及作者同步 | `NOT_RUN` | 未使用用户授权账户，也未进行真人交互挑战 |
| 七平台签名 locator 刷新与真实 CDN 下载 | `NOT_RUN` | 未授权 CDN 流量；MediaCrawler refresh 尚未实现 |
| Emby/Jellyfin 重扫与播放 | `NOT_RUN` | 未启动或修改服务器 |

自动下载器与导出测试不得提升这些行的状态。

手机号登录对外能力、MediaCrawler refresh、平台特有 DASH/多 P/字幕/弹幕或幻灯片/mux 衍生物、调度/限流/退避、REST 运维、Docker 与生产运维属于不可用或延期实现范围，而不是 `NOT_RUN` 验收结果。
