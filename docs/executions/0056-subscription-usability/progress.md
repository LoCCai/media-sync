**English** | [中文](progress.zh.md)

# Progress

Implementation is in progress under planning commit `fe54aba`; this execution and the seven-platform product goal are not complete.

The implemented slice is published as `57c447c`; a fresh fetch at publication verified equality with `origin/main`. Automatic creator profiles were pending then; the Bili-first implementation and remaining scope are described below.

## Implemented in this slice

- Library/Settings and deployment guidance separate local compatible-directory output from optional Emby/Jellyfin connectivity. A real authenticated API/exporter test proves local video/NFO/body output with no connector configured or constructed; archive integrity is still required. Server-side scheduled/manual scanning is configured in the media server, not implicitly triggered by export.
- Migration `0009_subscription_removal` adds reversible removal. API/CLI share one transaction service; default lists hide removed subscriptions, the explicit removed view retains them, and restore keeps the same ID/checkpoint paused. Files, authors, contents, assets, Runs, Jobs and history remain. Dormant eligible sync/pipeline work is cancelled; claimed/running work or related active Operations rejects removal. Old terminal Job/nonterminal Run contradictions are preserved, not interpreted as live execution. Creating a duplicate removed subscription returns a fixed conflict and does not overwrite configuration.
- Subscription UI provides removal/restore confirmations, a removed view, fixed conflict guidance and identity/request-generation fences. Enabled subscriptions are labeled enabled rather than running, including the dashboard. Existing creator preview is explicitly local input validation and the name is a local note, not claimed remote profile discovery.
- Jobs offers Chinese business meaning and next steps, with raw fixed fields collapsed. The authenticated report for an exact subscription-sync Job contains closed version/state/error/time/identity evidence and at most five correlated Operations (16 KiB maximum); it distinguishes missing/foreign Runs, terminal Job/nonterminal Run and Worker completion/business failure. Reports require explicit retrieval/copy/download. No raw logs, SQL, request payloads, paths, credentials or arbitrary error strings are included; the aggregate support bundle is unchanged.

## Still required

Automatic creator nickname/avatar lookup was **not implemented** at the 0056 release. [0057](../0057-creator-profile-lookup/progress.md) has since frozen the plan and implemented the first Bili saved-session slice; consult that execution for qualification/publication. The other six platforms and Cookie mode remain required. Preserve a separate local alias and prevent ordinary ingestion from clearing profile data; do not substitute full creator crawling or an arbitrary remote-avatar proxy.

Pasted-Cookie remote validation/private persistence/reuse, bounded Bili history coverage without watermark skips, actual capture/archive and media-server qualification remain required. No production deployment, login, retry, download/export or supervisor restart occurred. Local synthetic tests do not remedy or reclassify the historical failed real canary.

Post-fix regression passed 2849 tests (eight environment skips); Web passed 440. The first full run's two failures and their corrections are retained in [verification](verification.md), not relabeled as a full-suite pass. The next required profile implementation is outlined in the [design draft](creator-profile-design.md); no remote lookup code is claimed by that document.
