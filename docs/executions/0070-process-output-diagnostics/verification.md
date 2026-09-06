[**English**](verification.md) | [中文](verification.zh.md)

# Verification

Status: offline release gates pass on the final frozen source.

## Passing evidence

- Final complete Python coverage was executed in three isolated groups and totals `6924 passed, 40 skipped` after removing one intentional eight-test helper overlap: unit `4604 passed, 3 skipped`, contract `1085 passed, 2 skipped`, integration `1235 passed, 35 skipped`. The raw unit command reported `4612 passed, 3 skipped in 511.42s`; contract completed in 489.20s and integration in 422.79s. The only warning class was the existing Starlette/httpx deprecation.
- Final process-output/login focus: `255 passed, 1 skipped`. Output-capture alone passed 51 tests, and the two pinned MediaCrawler-format cross-process cases passed independently. The skip is the POSIX-only virtual-environment launcher on Windows.
- The earlier exact-delivery race/recovery focus passed 255 tests; after the final stale supervisor-lease fix, all 17 delivery API tests and a 14-test lease selection also passed. Migration/database/package-resource focus passed 52. These selections overlap the complete coverage and are not added to its count.
- Final Web suite: 25 files / 781 tests. Prettier passed, Svelte reported zero errors and zero warnings, and the production build passed.
- Ruff lint passed; the final whole-repository Ruff format check reported 1101 files already formatted; strict mypy passed 149 source files; compileall passed; `uv lock --check` resolved 62 packages; both pinned upstream checkouts passed; `git diff --check` passed.
- The post-fix wheel/sdist each contain all 165 application Python files byte-identical to the workspace, with required migration/Mako resources and zero actual `.env`, database, private-key, credential, runtime log/profile/output, build-cache, temporary, VCS/tool-state or link members. `.env.example` and eight versioned JSONL crawler fixtures are templates/test data. Wheel SHA-256: `eaba763d84ce337027cd04cd6f0a6c7fcfad015b240e139a4c61f8e783e3a4cd`; sdist SHA-256: `bc073ab59a56f26ec114cbcedacb041b91f06144119a6e97a9827629d1cc1def`.

The subprocess contracts prove that result/event framing remains parseable; an ambient forged Operation ID is rejected; exact Operation and LoginSession filters return the managed QR events; secret, QR, URL, content, DOM, and private-path sentinels are absent from validated events and raw managed segments; and drop counters remain visible.

## Failures found and corrected

- The first repository-wide run reached 138 passes and exposed 14 isolated-fixture failures in `test_browser_policy_wiring.py`; the fake runtime now supplies its platform login modules and `tools.utils` explicitly. The file then passed 38 tests.
- Review invalidated and stopped two early full runs while code was still changing. The first frozen `-x` run reached 3219 passes before finding stale SystemExit expectations and a synthetic process without the now-required stderr pipe. A following complete run reached 6918 passes before finding stale five-platform Cookie capability and 74-route inventories. The corrected selection passed 112 tests, then the final complete run above passed.
- Independent logging review reproduced a release-blocking issue: actual pinned MediaCrawler log prefixes produced only `policy_filtered`. The shared normalizer fix passed 51 capture tests and real-process QR/creator cases while hostile JSON, HTML, content, Cookie, Authorization, storage, QR, signed-URL and private-path sentinels remained absent from events and raw segments.
- The initial package member denylist falsely matched the legitimate Web `/logs` route. Narrowing the rule to package-root runtime directories produced a clean full audit; no archive member was manually removed or exempted.
- Final cross-feature review found that an exact-delivery observer could poll a crashed supervisor's stale `claimed`/`running` lease forever. The observer now retries only that exact Job, leaving live leases untouched and reclaiming expired leases. Four discovery/pipeline × claimed/running regressions fail on the old loop and pass on the corrected source. A monolithic final run was stopped at 3% to parallelize; an initial isolated unit command then failed collection because it omitted a cross-directory helper. Explicitly collecting that eight-test helper produced the successful final groups above, with the duplicate removed from the unique total.

## Not run

- Current Linux/Docker image qualification.
- Any real QR login or recovery of old failed runs.
- Real creator crawl, CDN retrieval, archive playback, Emby/Jellyfin scan, or supervisor restart.
- PostgreSQL runtime tests when no test database URL is configured.
