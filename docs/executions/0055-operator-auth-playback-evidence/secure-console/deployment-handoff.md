**English** | [中文](deployment-handoff.zh.md)

# Cross-host reverse-proxy deployment handoff

- Date: 2026-09-05
- Application baseline: `0fd7c17`
- Status: Authenticated console entry observed; platform-login failures under diagnosis; full qualification incomplete

## Goal and plan

Deliver a complete Compose configuration for an application host and a separate LAN HTTPS reverse proxy. Preserve the seven-platform goal, published application code, authentication, data volume and external credential. Keep the actual browser HTTPS authority explicit, align the probe Host, validate locally, then require operator configuration preflight before container recreation. Do not invent a public domain or claim that an HTTPS Origin enables TLS on the HTTP backend.

## Initial progress and evidence (historical)

The operator reports host checkout `0fd7c17`, image `sha256:468ba823e582f39fd7ae79b2c0550ff3f89081ab510f102ce19d1f0a66acacd5`, runtime UID 1000, a UID/GID 0 credential at mode 0600, `SECRET_UNREADABLE`, the new preflight entrypoint present and authentication preflight rejection. This supports a credential-read failure, not a successful deployment. A single-file owner correction was advised only for ordinary rootful/non-remapped Docker; successful subsequent preflight has not been supplied.

Two direct read-only LAN HTTP requests (root and public health) returned 403 `operator_host_forbidden`. Network reachability is proven, but deployment identity, successful login and current-process startup logs are not. Earlier tail logs can include previous failures.

The generated personal `docker-compose.yml` is Git-ignored and is not published. It preserves the supplied build-proxy settings, external secret path, named volume, tmpfs, port 8632 on all interfaces and optional supervisor profile. `MEDIA_SYNC_PUBLIC_HOST` is a required host[:port] value shared by the HTTPS Origin and healthcheck Host. The field must omit scheme/path/trailing slash and explicit default :443; nondefault HTTPS ports must be retained. The supervisor does not serve HTTP, so its inherited API healthcheck is disabled rather than used as worker-health evidence.

## Initial verification (historical)

- Existing Prettier YAML parser successfully parsed the whole generated file; formatting check passed.
- Four pure application-policy checks passed: HTTPS default authority and :8443 accept their corresponding Host with Secure Cookie; explicit :443 and LAN HTTP are rejected by the direct policy validator. Use the canonical authority in the healthcheck.
- Independent review confirms cross-host TLS termination with HTTP upstream is compatible: preserve actual Host, Origin, Cookie and CSRF; forwarded-host/proto headers do not replace these checks.
- No Docker CLI is available locally. Compose interpolation/schema, container recreation, runtime UID fixes, reverse-proxy TLS/certificate trust, browser login, SSE and live platform/media-server workflows are not verified by this handoff.
- No application source, upstream lock, frozen plan, user secret value, server filesystem or running service was modified. Personal configuration stays outside Git; only sanitized bilingual documentation is published.

## Initial operator steps (historical)

Back up and replace only the live Compose file in the existing project directory; keep the named volume and other .env entries. Set the actual `MEDIA_SYNC_PUBLIC_HOST` in that private .env. Run `docker-compose config --quiet`, then override the entrypoint to run `serve --check-config`. Only after fixed valid status, run `docker-compose up -d --force-recreate media-sync`; restart alone does not reload changed environment, and no image rebuild is needed for this configuration.

The separate proxy forwards to the application's LAN HTTP port, preserves the complete browser Host and disables response buffering for SSE. Restrict backend access to the proxy on a trusted LAN; this hop remains unencrypted. Verify through the real HTTPS browser address. Do not delete volumes, broaden credential permissions, automatically accept a license or convert these partial results into live PASS.

## Verification after the operator supplied the HTTPS entry

Date: 2026-09-05. The operator supplied the actual HTTPS entry after the initial variable-based handoff. The private, Git-ignored `docker-compose.yml` now uses its fixed HTTPS Origin and matching fixed healthcheck Host; the `MEDIA_SYNC_PUBLIC_HOST` placeholder has been removed. The complete personal YAML passed the existing parser again. The actual domain, IP addresses and credential-file path are intentionally omitted from this public record.

- Normal certificate-verified HTTPS GET requests, without a TLS-verification bypass, returned 200 for root, public health and public ready.
- Independent anonymous requests to `/api/v1/accounts` and `/api/docs` returned 401 with fixed `operator_auth_required`. These requests did not exercise HTML navigation.
- In the real in-app browser, HTML navigation to `/accounts` reached `/?return_to=%2Faccounts` and displayed the operator login page. An initial independent PowerShell redirect probe stopped with `InvalidOperationException`; that failed attempt supplied no redirect status. A subsequent independent HttpClient probe with automatic redirects disabled confirmed HTTP 303 and `Location: /?return_to=%2Faccounts` for HTML navigation to `/accounts`.
- No login value was automatically entered and no Cookie or credential was read by the agent. At this initial anonymous-check stage, manual operator login was still pending; the subsequent observation is recorded below.
- Application source remains at baseline `0fd7c17`. Successful HTTPS responses do not identify the currently running image or prove that all current Linux-image, volume, restart and recovery gates passed. The earlier reported image ID is not re-established by these probes.

The real HTTPS endpoint and anonymous entry boundary are now verified to the scope above. A successful standalone configuration-preflight transcript is still not supplied. Compose schema/runtime recreation and container identity are not inferred from the page. The browser-facing TLS result does not change the plaintext nature of the separate reverse-proxy-to-application HTTP hop.

## Observation after manual operator login

Date: 2026-09-05. The operator manually logged in to the console. Subsequent read-only browser inspection reached the authenticated `/accounts` page and observed three platforms with failed account-authentication states. The Jobs page actually loaded six failed operations. The most recent displayed operation ran from 16:27:59 to 16:28:07 and exposed `runner_status=failed`, `login_session_status=failed`, `auth_status=failed` and fixed code `operation_login_failed`.

The UI showed an event-stream connection indicator and cursor 30. This is a connection indication, not proof that a newly generated event was delivered, persisted or replayed after reconnect. No new business operation or platform login was started by the agent, and no credentials, account names or UUIDs are recorded here.

Authenticated console access and the existing failure records have now been observed; a complete login/session lifecycle, SSE delivery/reconnect, successful platform synchronization and Emby/Jellyfin qualification remain incomplete. The failed platform records are evidence requiring diagnosis, not successful live qualification. See [login runtime triage](login-runtime-triage.md) for the shared runtime checks, code evidence and remaining deployment-side proof; without that proof, the failure cause must not be asserted as established.

## Current next step

Follow the bounded, credential-free checks in the runtime triage before retrying platform login; do not automatically accept licenses or start platform/media-server writes. If the personal Compose must be applied again, keep the fixed actual Origin and healthcheck Host, preserve data and secrets, perform configuration preflight, and recreate the service rather than merely restarting it. The historical `MEDIA_SYNC_PUBLIC_HOST` setup step above no longer applies to the delivered fixed configuration.
