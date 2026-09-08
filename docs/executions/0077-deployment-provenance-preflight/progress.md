**English** | [中文](progress.zh.md)

# Progress: deployment provenance and XHS canary preflight

Status: the local implementation is complete in `d6db86a`. No Docker/Linux deployment, database mutation, platform request, Subscription execution or supervisor restart was performed.

## Outcome

The deployment can now identify the exact media-sync source revision baked into an image and present that identity beside the current/expected database migration and the effective Bilibili/XHS continuation delays. The same secret-free deep-readiness report is available through the authenticated Web/API surface and `media-sync doctor --deep`, so the API and supervisor service definitions can be checked independently before any workload is resumed.

Missing provenance remains an explicit `not_run`; malformed or duplicated provenance is `fail` and is never echoed. These evidence states do not block ordinary service startup and do not grant live qualification.

## Implemented

1. **Image identity.** Docker accepts `MEDIA_SYNC_SOURCE_REVISION`, permits only one full lowercase 40-character Git SHA or `unavailable`, writes it to `/opt/BUILD-MANIFEST.txt`, and publishes it as the OCI `org.opencontainers.image.revision` label. The project `.git` directory remains outside the build context.
2. **Closed manifest parsing.** Deep readiness exposes a validated `source_revision` and `source_revision_status`. A missing manifest is `not_run`; a missing line or exact `unavailable` sentinel is provenance `not_run`; malformed and duplicate values are `fail` without reflecting the input.
3. **Migration truth.** A single packaged migration from the closed `0001..0015` set is visible even when it is old, while an unknown, missing or multiple revision is hidden. Only exact `0015_xhs_creator_notes` agreement is current.
4. **Effective pacing.** The report includes only the validated integer Bilibili and XHS continuation delays from the running process. These are evidence for comparing API and supervisor configuration, not a request to schedule work.
5. **Operator surfaces.** Diagnostics shows the application SHA, migration agreement and both continuation delays in the existing compact facts panel. The frontend fails closed for absent legacy fields or malformed backend values. `doctor --deep --accept-mediacrawler-license --json` emits the same report and exits nonzero when readiness is blocked.
6. **Compose handoff.** The tracked example forwards the source revision with an `unavailable` default and documents how to obtain the exact checked-out SHA. It does not require provenance merely to run an older/private build.

## Closeout corrections

- Final review found that the first implementation exposed the shared report only through API/Web despite the frozen plan requiring an independent supervisor check. The explicit deep `doctor` path and pass/blocked CLI tests were added before the final full suite.
- The database projection was kept allowlisted: a known older migration is useful evidence, but arbitrary database text is not rendered.
- Source, migration and continuation rendering is independently validated before display; unexpected backend strings do not become operator-visible diagnostic content.

## Remaining

- A post-push [authenticated read-only observation](online-observation-2026-09-09.md) found that the existing container's deep checkout/runtime checks now pass, but its UI lacks every 0077 provenance/migration/continuation row. The running application revision and database migration therefore remain unknown, and the XHS canary stopped before execution.
- Docker is unavailable on this Windows workstation. Dockerfile execution, image-label inspection, final runtime UID/mount behavior and API-versus-supervisor container comparison remain `NOT_RUN`.
- The current server has not been rebuilt from this revision. Its exact image identity, migration `0015`, pinned checkout, continuation equality, restart behavior and persistent mounts must be checked using the [deployment handoff](deployment-handoff.md).
- Live XHS login/profile adoption, creator API, CDN download, host archive/library/NFO bytes, replay, restart continuation and one resident-supervisor cycle remain `NOT_RUN`.
- Real PostgreSQL and optional Emby/Jellyfin reading remain `NOT_RUN`. A media-server API connection is not required for compatible local-directory output.
- Do not begin Douyin delivery until the XHS canary has a separate evidence record or a documented blocker. The original seven-platform goal remains active.
