**English** | [中文](0003-pinned-webui-build-security-override.zh.md)

# ADR-0003: Build-time security override for the pinned MediaCrawler WebUI

- Status: Accepted
- Date: 2026-10-02

## Context

The pinned MediaCrawler checkout (d6f7c5bb) ships a WebUI whose npm manifest declares axios ^1.7.9. The Docker image build compiles that WebUI into the same-origin `/crawler/` bundle and enforces `npm audit --omit=dev --audit-level=low` as a fail-closed gate. On 2026-10-02 the npm advisory database published high-severity axios advisories affecting every axios release through 1.19.0 — including the lock-resolved axios 1.13.2 that the pinned checkout installs under the upstream `^1.7.9` declaration — so the gate only passes once the dependency is overridden to the fixed version axios@1.20.0 (which the `^1.7.9` range itself admits). The advisories include:

- GHSA-44g4-m2mj-wpvx — CIDR-form NO_PROXY entries are ignored, so proxy exclusions for internal IP ranges are bypassed;
- GHSA-r4gj-5m52-g5wh — the fetch adapter does not enforce `maxRedirects: 0`, allowing redirect-based SSRF.

The first uncached rebuild after the advisories published failed on that gate (the audit reports twelve high advisories for axios 1.0.0 – 1.19.0 and names axios@1.20.0 as the fix). Removing or relaxing the gate is unacceptable, and waiting for the upstream project to re-pin the dependency would leave deployments unbuildable indefinitely.

## Local deterministic evidence

Before this decision was recorded, the gate flow was reproduced locally against the pinned WebUI manifest (`.mediacrawler-local/webui/package.json`, seam `axios: "^1.7.9"`, no overrides) using the same steps as the Dockerfile build stage:

- With the prior override (axios 1.18.0): `npm audit --omit=dev --audit-level=low` reports **1 high severity vulnerability** — twelve axios advisories in the 1.0.0 – 1.19.0 range, including GHSA-44g4-m2mj-wpvx and GHSA-r4gj-5m52-g5wh — and `npm audit fix --force` names axios@1.20.0 as the fix.
- With the new override (axios 1.20.0): the same flow reports **found 0 vulnerabilities**.

## Decision

`docker/mediacrawler-webui-security-patch.mjs` applies a pinned exact build-time-only dependency override for the WebUI build. The script first asserts the upstream seams (it fails explicitly if upstream changes the axios `^1.7.9` declaration or already carries an `overrides` field), then applies exact versions: as of commit `2df128f`, axios 1.20.0 together with follow-redirects 1.16.0 and form-data 4.0.6. When advisories force an upgrade, the change is one line in this script, the commit message names the audit gate, and affected images are rebuilt from the resulting exact commit.

The override only affects the browser bundle compiled inside the image. The upstream checkout stays byte-for-byte unchanged and passes revision validation: no upstream file is modified, `scripts/check_upstreams.py` keeps passing, and `npm audit` remains a mandatory, unmodified build gate.

## Consequences

- New advisories landing between upstream releases still let images build fail-closed; the audit gate never ships a WebUI bundle carrying known vulnerabilities.
- Every override upgrade changes the image digest even when application source is unchanged; provenance identity (`org.opencontainers.image.revision`, `/opt/BUILD-MANIFEST.txt`) continues to identify the exact source commit of a produced image.
- When upstream re-pins axios (or overrides these packages itself), the script's seam assertions fail the build; the override versions must then be aligned with upstream inside the script, never silently skipped.
- The override table is a reviewed, intentional divergence from the upstream dependency declaration and must be re-evaluated whenever the pinned MediaCrawler commit changes.
- Commit `2df128f` records the first upgrade under this policy (1.18.0 → 1.20.0) in response to the 2026-10-02 advisories. Deployments built from commits before it carry the vulnerable transitive versions inside their WebUI bundle and should be rebuilt. Earlier baselines recorded in the 0072 verification and `docs/status.md` (axios 1.18.0, "0 vulnerabilities" at that time) predate these advisories and are superseded by this decision.
