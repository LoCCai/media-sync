**English** | [中文](progress.zh.md)

# Progress

Baseline clean and synchronized. Three independent source audits identified attachment loss, missing dynamic refresh, incompatible upload-only checkpoints and cross-author content reassignment. Stage A addresses the verified data-integrity dependency before any new dynamic producer can invoke the existing ingestion path. No dynamic scope is enabled and no platform request is made.

Public GitHub read-only source discovery also checked SocialSisterYi/bilibili-API-collect (default deprecated, commit4c00347d4f3494318903eeb11fb00d7b9c1f8c68) and Nemo2011/bilibili-api (main, commit3798d3b3bd3c3a93678d5a0367637a19262303ef). Their current trees/readmes contain shutdown notices, not the needed dynamic contract. No removed source was restored, no runtime dependency/lock changed, and these notices are not treated as technical response evidence. Stage C remains missing evidence.

## Stage A implementation

Plan frozen at `c24ab78`. A regression first demonstrated that cross-author content upsert silently overwrote ownership. SQLite and PostgreSQL now condition the native content conflict update on the current database owner and never SET author_id. Same-author refresh remains allowed, including existing ORM instances; different-author rejection changes no content metadata or tombstone. The author/content savepoint rolls back earlier changes in that call while leaving the outer transaction usable. PostgreSQL author discovery also uses native upsert; other-dialect fallback locks and refreshes a found row before checking its owner. There is no historical repair, schema migration, implicit takeover or path rename.

Typed conflicts propagate as the literal `content_ownership_conflict`, not mutable exception text or attributes. Generic sync, MediaCrawler ingestion and CLI use terminal failure; the scheduler does not automatically retry that Job or count it toward an account circuit. Web and downloadable safe reports preserve the exact classification, explain that existing content remains with its original creator, and advise inspecting subscription/source. They do not recommend deleting data or replacing credentials. Normal future subscription scheduling is not globally disabled by this per-Job terminal policy.

MediaCrawler and bounded CLI still read durable publication truth before handling a thrown ingestion error, so a post-commit exception cannot overwrite an already successful Run. A conflicting bounded unit cannot publish a checkpoint, assets or refresh observations; earlier committed legacy batches retain their original semantics and are not presented as rolled back. Failure cleanup and downstream-pipeline behavior are being checked against the actual normalized ingestion and sealed scheduler paths.

## Still required

Stages B–D remain unimplemented: explicit uploads/dynamics/both scope, independent resumable feeds, source-backed dynamic author/attachment contracts, exact refresh authority and the capture → archive → local-library workflow. A content ownership guard is a prerequisite, not dynamic media support. The other five platform profiles, three remaining pasted-Cookie validators and seven-platform real-world qualification remain open. Local compatible-directory output does not require a server connection; no claim is made that a media server plays arbitrary text/gallery files.

No production login, subscription change, retry, download/export, deployment, media-server action or supervisor restart occurred. The historical failed Bili canary remains unresolved by live evidence.

## Review findings and reopened freeze

An independent read-only review found two concrete durability gaps before publication. First, CLI failure marking was best-effort but its JSON unconditionally claimed failed_terminal even if the database write failed. Second, a Run could commit the ownership-conflict terminal state before Job finalization; a lost acknowledgement or process exit could then let the old success-only reconciliation retry the Job and affect circuit counters. Source freeze was reopened to fix precise conflict Run reconciliation and honest CLI readback. The already-started unit/contract checks and first package build are intermediate snapshots, not final-source release gates. No result has been relabeled to conceal the review findings.

## Durability corrections implemented

CLI now confirms its exact failure status/code from a new transaction. Lost commit acknowledgement can still resolve to confirmed terminal failure; failed/unavailable readback produces fixed `unknown / ingestion_state_unconfirmed`, observed conflict code and an inspect-Run instruction, not a retry claim. Unavailable initial bounded publication truth causes no failure write. An independent review confirmed existing succeeded Runs are protected by the INGESTING compare-and-swap and never overwritten.

The scheduler repository reconciles only the exact current attachment with literal failed_terminal/content_ownership_conflict. Native update predicates recheck Run scope, observed Job status and lease; a live worker also needs its current owner/token and unexpired lease. Recovery covers lost acknowledgement, expired leases, old retry/queued states and operator actions; it preserves prior lane failure counters, releases only the relevant probe and emits no media pipeline. Normal successful-Run behavior is retained. Advisory outcomes cannot adopt an unattached historical conflict Run; the existing generic handler's explicit fixed conflict result may still bind its actual Run during finalization. No scheduler service rewrite was required.

The second production freeze was scheduler/repository.py SHA256 `37ac86a66543d8845bb1e1ae6d415169b27247f4bceb94f24a86a2130a773b21`. The historical-Run guard changed after the second unit/contract runs had started; those remain snapshot checks. The further seven-line correction below also landed after complete integration began. Final affected integration/unit/API regression supplements those snapshots; exact commands/results and package correspondence are recorded in verification rather than claiming one same-source full-suite run.

## Final recovery isolation

A second independent review reproduced queue poisoning from a malformed old retry payload. Three new regressions cover retry_wait, failed_retryable and expired running Jobs with exact conflict attachments. A seven-line correction preserves their proven terminal outcome but skips subscription scheduling when pure payload validation fails: an invalid historical cycle cannot authorize changes to a newer schedule. Other queued subscriptions remain claimable, database exceptions are not swallowed, and successful-Run logic is unchanged. The reviewer independently reproduced all three repaired cases and unchanged schedule snapshots.

Latest frozen repository SHA256 is `cee10a1e20edce7f8ae6d2c0690ce564773d679a8f4a3bdf5e0263f11b024bc4`. No further source edits are planned; release verification and bilingual Git publication follow in the verification record. Stage A does not close Stages B–D or the original goal.

Final affected regression passed551 with13 unavailable PostgreSQL cases skipped; full Web passed640. Complete-directory snapshots and all review-driven corrections are separately recorded, not summed or presented as one same-source full suite. Final wheel/sdist source bytes match all140 application Python files. Stage A is implemented and offline verified; publication is recorded next, without deployment or live qualification.

Bilingual implementation `d43988c` is now published to GitHub, with non-force push and fresh-fetch HEAD/origin equality0 0 plus a clean worktree. This final publication-record update is a separate bilingual commit. Stage A is delivered as the documented prerequisite only; follow-up dynamics scope/attachments/refresh and seven-platform qualification remain required.
