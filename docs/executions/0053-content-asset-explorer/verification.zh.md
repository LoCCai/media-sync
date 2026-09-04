[English](verification.md) | **中文**

# 执行 0053 验证

- 状态：仅完成变更前基线；实现验证待运行
- 日期：2026-09-05
- 基线：be26cc7

## 已记录基线

| 检查 | 结果 |
| --- | --- |
| Git 同步 | HEAD == origin/main == GitHub main == be26cc7a168e54ba383a1d2446c438c2d80bc4ef；仅保留既存未跟踪 .mimosa |
| 前驱冻结套件 | 执行 0052 已记录 2315 passed、3 skipped、1 warning，耗时 555.05 秒；skip 均为 Windows 不适用的 POSIX 用例 |
| 当前 API 基线 | uv run --frozen pytest -q -p no:cacheprovider tests/unit/test_api_server.py → 9 passed、1 项已知 Starlette/httpx 弃用 warning，耗时 3.93 秒 |
| 当前 Web 基线 | npm --prefix web test -- --run → 3 个文件、17 项测试通过 |
| 文档 | uv run --frozen python scripts/check_docs.py → 新增八份 0053 记录前，466 份 Markdown 通过 |
| 锁定上游 | uv run --frozen python scripts/check_upstreams.py → 2 个锁定 checkout 通过 |
| 仓库空白 | 新增 0053 记录前 git diff --check 通过 |

Explorer 投影、详情端点、归档预览、Range/安全测试、Web 升级、打包门禁与完整套件仍待执行。

## 证据口径

本基线未使用真人账户、平台 API/CDN、下载的作者媒体或 Emby/Jellyfin 服务。全部此类行继续在 Execution 0047 下保持 NOT_RUN。
