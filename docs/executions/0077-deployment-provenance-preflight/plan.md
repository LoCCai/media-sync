**English** | [中文](plan.zh.md)

# Plan

Status: **FROZEN FOR IMPLEMENTATION**. This plan authorizes local implementation and verification only. Deployment, platform traffic, Subscription execution and supervisor control remain outside this execution.

## 1. Freeze the additive evidence contract

- Extend `build_manifest` with `source_revision: string | null` and `source_revision_status: pass | fail | not_run`; preserve the existing `status`, `present` and allowlisted toolchain `facts` fields.
- Extend deep readiness with `continuations.bili_delay_seconds` and `continuations.xhs_delay_seconds`. Retain the existing database object's current and expected revisions as the only migration source of truth.
- Keep every change additive so an older stored response or a manifest without source revision renders as unavailable rather than crashing.

## 2. Carry source revision through the image

- Add Docker build argument `MEDIA_SYNC_SOURCE_REVISION=unavailable` and reject any value other than the sentinel or a full lowercase 40-character SHA.
- Record the value as `source_revision:` in `/opt/BUILD-MANIFEST.txt` and as `org.opencontainers.image.revision`; keep `.git` excluded by `.dockerignore`.
- Add the Compose build argument and a concise command comment: `export MEDIA_SYNC_SOURCE_REVISION=$(git rev-parse HEAD)` before a qualifying build.

## 3. Parse and publish safely

- Refactor build-manifest reading just enough to inject a temporary manifest in tests.
- Accept only a full lowercase SHA as `pass`, the exact sentinel or a missing line as `not_run`, and any other recorded value as `fail`; never echo malformed text.
- Add the safe continuation integers to the deep report. Do not make missing provenance block ordinary runtime readiness, because it is evidence quality rather than a crawler prerequisite.

## 4. Render operator evidence

- Update the shared TypeScript type and Diagnostics page to show the full source revision, a clear unavailable/invalid state, database current versus expected migration, and both continuation delays.
- Use existing panels and compact key/value rows; do not add cards inside cards or expose paths/secrets.

## 5. Verification and closeout

1. Focused Python tests for manifest parsing, report shape and API projection.
2. Focused Web tests for all new diagnostic states, followed by the complete Web suite, Svelte check and production build.
3. Dockerfile/Compose contract tests that assert the build argument, validation, manifest line, OCI label and `.dockerignore` boundary.
4. Complete Python suite, Ruff, strict mypy, compileall, lock/upstream checks, package builds, documentation links and `git diff --check`.
5. Write bilingual progress/verification and a deployment handoff. Commit implementation and documentation separately with bilingual bodies, then push by fast-forward only.

Live deployment and the XHS canary remain `NOT_RUN` at closeout. The next operator action is to pull the published SHA, export that exact revision for the build, back up `/data`, rebuild, and rerun deep readiness with the supervisor still stopped.
