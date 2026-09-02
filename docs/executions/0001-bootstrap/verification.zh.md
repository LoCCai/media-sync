[English](verification.md) | **中文**

# 执行 0001 验证

- 验证日期：2026-08-30
- 环境：Windows PowerShell, Asia/Shanghai

## 文档提交前已获取证据

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 工作区基线 | `git status --short --branch` | `## No commits yet on master` |
| Python | `python --version` | `Python 3.11.8` |
| Node.js | `node --version` | `v24.19.0` |
| Git | `git --version` | `git version 2.55.0.windows.5` |
| MediaCrawler revision | `git -C .upstream/MediaCrawler rev-parse HEAD` | `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` |
| bili-sync-up revision | `git -C .upstream/bili-sync-up rev-parse HEAD` | `dcb5bb73b56ac45b2525da14b389e185b0ea6dbd` |

## 最终检查

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 锁文件可解析 | `Get-Content upstreams.lock.json \| ConvertFrom-Json` | 0 | 2 个上游条目 |
| 锁定版本匹配 | 对比 HEAD 与锁条目 | 0 | 两项均为 `True` |
| 上游已忽略 | `git status --short --ignored` | 0 | `!! .upstream/` |
| 空白字符验证 | `git diff --check` | 0 | 无输出 |

提交前会再次审阅暂存文件列表与差异。运行时密钥和嵌套 `.git` 目录已通过 `.gitignore` 排除。
