**English** | [中文](verification.zh.md)

# Verification

Fresh fetch confirmed clean HEAD=origin/main `133e461007f92c7dd9444d4dd5e661887c5912d1`, divergence0 0. Both locks are unchanged;0063 tests/publication are historical, not inherited0064 evidence. Source discovery guessed several nonexistent command/preflight/request paths, then located actual policies/application files without writes. Fixed public GitHub source reads succeeded; no platform/production/credential requests.

Actual failures/corrections, frozen-source regression, Web/static/package gates, environment skips and GitHub publication will be recorded individually during implementation. Unrun checks are never marked PASS.

## Implementation checks and actual failures

- Frozen plan committed first as `b60cccb`. DY review found urlencode(None) in signing differs from HTTPX's default empty encoding. Transport now sends the real signer's original query, retaining literal None without inventing/fetching tokens. This proves offline byte equality, not platform acceptance.
- DY initial94 passed/4.26s;13 added boundary cases yielded107 passed/4.34s, independent107 passed/4.19s. Initial Ruff E501/B023 corrected, final formatting/mypy passed, no product-test failures. Tests execute locked get_user_info/get/parameter/help and locked JS in Node. HTTP/browser and the execjs adapter are synthetic boundaries, not full real PyExecJS/browser/platform qualification.
- Tieba initial32 failed,116 passed,2 errors: AST dedent changed whitespace inside a multiline JS literal, and a huge bytes parameter generated an overlong Windows test ID. Preserve source indentation and supply short IDs:149 passed/2.28s. Add rejection when the actual returned dictionary's nickname is mutated: final150 passed/2.18s, independent150 passed/2.06s. The old Tieba Cookie combination251 passed/3.51s overlaps and is not summed. Two mypy Any-return findings fixed with explicit cast; Ruff/format/single-source mypy passed.
- Root shared avatar/identity/API/Cookie/repository selection630 passed/68.64s,1 existing Starlette/httpx warning. Ruff first reported15 line-length/duplicate-branch/fullwidth-character diagnostics, corrected by formatting/equivalent branch grouping/Unicode escapes. Equivalent source formatting/branch edits occurred during that implementation snapshot, so it is not a final-source full gate.
- Six-platform real guardian/worker two-hop and actual script-dispatch selection29 passed/45.72s verifies private Cookie frames, no argv/environment/public-output leakage and locks released only after cleanup. Avatar checks include Tieba bare/timestamp URLs, same-CDN wrong authors, private/mixed DNS, redirects/oversize and old-image retention. API cross-author receipts use another valid portrait, not merely malformed input.
- Initial Web699 passed/0.979s and Svelte0 errors/0 warnings. Shared review covered easy-to-miss independent Cookie copy, old unsupported assertions, Tieba's invalid123 test ID and same-author avatar binding. No production requests or browser actions.

## Frozen-source static, Web and packages

Complete unit/contract/integration directories started only after application/test freeze. `ruff check src tests scripts` passed; `ruff format --check src tests scripts` left342 files unchanged; `mypy src/media_sync` passed135 source files; `python -m compileall -q src tests scripts` passed. `uv lock --check` retained62 packages; `python scripts/check_upstreams.py` verified2 clean locked checkouts. No dependency/lock/schema migration changes.

Final Web commands ran sequentially with immediate nonzero exit: `pnpm test`699 passed/0.917s, `pnpm check`0 errors/0 warnings, `pnpm build`PASS/7.20s, `pnpm format:check`PASS. Vite plugin timing notices are not errors. No later Web source/test edits. Root README/docs now point to current capabilities/verification rather than0055 test totals.

Independent `uv build --out-dir <fresh0064-specific temp directory>` built sdist then wheel from sdist. Both packages contain149 application Python files byte-identical to the frozen workspace, missing/extra/mismatch0. Application tree SHA256 `595b012cc19da2a98137cfbc5a7ed0b4e7a6ccb5c910f82c3cdc0445728eb81b` (ordinal path ordering, concatenate src-relative path+NUL+file SHA256+LF, then SHA256).

- Wheel:156 files,657055 bytes, SHA256 `7a2ebc887f8af0826c6d1b3afc20fcaa2a599fe1ce2a884e071580218c0f1b37`.
- Sdist:1107 files,2669684 bytes, SHA256 `57c2a33f14519c2759b7b8d6e0ede6e2a6b7cd3c6771e248e65e5898c573b839`.
- All156 RECORD hashes/sizes, migration Mako, name/version/Python constraints, dependencies including optional keyring, and CLI entry passed. No unsafe/duplicate/casefold/link/special members. Four private-name candidates matched static bilingual docs/archive and web jobs/library source bytes. This is member/source auditing, not a comprehensive content-secret scan.

Packaged documents are the build snapshot, excluding later docs/README/verification updates, not final release attachments or installation/deployment proof. DY source SHA256 `334ffb0722531fd8aab2de681900478f6813a51fb8c490d882486647ab4bd395`; Tieba `ef33cda5056934c1519535541ddf08a19db95f48602cd67d1bae0c9830345354`.

## Complete directories and environment boundaries

All three final disjoint complete directories passed, totaling **5841 passed,37 environment skips**, plus1 existing Starlette/httpx warning in unit. Overlapping selections are not added again. No later application/test edits; root independently recomputed the149-file application tree and matched the package audit exactly.

| Complete directory | Actual result | Local report |
| --- | --- | --- |
| unit |3875 passed,2 skipped,1 warning /306.36s|`artifacts/final-unit.xml`|
| contract |968 passed,2 skipped /426.83s|`artifacts/final-contract.xml`|
| integration |998 passed,33 skipped /353.59s|`artifacts/final-integration.xml`|

Exact rerun commands from the repository root:

```powershell
.venv/Scripts/python.exe -m pytest tests/unit -q --tb=short --junitxml=docs/executions/0064-douyin-tieba-profiles/artifacts/final-unit.xml
.venv/Scripts/python.exe -m pytest tests/contract -q --tb=short --junitxml=docs/executions/0064-douyin-tieba-profiles/artifacts/final-contract.xml
.venv/Scripts/python.exe -m pytest tests/integration -q --tb=short --junitxml=docs/executions/0064-douyin-tieba-profiles/artifacts/final-integration.xml
```

Raw reports stay in local docs and are Git-ignored by the existing artifacts policy; commands/results are version-controlled. Report SHA256: unit `34481aefc252c5586545da8ce5de6b02ab14f511b5e6cc71fbf85358663a341b`, contract `486e7b8bbbcd500c94fafcc4357a6740cae8c69b1b5ce7d67cee4352cab06b81`, integration `769c48bc7f519a56f18c24b1c80e63070fe262ca469e60385e948051fa76de0c`. Rerun timestamps/durations naturally change hashes. Skips comprise32 real PG checks and5 POSIX permissions/launcher/durability checks, not qualified by Windows substitutes. Final652 Markdown documents and diff checks passed; independent doc review found no unresolved issues. Pre-staging fresh fetch showed only the plan commit ahead1/behind0.

Docker is unavailable and `MEDIA_SYNC_TEST_POSTGRESQL_URL` is unset. Current Linux image/native permissions/durability, real PostgreSQL, platform/CDN bytes, live login/profile/capture/archive, native Emby/Jellyfin playback and production supervisor are NOT_RUN. The previously authorized failed Bili canary was not retried/reclassified. Six profile platforms are not seven-platform workflow completion.
