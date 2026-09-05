**English** | [中文](goal.zh.md)

# Bilibili login-success follow-up goal

- Date: 2026-09-05
- Status: Frozen before implementation
- Baseline: f9b343c

Investigate the operator's successful Bilibili login without confusing persisted authentication, login-start eligibility, and actual capture. Fix the observed contradictory console and the independently reproduced post-QR confirmation omission. Preserve the seven-platform subscription/archive/Emby goal and the accepted pasted-Cookie backlog; neither is complete.

Acceptance: authenticated accounts do not show an irrelevant failed login-start preflight; cached readiness cannot authorize re-login; Bilibili Cookie updates cannot report login success without a fresh strictly-boolean positive upstream remote pong. Record production observation separately from synthetic tests, fresh-process reuse, author capture and media playback.

