# Execution 0005 verification / 执行 0005 验证

- Verification date / 验证日期：Pending / 待完成
- Network/account policy / 网络与账户策略：offline mock transports and generated files only / 仅离线 mock transport 与生成文件。

## Pending checks / 待执行验证

| Check / 检查 | Command or evidence / 命令或证据 | Status / 状态 |
| --- | --- | --- |
| Locked dependencies / 锁定依赖 | `uv sync --all-groups --locked` | Pending / 待执行 |
| Lint and format / 规范与格式 | Ruff check and format check / Ruff 检查与格式检查 | Pending / 待执行 |
| Strict types / 严格类型 | `uv run mypy src/media_sync` | Pending / 待执行 |
| Full tests and coverage / 全量测试与覆盖率 | `uv run pytest --cov=media_sync --cov-report=term` | Pending / 待执行 |
| Asset replay/lifecycle / 资产重放与生命周期 | both discovery paths, CAS, stale lease and final DB failure / 两条发现链、CAS、旧租约与最终 DB 故障 | Pending / 待执行 |
| Locator/downloader security / locator 与下载安全 | schema, SSRF, redirects, pinned DNS, limits, resume and secret scans / schema、SSRF、重定向、DNS 固定、限制、续传与密钥扫描 | Pending / 待执行 |
| Emby determinism / Emby 确定性 | XML validation, repeated export and golden-tree hash / XML 验证、重复导出与黄金目录哈希 | Pending / 待执行 |
| Package and migrations / 包与迁移 | `uv build` plus source/unpacked-wheel upgrade / 构建及源码/解包 wheel 升级 | Pending / 待执行 |
| Docs/upstreams/diff / 文档、上游与差异 | repository scripts and `git diff --check` / 仓库脚本与差异检查 | Pending / 待执行 |

## Live qualification / 线上资格验证

All seven platform media downloads and real Emby/Jellyfin rescans remain `NOT_RUN`. Automated downloader/export tests cannot promote them. / 七个平台的真人媒体下载及真实 Emby/Jellyfin 重扫全部保持 `NOT_RUN`；自动下载/导出测试不能将其提升为通过。
