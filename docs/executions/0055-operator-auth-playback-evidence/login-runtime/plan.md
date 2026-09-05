**English** | [中文](plan.zh.md)

# Login browser runtime plan

- Date: 2026-09-05
- Status: Frozen before implementation

1. Commit this bilingual goal/plan/progress/verification baseline; preserve earlier frozen plans.
2. Share the approved browser-child environment construction across login, creator and detail, including `PLAYWRIGHT_BROWSERS_PATH`; exclude proxy credentials, arbitrary application secrets and Python injection settings. Retain required Windows/display settings.
3. Add an explicit bundled-Chromium adapter policy around pinned upstream standard launches. Remove only conflicting browser selectors, retain profile/proxy/context options, and install it in login, creator and detail entry points. Do not mutate upstream source or claim live fingerprint equivalence.
4. Extend login preflight to the same child environment and a bounded, temporary headed persistent browser launch. Keep general headless readiness available and make fixed failure reporting value-safe. No account profile or platform URL is used.
5. Add a bounded Xvfb readiness/liveness gate after operator check-config and before database initialization. Preserve help/check-only paths and test early failures without migrations; no credential-permission relaxation.
6. Run focused and broader regressions, static/types/docs/upstream checks and an independent launch-policy review. Attempt real local blank-browser verification only if the installed runtime supports it; mark Linux image/live platform checks NOT_RUN when unavailable.
7. Record bilingual progress, actual commands/results, remaining verification and precise operator rebuild steps. Explicitly stage reviewed changes, use bilingual commits, push GitHub and confirm remote identity/cleanliness. Do not deploy automatically or mark the full product goal complete.

Runtime browser exceptions still lacking actionable classification beyond the preflight boundary remain explicit follow-up work; no raw upstream logs may be exposed. After packaging is fixed, qualify one operator-assisted QR login and saved-session reuse before expanding the live canary.
