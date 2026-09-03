**English** | [中文](security-review.zh.md)

# Security and privacy review (execution 0046)

Scope: the implemented posture of media-sync at the 0046 boundary, claim by claim, with the enforcing mechanism. This is a self-review, not an external audit.

## 1. Credentials and secrets

| Claim | Enforcement |
| --- | --- |
| Raw cookies/passwords are never persisted in the database, config, logs, argv or Git | Requirements AUTH-004; accounts store opaque `credential_ref` values only; QR/OTP material stays inside the login child process |
| Secret references resolve at process start only | `security/secrets.py`: `env:` / `keyring:` / `file:` schemes with a confined `MEDIA_SYNC_SECRET_FILE_DIR` root |
| Signed CDN URLs are runtime-only | Detail-protocol children carry them in bounded frames/memory; recursive strip before persistence (executions 0009, 0013+); retained-tree scans assert zero-match |
| Creator authority references are secret-typed | `SecretValue` provenance for `creator_input.secret_ref`; ambiguous query/fragment URLs fail closed |

## 2. Process boundary

| Claim | Enforcement |
| --- | --- |
| Upstream crawler never imported into the service | ADR-0001: external pinned checkout as a child process; module-identity checks (`_module_belongs_to_checkout`) reject foreign modules |
| Cookie enters only a private env channel | Bridge injects via environment read by a small runner, removed before import; the public argv carries only entry point + confined spec path |
| Login/crawl children are reaped deterministically | Parent START/CANCEL/EOF framing, post-result guardian, Windows job objects / POSIX process groups (execution 0012) |

## 3. Network and filesystem policy

| Claim | Enforcement |
| --- | --- |
| Downloads reach only public, verified addresses | Every hop resolves to public DNS answers; pinned connections; manual redirects that drop Range validators across origins |
| Download paths cannot escape configured roots | Path-confinement guards; symlink/lstat checks on every directory; archive blobs are immutable no-clobber links |
| Upstream binary downloads stay disabled | Bridge config forces `ENABLE_GET_MEIDAS/GET_MEDIAS = False` |

## 4. Service exposure

| Claim | Enforcement |
| --- | --- |
| API/console default to loopback | `MEDIA_SYNC_API_HOST=127.0.0.1`; compose publishes `127.0.0.1:8632:8632` only |
| No authentication is a documented decision | The API is a local-first operator surface; container deployment docs require trusted networks; no secrets are readable via the API (payloads are redaction-safe projections) |
| Structured logs are redacted | Classified secret names are masked at sinks; raw adapter exceptions never surface to CLI/API output |

## 5. Privacy

- The archive intentionally links content to authors the user subscribed to; collection is bounded by per-subscription `max_items`, request delays, and closed request profiles; comments and keyword crawling are explicit non-goals.
- Browser profiles are per-platform-per-account under a 0o700 runtime root; QR images relayed for the web console live in the same root and are deleted with the login attempt (execution 0040).

## 6. Residual risks (honest list)

1. The API has no authentication: anyone with host-network access to the port controls the service. Mitigation: loopback/Tailscale/LAN trust.
2. SQLite is the single store; disk access equals full data access (including credential *references*, which still require the secret provider to use).
3. Upstream platform behavior changes can alter what the pinned crawler does; the license gate is an acknowledgement, not a technical control on upstream behavior.
4. No external audit has been performed (`NOT_RUN`, operator option).
