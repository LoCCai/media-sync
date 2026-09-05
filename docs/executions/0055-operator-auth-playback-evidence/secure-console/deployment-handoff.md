**English** | [中文](deployment-handoff.zh.md)

# Cross-host reverse-proxy deployment handoff

- Date: 2026-09-05
- Application baseline: `0fd7c17`
- Status: Personal configuration delivered; final HTTPS authority and operator verification pending

## Goal and plan

Deliver a complete Compose configuration for an application host and a separate LAN HTTPS reverse proxy. Preserve the seven-platform goal, published application code, authentication, data volume and external credential. Keep the actual browser HTTPS authority explicit, align the probe Host, validate locally, then require operator configuration preflight before container recreation. Do not invent a public domain or claim that an HTTPS Origin enables TLS on the HTTP backend.

## Progress and evidence

The operator reports host checkout `0fd7c17`, image `sha256:468ba823e582f39fd7ae79b2c0550ff3f89081ab510f102ce19d1f0a66acacd5`, runtime UID 1000, a UID/GID 0 credential at mode 0600, `SECRET_UNREADABLE`, the new preflight entrypoint present and authentication preflight rejection. This supports a credential-read failure, not a successful deployment. A single-file owner correction was advised only for ordinary rootful/non-remapped Docker; successful subsequent preflight has not been supplied.

Two direct read-only LAN HTTP requests (root and public health) returned 403 `operator_host_forbidden`. Network reachability is proven, but deployment identity, successful login and current-process startup logs are not. Earlier tail logs can include previous failures.

The generated personal `docker-compose.yml` is Git-ignored and is not published. It preserves the supplied build-proxy settings, external secret path, named volume, tmpfs, port 8632 on all interfaces and optional supervisor profile. `MEDIA_SYNC_PUBLIC_HOST` is a required host[:port] value shared by the HTTPS Origin and healthcheck Host. The field must omit scheme/path/trailing slash and explicit default :443; nondefault HTTPS ports must be retained. The supervisor does not serve HTTP, so its inherited API healthcheck is disabled rather than used as worker-health evidence.

## Verification

- Existing Prettier YAML parser successfully parsed the whole generated file; formatting check passed.
- Four pure application-policy checks passed: HTTPS default authority and :8443 accept their corresponding Host with Secure Cookie; explicit :443 and LAN HTTP are rejected by the direct policy validator. Use the canonical authority in the healthcheck.
- Independent review confirms cross-host TLS termination with HTTP upstream is compatible: preserve actual Host, Origin, Cookie and CSRF; forwarded-host/proto headers do not replace these checks.
- No Docker CLI is available locally. Compose interpolation/schema, container recreation, runtime UID fixes, reverse-proxy TLS/certificate trust, browser login, SSE and live platform/media-server workflows are not verified by this handoff.
- No application source, upstream lock, frozen plan, user secret value, server filesystem or running service was modified. Personal configuration stays outside Git; only sanitized bilingual documentation is published.

## Operator next steps

Back up and replace only the live Compose file in the existing project directory; keep the named volume and other .env entries. Set the actual `MEDIA_SYNC_PUBLIC_HOST` in that private .env. Run `docker-compose config --quiet`, then override the entrypoint to run `serve --check-config`. Only after fixed valid status, run `docker-compose up -d --force-recreate media-sync`; restart alone does not reload changed environment, and no image rebuild is needed for this configuration.

The separate proxy forwards to the application's LAN HTTP port, preserves the complete browser Host and disables response buffering for SSE. Restrict backend access to the proxy on a trusted LAN; this hop remains unencrypted. Verify through the real HTTPS browser address. Do not delete volumes, broaden credential permissions, automatically accept a license or convert these partial results into live PASS.
