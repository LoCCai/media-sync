**English** | [中文](progress.zh.md)

# Progress

Status: plan frozen; implementation pending.

- Confirmed at baseline `f41c6b3` that the current subscription `run-now` route changes only scheduling state, while the global scheduler and pipeline workers may claim unrelated subscriptions.
- Confirmed that the existing downstream selector covers the author's entire active asset snapshot and drops the detailed pipeline outcome at the worker boundary.
- Audited all seven history paths. No platform currently has evidence for permanent history completion; only Bilibili has trustworthy per-unit continuation and source-end observation, which remains vulnerable to cross-page list drift.
- Reproduced the Windows exporter pin defect: desired access zero allows an ancestor rename while the handle is open. `FILE_LIST_DIRECTORY` denies the rename and releases it after close.
- No source, database, deployment, account, supervisor or production media state has been changed by this planning checkpoint.

