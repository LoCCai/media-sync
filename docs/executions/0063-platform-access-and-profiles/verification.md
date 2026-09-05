**English** | [中文](verification.zh.md)

# Verification

Fresh fetch confirmed clean HEAD=origin/main `cc3ab9341636d45fb8a890829f68be982a70a5b7`, divergence0 0. Source audit only; no production/platform requests, credentials or browser interaction. One guessed creator_input.py path did not exist; actual capability/policy files were found with rg. No new tests at plan freeze; prior0062 test results are historical, not inherited. Actual implementation failures, final frozen-source regression, packaging, skips and publication will be recorded here.

## Implementation checks and actual failures

- Frozen plan committed as `c75c5ed` before source edits. Public GitHub API source discovery hit shared-IP rate limits; fixed raw sources remained available, no repeated API retry or platform requests.
- Tieba new parser/private-frame69 and real locked get/HTTP32 checks passed; final agent subset221 passed/3.98s. Wider Cookie selection271 passed/1 failed/35.65s exposed an old four-platform capability assertion. Root updated it to five, then API/capability68 passed/24.38s, including private save, failed replacement and no secret in database/operator outputs.
- KS new isolated module and real locked-method/browser-transport tests65 passed/1.87s; independent same selection65 passed/1.72s. Ruff exception-style/closure-binding findings in tests were corrected; no product test failure in that subset.
- Zhihu initial72 passed/12 failed because synthetic self responses used pre-read `json=` bodies and real `iter_raw` raised StreamConsumed. Explicit ByteStream fixtures corrected this, then84 passed/5.17s. Tests execute the locked client/get/get_creator_info/help.sign and local Node with the locked signing JS; only HTTP/browser boundaries are synthetic. No platform call or real Cookie.
- Root initial shared runner/repository/API136 passed/18.40s; new identity/API85 passed/21.53s. Test import/line-length findings were formatted and rechecked, not treated as aggregate success merely because a later command passed.
- Actual script-mode worker repro first4 failed/5.74s: success became result_invalid and platform _LookupFailure became temporary due to duplicate __main__/canonical types. A later combined snapshot41 passed/5 failed/28.02s included these four plus a URL-input test's obsolete422 expectation (now fixed400 platform validation). An attempted combined patch had a mismatched API line and applied nothing; corrected patch and canonical alias yielded4 passed/5.39s. The failing runs remain recorded, not overwritten or hidden by retry.
- Independent review also reproduced valid long KS/Zhihu IDs rejected by API max20. API max255, platform-specific bounds, dynamic UI label and KS128/Zhihu255 success/oversize rejection checks correct the omission. Escaped lone-surrogate nicknames now fail before framing/storage; a valid Unicode surrogate pair still succeeds.
- After these final source changes, worker/shared runner/API/Zhihu selection178 passed/28.64s,1 existing Starlette/httpx warning. Four-platform real two-hop process suite17 passed/27.54s; no raw Cookie in argv/environment/public output and account exclusion released only after process cleanup. These selections overlap and are never summed.

Static checks at source freeze: Ruff check PASS, format336 files unchanged, mypy133 source files PASS, compileall PASS; uv lock62 packages unchanged and both locked clean checkouts PASS. Web then passed671, Svelte0 errors/0 warnings, production build7.39s and formatting PASS; later account-page wording and Web revalidation are recorded separately. Complete Python directories were launched only after application-source freeze; their exact results and package audit follow below. No current Linux container, real PostgreSQL, platform/CDN/Emby/Jellyfin or production supervisor claim.

## Complete-directory regression and environment boundaries

All three complete directories started after final application-source freeze. Initial unit:3565 passed,2 failed,2 skipped,1 existing warning/296.33s. The old Weibo test still asserted unsupported for newly supported KS/Zhihu; the runner correctly entered credential validation and returned auth_expired. Only this test's capability/missing-credential expectations changed, then its full file passed49/1.03s. Application source and contract/integration tests did not change. The complete-unit rerun is recorded separately; the first failing run is not reported as passing.

| Directory command | Actual result | Local report |
| --- | --- | --- |
| `python -m pytest tests/unit -q --tb=short` (initial) |3565 passed,2 failed,2 skipped /296.33s|`artifacts/final-unit.xml`|
| `python -m pytest tests/contract -q --tb=short` |890 passed,2 skipped /410.66s|`artifacts/final-contract.xml`|
| `python -m pytest tests/integration -q --tb=short` |999 passed,33 skipped /359.22s|`artifacts/final-integration.xml`|
| `python -m pytest tests/unit -q --tb=short` (corrected old assertion) |3567 passed,2 skipped /272.83s|`artifacts/final-unit-rerun.xml`|

The final three disjoint Python directories total **5456 passed,37 environment skips**, with1 existing Starlette/httpx warning in unit. Initial failures and overlapping selections are not included. Final unit report SHA256: `f78b055692fd32ec990f4f536dadfb30b122f351e2d0de74ebe57ff33bb2cf91`. No later Python application/test edits; contract/integration remain valid complete runs of the same frozen application and their unchanged tests.

Actual execution uses `.venv/Scripts/python.exe` from the repository root, adding `--junitxml=docs/executions/0063-platform-access-and-profiles/` plus the table's report path. Raw JUnit stays in local docs and is Git-ignored by the existing artifacts policy; reproducible commands/results are committed. Initial unit/contract/integration report SHA256 values are respectively `81dd59cf0746561d87542c91a6c6c4e202f4399891bd93f69fbbab31412b3512`, `2da2c3d9385e532d3b72ca1707f3fbe7a3e1fd8f2e95ed0382e2ca94d97cd9c6`, `2b17dd482b807f29408c7b9728d700ea6ae7f2c841f9619dcdc1889007581ed3`. Timestamp/duration changes naturally change hashes on rerun.

Docker is unavailable and `MEDIA_SYNC_TEST_POSTGRESQL_URL` is unset. Integration skips32 real PostgreSQL checks and1 POSIX launcher test; unit skips2 POSIX durability/permission checks and contract skips2 POSIX launcher/permission checks. Windows private-process tests do not qualify native Linux permissions. Current Linux image, real PG races, platform/CDN requests, live login/capture/archive, native Emby/Jellyfin playback and production supervisor are all NOT_RUN. The prior failed Bili canary was neither retried nor relabeled successful.

## Frozen application packaging and static gates

- Independent `uv build` used a fresh0063-specific temporary directory, building sdist then wheel from sdist. Both packages contain147 application Python files matching frozen workspace bytes, with missing/extra/mismatch all0. Application tree SHA256: `55b67aa53417d19993af387047d7efcd2c2914b2788e5f0a6423c5d157993d63`.
- Wheel:154 files,646649 bytes, SHA256 `370e80932db83f2c74d615fd0a19f1bae518afd979f0cac0c3b99cc93a6b7d3e`; sdist:1091 files,2630371 bytes, SHA256 `96a0a90591eaace441584f3ef71875596d25eed79c41c4a791d8420eff75177d`. All154 RECORD entries, Mako bytes, Python `>=3.11,<3.14`, CLI entry and dependency metadata passed. No duplicate/casefold collision/link/special/unsafe member paths.
- The3 private-name candidates matched two docs/archive source documents and web/routes/library source bytes, not runtime data. This is member-name/source auditing, not a comprehensive content-secret scan. The audit script initially selected uv's generated .gitignore as tar and later flagged those names; corrected selection passed with no build-product defect.
- Named-tree digest sorts paths ordinally, concatenates UTF-8 `path + NUL + SHA256(bytes) + LF`, then hashes; application paths are relative to src. Whole-wheel tree: `a1cfd2808164869a1bc9351314320d6d7b05ed8360545558e4edd690f9777f62`; whole-sdist tree: `e0ec899519bfcd4dbd391f0cea628cf8d71f9e017f629054acae96f7572ba13a`. Packages are frozen application snapshots excluding later unit-assertion/account-page wording/doc updates, not release attachments or deployment proof. Root's final independent147-file application digest matched exactly. An initial PowerShell culture-dependent sort differed; Ordinal ordering matched the package audit, with no source drift.
- After correcting the old unit assertion, `ruff check src tests scripts`, `ruff format --check src tests scripts` (336 files), `mypy src/media_sync` (133 source files), and `python -m compileall -q src tests scripts` passed again. Initial docs check passed642 Markdown files; final additions are rechecked. Pre-staging fresh fetch still showed only the local plan commit ahead1/behind0.

## Final user-facing wording and Web revalidation

Read-only final review found old two-platform account-page copy inside the four-platform condition, plus deployment sections still claiming Tieba unavailable/five profile platforms pending. Both language guides and the account-page wording are corrected, including the existing UI-wiring assertion. Earlier Web results remain an earlier snapshot, not post-edit proof.

Final commands in web ran sequentially with immediate nonzero exit: `pnpm test` (671 passed/1.11s), `pnpm check` (0 errors/0 warnings), `pnpm build` (PASS,9.36s), `pnpm format:check` (PASS). Vite emitted plugin timing notices, not build failures. No later Web source/test edits. No browser qualification or platform requests this round. Final docs/diff gates and publication are recorded below.

## GitHub publication

Bilingual frozen plan `c75c5ed` and implementation `34a634896dd06d8e2d54145f960bde36f50f0ead` were normally pushed to origin/main at https://github.com/LoCCai/media-sync. A fresh fetch then confirmed HEAD=origin/main at that full implementation SHA, divergence0 0 and a clean worktree. Implementation staging contained only46 task source/test/Web/doc files; no credentials, runtime data, raw local JUnit, build outputs or temporary packages. Upstream/dependency/schema inputs are unchanged.

Before the implementation commit, `python scripts/check_docs.py` passed642 Markdown files, alongside `git diff --check` and staged-diff validation. This publication confirmation is a separate bilingual documentation-only commit, followed by another normal push and fresh-fetch consistency check. It changes neither frozen-source tests nor package proof and deploys no service. The original seven-platform goal remains active; remaining validators/profiles/avatars/media capabilities and real Linux/platform qualification still require progress.
