**English** | [中文](verification.zh.md)

# Verification

At plan freeze HEAD=origin/main=d600ed5 and worktree clean. No production or login actions.

## Final source evidence

- [Final selection](artifacts/verify_final_log_center.py): **356 passed, 1 warning /122.43s**, no skips. Store, API/diagnostic/config, CLI, lifecycle, real child channel/session binding, exact login-failure association, operator auth and supervisor. Warning is existing Starlette/httpx TestClient deprecation.
- [Real API-to-TypeScript contract](artifacts/verify_api_web_log_contract.py) and [in-memory helper](artifacts/verify_api_web_log_contract.cjs): PASS. Actual migrated DB, operator authentication, persisted segments and real frontend controller/download sanitizer. Four anonymous APIs=401; authenticated=200/no-store; anonymous HTML /logs and /jobs=303; /logs accepted after login. Preserves 200 control events, 64 subjects, truncation flags, microseconds and writer health; private sentinels absent. No browser click or live-platform acceptance claim.
- Web: 24 files/767 passed in1.36s; check0errors/0warnings; build8.91s; Prettier PASS. Includes49 log-controller cases and the new login-return case. Earlier765/766 totals are superseded, not cumulative.
- Ruff check/format374files, mypy145source files, compileall, upstream pins, uv lock, docs694Markdown and git diff checks PASS. Docs rechecked before commits.
- Final source packages in system Temp/media-sync-0068-final-4207a9834c364c93b8d511145564a2e9: wheel/sdist contain160application Python files byte-equal to checkout, verified by0066 check_package_sources.py. Wheel SHA256 b11fbebccdfb2e483ed8e46b0a7e04bf4d64815feef0642865651eef54027953; sdist d1d7bd683921d059f1dfd04a47c52e3eb1587ba901f9b33e47599b2907ed3dc5. Only docs/test tooling changed afterward: source-qualified packages, not final documentation snapshot. No installation/deployment.

## Earlier runs and corrections

- [Broad snapshot](artifacts/verify_log_center.py):2531passed,12skipped,3failed/834.23s. It began before final store shutdown fixes. Three old FixedRunner test stubs lacked diagnostic_hook, producing unexpected-error classification. The updated stub asserts the hook and emits a real stage through actual service→store→API→diagnostic; all45login-diagnostic tests then passed and are included in final356. Do not call the broad snapshot final all-green or sum overlapping selections.
- Broad skips: one POSIX venv launcher and eleven PostgreSQL races without MEDIA_SYNC_TEST_POSTGRESQL_URL. NOT_RUN, not passed. Historical six-thousand-plus full suite was not rerun.
- Initial API run3failed/47passed: new fixture used nonexistent Operation state failed; fixed to failed_retryable. Initial CLI2failed/93passed: old fake constructor/exact-kwargs assertions lacked event_sink; now require its callable wiring. All included in final selection.
- Review reproduced idle-close unsealed exit, synchronous idle sealing bypassing timeout, transient rename poisoning writes and writer-thread start recovery. Deterministic fixes pass; all70store tests included in final selection, including real Windows spawn/filesystem cases. No relaxed capacity/schema/lifecycle checks.
- Login-agent295passed/119.63s and lifecycle207passed/14.82s overlap final evidence. Login includes53new cases and real offline child→service→sealed log success/timeout. Strict v1 still only schema_version/status; telemetry cannot authenticate, forge subjects or leak raw upstream output.
- Final cross-layer review found missing /logs login-return allowlists; both sides and exact-route tests fixed. Subsequent auth/API70passed/27.48s. Earlier310/311 final-selection runs are superseded by356.
- Local JUnit files remain in artifacts but are Git-ignored; commit reproduction scripts and this bilingual sanitized record. No production secrets or trace copies.

## Live and residual boundaries

Production evidence remains0067 read-only inspection: DY/KS/Tieba/WB upstream_browser_timeout, Bili/XHS/Zhihu saved authenticated. This round: no production browser operation, retry, download, deployment or supervisor restart. Current Linux image, live QR/crawl/CDN/playback and PostgreSQL remain NOT_RUN; historical absent stages cannot be reconstructed.

[Usage](usage.md) discloses bounded retained pages, process counters, concurrent-append omissions, crash-open non-reclamation and excluded raw output. This is safe structured evidence, not all arbitrary dependency messages or full exception stacks. The separately reproduced older Windows exporter directory-pin weakness is recorded for follow-up, not claimed fixed here.

## Git publication

Frozen plan bfeb43f. Fresh pre-push fetch confirmed origin/main still d600ed5cdf5763a172e1f5b1dd82346652690041, no concurrent remote changes. Bilingual implementation commit and ordinary push; exact published revision/remote equality follow in a docs closeout. Overall goal remains active.
