**English** | [中文](verification.zh.md)

# Execution 0001 verification

- Verification date: 2026-08-30
- Environment: Windows PowerShell, Asia/Shanghai

## Evidence captured before documentation commit

| Check | Command | Result |
| --- | --- | --- |
| Workspace baseline | `git status --short --branch` | `## No commits yet on master` |
| Python | `python --version` | `Python 3.11.8` |
| Node.js | `node --version` | `v24.19.0` |
| Git | `git --version` | `git version 2.55.0.windows.5` |
| MediaCrawler revision | `git -C .upstream/MediaCrawler rev-parse HEAD` | `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` |
| bili-sync-up revision | `git -C .upstream/bili-sync-up rev-parse HEAD` | `dcb5bb73b56ac45b2525da14b389e185b0ea6dbd` |

## Final checks

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Lock JSON parses | `Get-Content upstreams.lock.json \| ConvertFrom-Json` | 0 | 2 upstream entries |
| Locked revisions match | Compare `rev-parse HEAD` with lock entries | 0 | Both `True` |
| Upstreams ignored | `git status --short --ignored` | 0 | `!! .upstream/` |
| Whitespace validation | `git diff --check` | 0 | No output |

The staged file list and diff are reviewed immediately before committing. Runtime secrets and nested `.git` directories are excluded by `.gitignore`.
