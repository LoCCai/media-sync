**English** | [中文](verification.zh.md)

# Pasted Cookie login audit and verification

- Date: 2026-09-05
- Status: Read-only source audit complete; new functional verification `NOT_RUN`
- Source context: HEAD `7268352` at documentation recording, with concurrent login repairs in the working tree. This is not a clean-tree release qualification.
- Pinned MediaCrawler checkout: `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`, matching `upstreams.lock.json` by read-only revision inspection. The upstream checkout was not edited or advanced.

## Project source findings

Repository-relative references below identify inspected symbols rather than promise future API contracts.

| Inspected source | Read-only finding |
| --- | --- |
| `src/media_sync/application/workbench.py`, `AccountWorkbenchService` | Cookie accounts require an opaque credential reference. Existing same-name accounts with differing login configuration conflict; account creation is not Cookie authentication. |
| `src/media_sync/interfaces/api.py`, `AccountCreate` and account login eligibility | Account creation accepts `credential_ref`, not raw Cookie input. Existing QR-login eligibility excludes Cookie accounts. |
| `src/media_sync/infrastructure/db/repositories.py`, `AccountRepository`; `src/media_sync/domain/transitions.py` | Account auth writes use observed-state compare-and-swap and fixed transitions. No audited general verified-Cookie replacement transaction exists. |
| `src/media_sync/security/secrets.py`, `SecretResolver` and providers | Environment, confined file and keyring references resolve secrets; providers are read-only. This does not provide a managed private write vault. |
| `src/media_sync/scheduler/mediacrawler_handler.py`, `MediaCrawlerScheduledHandler.run`; `src/media_sync/application/mediacrawler_download.py` | Cookie collection/download resolve the account's credential reference. Candidates must not be published into these consumers before successful verification. |
| `src/media_sync/scheduler/service.py`, handler context construction | The handler `AccountRef` carries the credential reference, not an authentication-status gate. An existing configured Cookie can be attempted without this proposed validation flow. |
| `src/media_sync/integrations/mediacrawler/login.py` and `login_runner.py`, `_configure_upstream` / `_install_client_guard` | Login modes are QR and saved-session probe. `update_cookies` completion raises authenticated without a fresh remote authentication check; it cannot validate an imported candidate. |
| `src/media_sync/integrations/mediacrawler/bridge.py`, `BridgeRequest` / private input | Cookie data already has a bounded private child-input route, not a public manifest field. Any new import must preserve that secret boundary. |

The deployed operator-secret mount may be read-only. A new managed vault must be independent of `/run/secrets`; neither making that mount writable nor selecting a new secret scheme is approved by this audit. Linux owner-only behavior and Windows ACL/DPAPI remain decisions for the next frozen plan.

## Pinned platform findings

All upstream references are relative to the locked `.upstream/MediaCrawler` checkout. These are code findings, not observed live responses.

| Platform / source | Current check and resulting limit |
| --- | --- |
| Bilibili, `media_platform/bilibili/client.py`, `pong` | Calls `/x/web-interface/nav` and checks `isLogin`. Best first-slice basis; freeze strict boolean and canonical current-user identity validation rather than preserve a loose truthiness check. |
| XHS, `media_platform/xhs/client.py`, `query_self` / `pong` | Calls `/api/sns/web/v1/user/selfinfo`, then checks nested `data.result.success`. A self endpoint exists, but exact identity/response semantics and signed-client behavior still need qualification. |
| Zhihu, `media_platform/zhihu/client.py`, `get_current_user_info` / `pong` | Calls `/api/v4/me` and checks `uid` and `name`. Define strict identity proof and prevent email or other full-response personal data entering diagnostics. |
| Weibo, `media_platform/weibo/client.py`, `pong` | Calls `/api/config` and checks `login`. A remote login flag is present; the exact authenticated-user identity contract remains undefined. |
| Kuaishou, `media_platform/kuaishou/client.py`, `pong` | Checks GraphQL `visionProfileUserList` result `1` with `ftype=1`. The audit did not establish that this is authoritative authenticated-self proof. |
| Douyin, `media_platform/douyin/client.py`, `pong` | Checks local storage `HasUserLogin` or Cookie `LOGIN_STATUS`. A pasted marker can satisfy this without remote proof; this check must not authenticate a candidate. |
| Tieba, `media_platform/tieba/client.py`, `pong` | Checks presence of `STOKEN`, `PTOKEN` or `BDUSS`. Mere Cookie presence is not validity; this check must not authenticate a candidate. |

Pinned `login_by_cookies` implementations also only import Cookie values; XHS imports `web_session` specifically. Successful browser import or header update must never be recorded as successful remote verification. An old authenticated profile would contaminate the result, so candidate isolation is mandatory.

## Audit method and results

Used read-only `rg -n`, `Get-Content` and bounded line selections to inspect the cited project/upstream symbols; read `upstreams.lock.json`, and ran `git rev-parse --short HEAD` plus `git -C .upstream/MediaCrawler rev-parse HEAD`. An initial search included nonexistent guessed scheduler/adapter paths; it produced no evidence and was corrected by searching actual tracked source. No upstream network authentication request, platform browser session, credential resolution or Cookie write was executed.

This documentation increment adds eight bilingual Markdown files only. No Cookie implementation, test fixture, endpoint, secret provider, migration or account mutation is delivered. `.venv/Scripts/python.exe scripts/check_docs.py` passed with 552 Markdown files checked. Symbol cross-checking corrected the draft's handler class name to `MediaCrawlerScheduledHandler`. Documentation validation does not change functional status.

## Functional evidence status

| Gate | Status |
| --- | --- |
| Paste/parse/validate/save implementation and automated tests | `NOT_RUN` — not implemented |
| Private vault permissions, atomic replacement and crash recovery | `NOT_RUN` — design pending |
| Bilibili real self-authentication, persistence and reuse | `NOT_RUN` |
| Remaining six authoritative validators and live qualification | `NOT_RUN` — not implemented |
| Cookie-based author capture and Emby/Jellyfin playback for this new flow | `NOT_RUN` |

The separate login runtime/diagnostic test results and operator-supplied blank-browser smoke do not qualify Cookie authentication. No platform or playback PASS is created by this audit.
