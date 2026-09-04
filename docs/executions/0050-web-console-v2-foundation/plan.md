**English** | [中文](plan.zh.md)

# Execution 0050 plan

- Status: Executed and verified for the offline foundation
- Plan date: 2026-09-04
- Predecessor: `6d68768`
- Database migration: None
- Implementation and closeout commit: the commit containing this record (self SHA not embedded)

## Baseline

The operator's first container run proved that Chromium itself could launch, but `mediacrawler doctor` stopped at `license_digest_mismatch`; the old build manifest also contained `chromium: launch-failed`. The single-file console exposed every workflow in one long page, required two checkboxes after every refresh, and gave little route-level task context. The 0050 plan therefore couples the portable qualification repair with the independently removable SPA foundation while retaining all backend safety gates.

## Delivery sequence

1. Correct and test LICENSE qualification against the pinned upstream blob with canonical LF semantics.
2. Establish frontend tooling, tokens, shell, responsive navigation, shared controls, API client and typed projections.
3. Migrate overview and read-only account/subscription/job/asset surfaces, then wire the existing create/login/run/download/export operations.
4. Add content and library projection endpoints, diagnostics and settings, one-time acknowledgement, and the `/legacy` rollback path.
5. Integrate static serving, route fallback, cache/security headers and the Node-free multi-stage Docker build.
6. Validate browser behavior, reference fidelity, desktop/mobile layouts, static resource packaging and Python/frontend quality gates.
7. Update deployment/status/journal records, commit all intended files, push `main`, and reconcile local/remote SHA.

## Verification plan

- Frontend: Prettier, `svelte-check`, Vitest and a production adapter-static build.
- Backend: complete API tests, checkout/license-focused contract tests, Ruff, format, strict mypy, compileall, package build, docs and upstream locks.
- Browser: every route renders meaningful content with no framework overlay or console errors; exercise reset → first acknowledgement → refresh persistence; inspect desktop and mobile screenshots against the bili-sync reference.
- Complete Python suite: run and record the exact Windows result without suppressing the previously documented receipt/process flakiness.
- Docker: static Dockerfile/context audit here; actual image build, manifest and runtime probes on the operator Linux host.

## Commit policy

All implementation, tests and closeout records are committed together after the gates above. The resulting commit is pushed to `origin/main` automatically, per operator instruction; generated frontend output, `node_modules`, local databases and raw junit XML remain ignored.
