**English** | [中文](progress.zh.md)

# Execution 0008 progress

- Status: Complete for the offline acceptance scope
- Started: 2026-08-30 15:48 +08:00
- Completed: 2026-08-30
- Plan commit: `f0c6015`
- Implementation commit: this commit
- Predecessor: Execution 0007 implementation commit `d071618`
- Network boundary: offline fixtures and repository-owned local helper processes only

## Outcome

Execution 0008 closes execution 0007 AC6 and AC13 as an offline successor acceptance result. It adds deterministic evidence for both remaining cancellation windows, a closed eleven-failure × three-sink matrix, fail-closed retained-filesystem and SQLite scanners, and an authoritative retained-artifact gate. The only production change is the final cancellation check immediately before completion-receipt publication.

Execution 0007's four historical records remain unchanged at their original `PARTIAL` result. This record reports the successor closeout; it does not rewrite prior evidence.

## Implementation delivered

| Deliverable | Result |
| --- | --- |
| Child-exit/pre-seal cancellation | A real repository-owned child returns `0`, its complete tree joins, cancellation is observed before receipt publication, the receipt writer is not entered, the attempt is secured and the account/profile lock can be reacquired |
| Handler pre-seal boundary | Normalization and ingestion spies remain at zero after the runner's cancelled verdict |
| Post-seal/pre-ingest cancellation | Single and repeated cancellation both join the protected normalizer before unwind; no Content/Asset, checkpoint advance or successful SyncRun is committed |
| Closed security matrix | Exact eleven-row failure enum × `filesystem`, `sqlite`, `operator` = 33 asserted cells |
| Scheduler authority | Every row checks Job, SyncRun, checkpoint, Content, Asset, platform/account lanes and Job/worker/lane CLI projections against its fixed terminal or fenced state |
| Scanner contracts | Retained filesystem traversal, path names, SQLite database files and sidecars are checked fail-closed |
| Compatibility | Manifest v2/receipt v1 remains byte-exact, immutable and manual-ingest/shared-normalization-only; scheduled recovery still trusts v3 only |

## Test-first and hardening history

1. The child-exit/pre-seal regression was added first and failed because `write_completion_receipt()` was entered after cancellation. A seven-line production repair added the final cancellation check; the regression then passed.
2. The handler post-seal single/repeated cancellation cases passed on their first run. The existing join-before-unwind implementation needed no production change.
3. The first matrix draft could pass without proving that a row actually injected its sentinel. Runner/handler cleanup observers were added, and every one of the eleven rows now proves that its generated sentinel existed before cleanup.
4. A `0.5s` timeout fired before the helper wrote its sentinel. The bounded timeout was changed to `4.0s`, preserving a real timeout while making injection evidence deterministic.
5. Runtime polling and final retained scans were separated: polling tolerates a temporarily locked SQLite file, while the final scan fails closed.
6. Audit found that default `os.walk` can swallow traversal errors and did not scan path names, while `Path.is_file()` could hide SQLite sidecar inspection errors. The scanners now reject those conditions, with dedicated contracts covering both fixes.

The ordinary matrix checks fixed redacted cleanup outcomes. Strong evidence for raw cleanup-error suppression comes from the separately selected quarantine/unresolved negative tests; the ordinary matrix's `.quarantine` and `Traceback` checks are not represented as an independent proof.

## Verification outcome

| Gate | Result |
| --- | --- |
| Exact cancellation/matrix core | `16 passed in 29.08s` |
| Matrix module including scanner contracts | `14 passed in 24.29s` |
| Related contract/integration modules | `151 passed, 1 skipped` |
| Credential-bearing negative boundary gate | `13 passed, 1 skipped in 7.31s` |
| Full branch-aware suite | `837 passed, 1 skipped in 248.20s`; `79%` branch-aware coverage |
| Authoritative retained-artifact gate | `45 passed in 69.82s`; `CLOSEOUT_PASS`; 33 matrix cells and 12 exact secret scans |
| Dependency, lint, format, types, build and repository checks | `PASS`; exact results are recorded in `verification.md` |

The single full-suite skip is the POSIX mode-bit boundary that is not applicable on Windows.

## Current qualification

| Scope | Status | Truth |
| --- | --- | --- |
| Execution 0007 AC6 successor closeout | `PASS` | Both remaining deterministic cancellation windows are exercised offline |
| Execution 0007 AC13 successor closeout | `PASS` | Exact eleven-failure × three-sink matrix and fail-closed scanners pass |
| Signed-locator refresh | Unimplemented | Execution 0009 scope |
| Automatic `sync → download → Emby` DAG | Unimplemented | Execution 0010 scope after refresh |
| Live login, creator traffic and scheduled runs | `NOT_RUN` | No authorized account or interactive challenge was supplied |
| Live CDN and real Emby/Jellyfin | `NOT_RUN` | No refresh-capable authorized environment or media server was supplied |

## Deferred truthfully

- Successful sealed v3 output may still contain an unknown signed query that the parent could not pre-register as a known secret. It remains an explicit credential-bearing temporary boundary until execution 0009 implements signed-locator refresh together with successful/recovery terminal cleanup or isolation.
- Durable automatic `sync → download → Emby` planning remains execution 0010. Execution 0008 creates no blocked downstream Jobs.
- Real QR/Cookie/saved-session login, creator traffic, platform pagination/rate behavior, CDN retrieval and Emby/Jellyfin scan/playback remain `NOT_RUN` for all seven platforms. Phone login remains unsupported.
- `wb`, `tieba` and `zhihu` downloadable assets, platform-specific derivatives, REST, QR/challenge presentation, resident supervision, Docker, public deployment and HA/PostgreSQL remain unimplemented or deferred.
