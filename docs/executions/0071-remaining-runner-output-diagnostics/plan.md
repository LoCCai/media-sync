**English** | [中文](plan.zh.md)

# Plan

## 1. Freeze the inventory and trust boundaries

- Trace the exact process and stream topology for `CookieLoginProcessRunner`, `MediaCrawlerCreatorProfileProcessRunner`, `MediaCrawlerDetailProcessRunner`, `creator_avatar_worker.py`, `SubprocessProbeRunner`, `FFprobeMediaProbe`, and `FFmpegStreamCopyMuxer`, including mux/remux/concat call sites and the asset-download application boundary.
- Classify every stream before editing: Cookie/profile guardian and worker stdout use bounded four-byte-length JSON frames; detail child stdout is a bounded ASCII JSON result frame; avatar stdout is raw PNG; ffprobe/ffmpeg stdout is parser input. None is free-text diagnostic input.
- Record that in-process HTTP, DNS and filesystem streaming have no child-process output. They receive closed lifecycle events only, never request/response bodies or media bytes. Record separately that guardian stderr is currently an unread pipe and must not be used to relay or retain worker diagnostics.
- Keep checkout, prefetch, browser-version and readiness probes out of scope unless they have both a demonstrated evidence gap and an exact trusted work identity. The inventory, not subprocess existence alone, determines capture eligibility.

## 2. Generalize protocol-safe capture

- Reuse `capture_current_process_output`, `ProcessOutputCapture`, `log_environment_for_child`, and the existing managed `LogStore`; preserve the current classifier, independent event validation, byte/line bounds and fixed drop counters.
- Add the smallest single-diagnostic-stream mode needed by helpers whose stdout must remain owned by a protocol or parser. It may drain approved stderr without attaching the existing two-stream reader to stdout, changing stdout consumption, or widening free-text event fields.
- Keep capture parent-authorized through the validated child environment and remove its control envelope before importing or calling upstream code. Missing, forged or malformed authorization leaves direct invocation quiet.
- Restore Python and native file descriptors, close the capture writer, drain the reader and emit summaries before writing any result frame or PNG. A capture setup, reader, classifier, store or flush failure remains best effort and cannot replace the primary result or modify deadlines, cancellation and complete-tree shutdown.

## 3. Cover Cookie validation and creator profiles

- In the locked Cookie worker, enter capture only around `_verify_remote`; pass the request Cookie to the redactor only as an in-memory known secret. Restore descriptors before `_emit` writes the worker result. Do not capture or serialize the Cookie request, response JSON/HTML/body, browser/session state or remote identity object.
- In the locked creator-profile worker, capture only the platform lookup around the selected adapter call. Treat Cookie values, secret creator references, returned nicknames, avatar URLs, platform identifiers and arbitrary metadata as non-log data even when an exception embeds them.
- Keep guardian and worker four-byte-length framing byte-exact. Do not redirect logs to guardian stderr: it is not drained today, so writing there could deadlock and cannot serve as a safe evidence path.
- Preserve existing remote-proof semantics, profile merge rules, timeout/cancellation behavior and persistence. Logging success cannot authenticate an account or authorize a profile update; logging failure cannot turn a successful or failed business result into another outcome.

## 4. Cover detail and media-address resolution

- In `detail_runner.py --child`, capture only around `_execute_child`, where the exact detail and media locators are resolved. Exit capture and restore stdout before `_emit_child_frame` writes its bounded protocol result.
- Mark account Cookie, secret content reference and every resolved or backup media address as known/high-risk material. Never retain raw detail JSONL, base64 result content, response JSON/HTML/body, creator/content fields, headers, locator queries or signed URLs.
- Propagate only validated local account/subscription/platform identities and an exact asset identity when the authoritative lazy-refresh caller possesses one. The detail request itself is not authority for arbitrary context, and duplicate fields cannot override local truth.
- Preserve exact-detail authority checks, one-time refresh selection, timeout and cleanup behavior. Diagnostics cannot make a locator valid, authorize a different content ID, trigger a retry or change the returned refresh disposition.

## 5. Cover download, probe, avatar and remux helpers

- At `_PerAssetDownloadRunner`/`AssetDownloadService`, begin diagnostic binding only after the authoritative `_begin` transition returns the exact asset-download Job and asset. Add closed phases/outcomes for in-process resolve, HTTP/DNS, streaming, validation and publication only where they explain an existing result; never include URLs, headers, addresses, filenames, response data or media bytes.
- For `FFprobeMediaProbe` and every `FFmpegStreamCopyMuxer` probe/mux/remux/concat path using `SubprocessProbeRunner`, preserve bounded stdout exclusively for the current parser and capture only bounded policy-approved stderr. Do not log argv, concat scripts, input/output paths, signed locators or ffprobe JSON.
- In `creator_avatar_worker.py`, wrap only remote retrieval and image decoding with current-process capture, then fully restore stdout before writing the PNG. The URL received on stdin and the fetched/decoded bytes never become diagnostics; failed capture must retain the existing avatar fallback/keep-old behavior.
- Exclude generic downloader HTTP/DNS work and helpers that expose only binary/protocol output from free-text capture. Closed lifecycle evidence is sufficient when there is no independently safe human diagnostic stream.

## 6. Preserve exact correlation and log-center behavior

- Extend `encode_process_output_context`/`decode_process_output_context` only for the canonical UUID keys proven necessary by the inventory. Keep a versioned closed object, reject duplicates/extras/noncanonical values and discard the entire envelope when any supplied field is invalid.
- Bind Cookie/profile events to their trusted Operation/account/platform; bind detail to trusted account/subscription/platform and available asset; bind download/probe/remux/avatar events to the exact Job/asset/account/creator facts owned by the invoking application. Local authoritative facts win, and no login-session, Job, Run, asset or creator identity is invented.
- Reuse the closed `process_output`, `process_output_summary` and `process_output_dropped` schema, adding only closed module/phase/action/stream values that are necessary to distinguish these boundaries. Never add arbitrary metadata or a raw-output field.
- Extend authenticated APIs and the Chinese log center only where the new closed values require safe labels or filters. Keep pagination, encoding, Operation links and defensive unknown handling; do not add raw-segment download, filesystem browsing or unchecked server-text rendering.

## 7. Run adversarial and cross-process verification

- Unit-test the single-stream adapter, descriptor restoration, bounds and sink failure. Inject raw Cookie/Authorization, `Set-Cookie`, QR/base64, signed URLs, upstream JSON/JSONL, HTML/DOM, request/response bodies, creator metadata, media bytes and Windows/POSIX private paths; each sentinel must be absent from validated events and raw managed segment bytes.
- Execute real guardian/worker and detail/avatar children. Assert four-byte frames, detail result bytes, ffprobe parser output and avatar PNG are byte-exact; captures close before protocol emission; guardian stderr receives no diagnostics; stdout/stderr floods, invalid encoding, oversize lines, timeout, cancellation and early exit do not deadlock.
- Prove exact and absent context for Cookie, profile, detail and download paths, including extra/duplicate/malformed/mixed envelope values, direct invocation and concurrent attempts. Prove log-store rejection or an unavailable state directory leaves every business result, durable transition and retry decision unchanged.
- Run focused output-capture, Cookie/profile/detail, download/probe/mux/avatar, API and Web tests; then the affected Ruff/format, strict mypy, Web type/lint/build, full Python groups and `git diff --check`. Record exact commands, counts, skips and failures later; do not predeclare success or live qualification.

## 8. Close out without overstating qualification

- Add `progress(.zh).md` only after implementation, describing exact wired and excluded boundaries. Add `verification(.zh).md` with commands, counts, failures, fixes and explicit `NOT_RUN` rows; keep both language versions semantically aligned.
- Separate implementation and closeout history, and publish only after the root worktree passes agreed gates and the user authorizes publication. Planning does not authorize deployment, production inspection, supervisor restart or a platform retry.
- State prominently that process diagnostics cannot reconstruct old discarded output and do not fix QR scanning. After deployment, only a separately authorized controlled attempt can produce evidence for selecting a real platform fix.
- Continue the seven-platform capture/download/archive/playback objective independently. Do not convert offline diagnostic tests into live Cookie, profile, detail, CDN, download, Emby/Jellyfin or QR PASS rows.
