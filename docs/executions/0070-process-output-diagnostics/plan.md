**English** | [中文](plan.zh.md)

# Plan

## 1. Freeze the evidence and safety boundary

- Trace every stdout/stderr path for the generic MediaCrawler runner and QR-login runner, including the parent protocol readers and child imports.
- Preserve the execution-0068 structured lifecycle events. Add process output only where it supplies missing evidence; never claim that old discarded output can be recovered.
- Define “all logs” as complete coverage of safely classifiable diagnostic output. Reject raw secrets, QR material, user content and arbitrary third-party chatter.

## 2. Implement one bounded capture primitive

- Add a reusable process-output capture module over the existing `LogStore`, selecting the same `state_dir/logs` location used by API, CLI and supervisor.
- Capture child-internal fd 1/2 through a private pipe, decode incrementally and classify line-by-line. Merge upstream stdout/stderr when the surrounding public channels are protocols and retain the original source only when it is trustworthy. Require explicit level/traceback/exception shapes; keyword hits alone never authorize persistence, and JSON/JSONL, HTML/DOM or likely creator-content objects are policy-filtered.
- Enforce the per-run byte/line/line-length limits. Emit summaries and explicit fixed dropped reasons even when no free-text line is retained.
- Reject relative/root log directories and path identity changes; do not follow symlinks or broaden existing store deletion authority.

## 3. Preserve protocol and authorization boundaries

- In the generic crawler, keep stdout as the strict final status/result stream. Authorize capture only through the trusted parent environment and remove the control value before importing upstream code.
- In QR login, duplicate the original stderr for the versioned `EventWriter`, keep stdout for the result frame, and route only upstream child fd output through the private capture pipe.
- Restore descriptors deterministically on success, exception, cancellation and teardown. Capture failures must not change the runner's result, hide its primary error or grant authentication.

## 4. Propagate exact trusted context

- Snapshot the parent `operation_id` and `correlation_id` from validated observability context before starting asynchronous login-reader work.
- Serialize only canonical allowed UUID keys through a dedicated environment variable; the child pops and strictly validates the complete value before upstream import. If any field is invalid, discard the whole propagated context.
- Merge creator manifest identities and login account/platform identities after validation. Manifest truth wins on duplicate fields; never fabricate a login-session UUID.

## 5. Extend the closed event schema

- Add the three process-output event codes, a closed stream field and fixed drop/error values.
- Permit bounded `message` only on `process_output`; run a second policy check at event construction so callers cannot bypass the capture redactor.
- Keep time, writer identity, sequence and persisted/queued/drop semantics owned by the existing `LogStore`.

## 6. Integrate APIs and the log-center UI

- Extend the TypeScript log parser with the new codes, stream, message and drop reasons. Preserve any concurrent exact-subscription-delivery changes in the same files.
- Show a readable safe message for retained output and clear summaries for filtered/dropped lines. Keep unknown values defensive rather than rendering unchecked server text.
- Retain current authentication, filters, bounded pagination, operation links and diagnostic download behavior; no direct filesystem browsing or raw-segment download endpoint is added.

## 7. Verification and adversarial review

- Unit-test safe diagnostic classification and hostile Cookie object, `Set-Cookie`, Authorization, storage-state, QR/base64, signed-URL and Windows/POSIX path cases, plus invalid UTF-8, oversize lines, flood limits, sink refusal and directory safety. The sentinel must be absent both from validated events and raw managed segment bytes.
- Contract-test real child processes: generic result framing remains exact; QR result/event framing remains parseable; diagnostic output reaches managed segments; secrets and private paths do not.
- Test valid Operation correlation, absent context, malformed/mixed/malicious environment values and direct runner invocation without parent authorization.
- Run focused log-store/output tests, MediaCrawler bridge/login contracts, API/frontend tests, Ruff/format, mypy, web type/lint/build as affected, and `git diff --check`. Record exact results later in `verification(.zh).md`; do not predeclare success.

## 8. Closeout and continuation

- Add `progress(.zh).md` only with implemented facts and explicit remaining runners; add `verification(.zh).md` with commands, counts, failures, fixes and `NOT_RUN` rows.
- Use separate bilingual plan and implementation/closeout commits. Push only when the root worktree has passed the agreed gates and the user has requested publication.
- Do not deploy, restart supervisor, retry login or begin production backfill automatically. After deployment, one controlled failed-platform attempt should be inspected through the new log center before selecting a login fix.
