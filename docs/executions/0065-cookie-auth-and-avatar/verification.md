**English** | [中文](verification.zh.md)

# Verification

Clean baseline HEAD=origin/main9ac392f98b65a15bc88e6e7faa6b011a1e5744fb, divergence0 0. Read-only path guesses failed then actual modules located with rg. Initial avatar-only draft failed staged EOF-whitespace check before commit; replaced by this scope after independent source discoveries, no application changes before frozen plan. All current checks pending; prior full/live PASS is not inherited.

## Implementation checkpoints and actual corrections

Plan committed first as3ecab22. Shared initial selection700 passed/80.83s plus existing Starlette/httpx warning. This includes exact parser/optional avatar/service/receipt/subscription and old-auth retention; new platform remote modules were verified separately during implementation. Local JUnit artifacts/shared-initial.xml is ignored by existing artifact policy. Root's later import-order-only Ruff correction does not imply a second full run of that snapshot.

Web initially twice1 failed/700 passed: two successive old nickname-only copy assertions in the same test. Updated those assertions to the implemented limited Zhihu avatar and retained KS/DY nickname-only scope. Final701 passed/0.905s after adding explicit seven-platform/cp.api_ph/XHS-boundary assertions. Svelte0 errors/0 warnings, buildPASS7.33s, PrettierPASS; final added assertions change tests only, not built source. Earlier passing Web snapshots overlap and are not summed.

Mid-edit static check observed unfinished agent file diagnostics (27 Ruff,8 mypy); agents corrected their own files. Root's later single import-order Ruff issue was corrected. Current full Ruff checkPASS, format349 unchanged, mypy137 source modulesPASS, compileallPASS. Docs662,2 clean locked checkouts and uv lock62 packagesPASS. Final frozen regression/package/publication follow below; not a full0065 test-directory claim.

## Platform and process checks

- DY final153 passed/1.16s. Initial1 failed/127 passed arose because empty SecretValue is rejected before the adapter, not by its typed failure handler; the test now exercises a nonempty invalid header. Subsequent128-pass snapshot preceded the final contradiction/network-classification checks. Final Ruff/format/mypy passed. Source SHA25689148098135633992c5b7ca9bbacf68fee15a8e65e45daeea7d625136012abad.
- KS initial149 passed/1.87s; final168 passed/1.91s after bounded transport cases, no pytest failure. Source static line-length/type-narrowing/Any-return issues were fixed. Real locked constructor/post, exact CP Cookie/body, one request, raw JSON and returned object mutation/substitution checks pass. Source SHA2566a8d40a0369a7cb903e7fd74d43a3b813b1b2b5743b497f06e34fb0a2f7c8458.
- Independent actual script worker12 passed/15.42s: both platform dispatch paths, canonical typed errors, Cookie solely in stdin, no argv/env/public stdout/stderr disclosure, no unexpected network/files. The first test-harness attempt blocked subprocess/socket too early and interfered with Windows asyncio/Popen initialization; corrected the synthetic guard timing without changing the application.
- The first33-file affected run was **1 failed,1817 passed/173.45s**,1 existing warning: cookie hard-parent-death test observed both PIDs exited but immediate OS-lock acquisition returned false. Original failure is preserved in artifacts/final-affected.xml (SHA256f5c4675d6adba64fea6e95c6d020afec006159fef471065bbbf8c487af93a0e6). Later actual acquisition of that exact failed temporary fixture succeeded and was released. Original node alone1 passed/3.86s; a temporary read-only WinError diagnostic1 passed/2.28s observed expected pre-kill sharing violation32 and successful post-exit acquisition. It did not reproduce the precise transient failure; this does not prove its exact kernel cause.
- Changed only that test's immediate lock assertion to require actual acquisition within5s, following the existing QR hard-parent-death contract. Pre-kill refusal and both child exits remain mandatory; an indefinitely held lock still fails. No production lock/cleanup code changed. Process+script worker recheck22 passed/25.90s. This is a bounded observation correction, not a production lifecycle fix. Final33-file rerun is recorded separately below.

## Final package audit

A first audit completed one build; the audit script needed corrections for semantically equivalent Python range ordering, a known static artifacts/README.md path, and a newline-containing py.typed file. These were audit assumptions, not product defects. A transient agent service error did not trigger a duplicate build. After the test-only lock correction, a new dedicated final temp build was audited successfully, including that final test byte content.

Final directory: C:/Users/LoCCai/AppData/Local/Temp/media-sync-0065-final-package-audit-c075a40a18d840029c75b0d6739ae4a9. `uv build --out-dir <fresh directory>` builds the wheel from the sdist. Both include151 application Python files with missing/extra/byte mismatch0. Application tree SHA256 **1017ce5f18967035bf64d58702e19b547853b3e741a9e813956d8f8d0d8957a5**, independently recomputed by root after the test change: ordinal-sort src-relative paths, concatenate path+NUL+lowercase file SHA256+LF, then SHA256.

| Final package | Size / members | SHA256 |
| --- | --- | --- |
| wheel |662935 bytes /158|3700a52ebeae8be70d1518aa7f6bbb0800e10f7b6afa5f9613856c2a4182b6db|
| sdist |2709558 bytes /1124|227fbd28ce46a6b7efac69db282fc844421cb3e4491779e7bd823d2c4f62cdeb|

All158 wheel RECORD hashes/sizes, safe unique non-link/non-special members, source bytes, name/version/Python semantics,11 declared dependencies including optional keyring, CLI, py.typed and migration Mako passed. Five private-name candidates are inspected static artifacts/docs/archive and web jobs/library source, not runtime data; not a comprehensive content-secret scan. Sdist documents are the snapshot before these final verification/publication additions, not final release attachments or installation/deployment proof.

Docker unavailable; MEDIA_SYNC_TEST_POSTGRESQL_URL unset. Current Linux image/native permissions/durability, real PostgreSQL, platform/CDN bytes, live Cookie/login/profile/capture/archive, native Emby/Jellyfin playback and supervisor are NOT_RUN. No live request, user Cookie, production retry/deployment/supervisor restart. All seven self implementations do not establish seven-platform real workflow completion.

## Final frozen affected regression

After the test-only observation correction, the same complete33-file affected selection passed **1818 tests /187.54s**, no skips, one existing Starlette/httpx warning. This spans relevant unit/contract/integration Cookie/profile/avatar files, not the entire repository suite. No later application/test edits. Report artifacts/final-affected-recheck.xml SHA256 `616caaea2fa0679ee40aa3481c11a4e7b49294f8b18551940dca79904128df3b`; earlier failed report remains separate. Do not sum earlier overlapping module, process or shared selections.

Reproduce from repository root:

```powershell
$task0065Tests = @(rg --files tests | Where-Object { $_ -match '(cookie|creator_profile|creator_avatar)' } | Sort-Object)
.venv/Scripts/python.exe -m pytest @task0065Tests -q --tb=short --junitxml=docs/executions/0065-cookie-auth-and-avatar/artifacts/final-affected-recheck.xml
```

Final full Ruff check/format, mypy137 modules, compileall, Web701/check/build/format, docs662/links,2 locked checkouts, uv lock62 packages and diff checks passed at their stated frozen snapshots. Raw JUnit stays locally under docs/artifacts and remains Git-ignored by existing policy; this document versions exact commands/results/failures. No environment skip was hidden as passed; real-platform/OS gates above remain NOT_RUN.

Fresh fetch before commit had plan ahead1/behind0; source and test changes are task-owned, no runtime/credential/upstream changes. GitHub publication will be recorded after the actual normal push and fresh-fetch comparison.

## GitHub publication

Frozen bilingual plan3ecab22 and implementation e149f5059a3a695eebaf5f8ddc12d91084d9550e were normally pushed to origin/main at https://github.com/LoCCai/media-sync without force. Fresh fetch confirmed HEAD=origin/main at that full implementation SHA, divergence0 0 and clean worktree. Only41 task source/test/Web/bilingual-doc files were staged for implementation; no credentials, runtime data, raw JUnit, temporary public checkouts or packages were committed.

This publication record is a separate bilingual documentation-only commit, followed by another normal push/fetch comparison. Application/test sources remain frozen. No install/deployment, real platform request, Bili canary retry or supervisor recovery. Remaining XHS profile, avatar/media breadth and real-environment acceptance stay part of the active original goal.
