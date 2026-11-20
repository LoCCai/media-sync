**English** | [中文](goal.zh.md)

# Goal: surface the operator-visible gaps 0088 left behind

## Why this execution exists

[0088](../0088-code-review/verification.md) fixed 26 defects but left three
operator-facing findings unfixed because they were classified as NIT or RISK.
They are not cosmetic: each one makes a real state invisible to the person
running the deployment. This execution closes them, and does so without touching
any frozen platform behaviour.

1. **The continuation delays for four platforms were not exposed anywhere.** An
   operator compares `/api/v1/settings` and `doctor --deep` against the
   supervisor's environment to prove both processes pace scans identically. Those
   two surfaces reported only Bilibili, XHS, Douyin and Kuaishou. Weibo, Tieba and
   Zhihu — the platforms whose policies were missing at nine construction sites —
   were invisible, which is exactly how that wiring gap stayed undetected.
2. **The dashboard presented bounded windows as totals.** Jobs are fetched with
   `limit=12`, assets with `limit=200`, contents with `limit=50`, and the KPI
   cards derived "待处理任务" and "已归档资产" from those arrays. A 40-job queue
   showed 12; a 5 000-asset library showed 173. The numbers were right about the
   window and wrong about the question.
3. **Every non-scheduler operation row read "已有白名单摘要".** When
   `safeOperationResult` returned a projection, the cell printed that phrase
   regardless of whether the operation was a download, an export or a login, so a
   successful download and a successful login were indistinguishable at a glance.

## What stays untouched

- No change to any platform's cursor, stop reasons, selection or delivery
  behaviour. This execution is entirely about what the API and the console *show*.
- No new fields that could carry a secret: the added values are integer delays
  already present in `Settings`, already validated, and already compared by
  `deployment-handover`.
- Deployment, login and every live request stay `NOT_RUN`
  per [0087](../0087-operator-canary/qualification.md).
