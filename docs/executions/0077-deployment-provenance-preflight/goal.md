**English** | [中文](goal.zh.md)

# Goal: deployment provenance and XHS canary preflight

Status: **PLANNED ONLY** at baseline `4e8d75f`. No 0077 implementation, deployment mutation, platform request, Subscription execution or supervisor restart has started.

Execution 0077 closes the evidence gap exposed before the planned XHS deployment canary. A healthy HTTP response and package version `0.1.0` do not identify the application commit inside an image. The current authenticated deployment observed on 2026-09-08 returned public health/readiness success, but its Settings page did not expose the 0076 XHS continuation field and its deep diagnostic stopped at `git_inspection_failed`. Those facts contradict qualification of the deployed service as 0076; they do not identify its exact source revision or diagnose the checkout failure.

The intended operator result is a read-only, secret-free preflight that can answer:

```text
Which media-sync commit is in this image?
Which database migration is active and expected?
Which Bili/XHS continuation delays does this process use?
Is the pinned MediaCrawler checkout actually qualified?
```

## Required behavior

1. **Self-identifying image.** Docker builds accept an explicit application source revision, validate it as one full lowercase Git SHA or the closed `unavailable` sentinel, record it in the private build manifest and OCI image metadata, and never copy the media-sync `.git` directory into the build context or final image.
2. **Honest backward compatibility.** Images built without a revision remain runnable and report provenance `not_run`; malformed recorded revisions report `fail`. Neither state is silently converted into a commit or treated as live qualification.
3. **Safe diagnostic projection.** Existing authenticated deep readiness exposes only the validated application revision, its provenance status, current/expected database migration and the two integer continuation delays. It does not expose environment values, Cookies, tokens, creator references, host paths or raw subprocess output.
4. **Operator-visible evidence.** Diagnostics renders application revision, migration agreement and both continuation delays with compact stable states. The CLI JSON path uses the same report, so the API and supervisor containers can be inspected independently and compared without starting work.
5. **Reproducible Compose handoff.** The example Compose file forwards `MEDIA_SYNC_SOURCE_REVISION` as a build argument with a non-blocking `unavailable` default and documents the exact `git rev-parse HEAD` export used for a qualifying build.
6. **No operational side effects.** This execution does not log in, crawl, create/resume/delete a Subscription, download media, mutate a database, restart a container or start the supervisor.

## Acceptance evidence

- Unit tests cover missing, valid, unavailable and malformed build-manifest revisions plus the additive deep-readiness payload.
- Web tests cover full and absent revision rendering, current/mismatched migration status and both continuation values.
- Static checks prove Dockerfile/Compose propagation, OCI revision metadata and absence of `.git` inclusion.
- Focused and complete Python/Web gates, package checks and bilingual documentation checks are recorded without changing live qualification.

## Explicit non-goals

- Deploying or rebuilding the user's server.
- Resolving a server checkout failure without current-container shell evidence.
- Running the XHS canary or changing any platform qualification row.
- Beginning the later Douyin delivery implementation.
