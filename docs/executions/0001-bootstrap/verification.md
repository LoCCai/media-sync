# Execution 0001 verification / 执行 0001 验证

- Verification date / 验证日期：2026-08-30
- Environment / 环境：Windows PowerShell, Asia/Shanghai

## Evidence captured before documentation commit / 文档提交前已获取证据

| Check / 检查 | Command / 命令 | Result / 结果 |
| --- | --- | --- |
| Workspace baseline / 工作区基线 | `git status --short --branch` | `## No commits yet on master` |
| Python | `python --version` | `Python 3.11.8` |
| Node.js | `node --version` | `v24.19.0` |
| Git | `git --version` | `git version 2.55.0.windows.5` |
| MediaCrawler revision | `git -C .upstream/MediaCrawler rev-parse HEAD` | `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` |
| bili-sync-up revision | `git -C .upstream/bili-sync-up rev-parse HEAD` | `dcb5bb73b56ac45b2525da14b389e185b0ea6dbd` |

## Final checks / 最终检查

| Check / 检查 | Command / 命令 | Exit / 退出码 | Result / 结果 |
| --- | --- | ---: | --- |
| Lock JSON parses / 锁文件可解析 | `Get-Content upstreams.lock.json \| ConvertFrom-Json` | 0 | 2 upstream entries / 2 个上游条目 |
| Locked revisions match / 锁定版本匹配 | Compare `rev-parse HEAD` with lock entries / 对比 HEAD 与锁条目 | 0 | Both `True` / 两项均为 `True` |
| Upstreams ignored / 上游已忽略 | `git status --short --ignored` | 0 | `!! .upstream/` |
| Whitespace validation / 空白字符验证 | `git diff --check` | 0 | No output / 无输出 |

The staged file list and diff are reviewed immediately before committing. Runtime secrets and nested `.git` directories are excluded by `.gitignore`.

提交前会再次审阅暂存文件列表与差异。运行时密钥和嵌套 `.git` 目录已通过 `.gitignore` 排除。
