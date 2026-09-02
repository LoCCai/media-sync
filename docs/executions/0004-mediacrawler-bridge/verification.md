**English** | [中文](verification.zh.md)

# Execution 0004 verification

- Verification date: 2026-08-30
- Environment: Windows, Python 3.11.8, pytest 8.4.2
- Network/account policy: locked-checkout inspection, offline fixtures and fake subprocesses only; no platform request, browser or real account

## Final quality gate

| Check | Command | Result |
| --- | --- | --- |
| Locked dependencies | `uv sync --all-groups --locked` | PASS — 58 resolved, 43 audited |
| Lint | `uv run ruff check .` | PASS — all checks passed |
| Format | `uv run ruff format --check .` | PASS — 95 files |
| Strict types | `uv run mypy src/media_sync` | PASS — 40 source files |
| Full offline suite + coverage | `uv run pytest --cov=media_sync --cov-report=term` | PASS — 249 tests in 65.16s, 80% total |
| Focused bridge/recovery gate | `uv run pytest tests/contract/test_mediacrawler_bridge.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_checkpoint_fencing.py tests/integration/test_mediacrawler_cli_ingest.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_secret_sinks.py tests/unit/test_security.py -q` | PASS — 142 tests in 50.55s |
| Secret sinks | `uv run pytest tests/integration/test_secret_sinks.py tests/unit/test_security.py -q` | PASS — 33 tests in 0.62s |
| Package | `uv build` | PASS — sdist and wheel built |
| Packaged migrations | `uv run pytest tests/integration/test_packaged_migrations.py -q` | PASS — 2 tests in 3.61s; source and unpacked wheel reach `0002_checkpoint` |
| Documentation | `uv run python scripts/check_docs.py` | PASS — 32 Markdown files |
| Upstream locks | `uv run python scripts/check_upstreams.py` | PASS — 2 exact checkouts |
| Patch whitespace | `git diff --check` | PASS |

All commands exited `0`. The final checks were run after the two-record final-batch rollback/replay regression and old-crawl continuation protection were added.

## Behavioral and security evidence

- Contract tests cover all seven command policies, versioned fixture schemas, JSONL limits and normalizers. Dry-run always reports `spawned=false` and `live_qualification=NOT_RUN`.
- The real CLI-ingest integration path validates manifest v2, a cryptographic completion receipt and immutable byte snapshots before normalization; only checkout lookup is isolated for the fixture test.
- Author/account/subscription/job/revision/mode/login/item-cap fingerprints are bound. Signed creator references are resolved only in memory and compared to the manifest fingerprint. A mismatch, truncated tail or quarantined semantic record creates no run and advances no checkpoint.
- Secret provenance is explicit: signed/opaque creator inputs arrive as `SecretValue`; a plain URL with ambiguous query or fragment material is rejected. Before receipt publication the parent searches raw UTF-8 bytes and decoded JSON strings for exact known Cookie/signed-reference disclosure, including recognized signature components. A match returns fixed `completion_failed`, writes no receipt, and therefore cannot enter CLI ingestion or SQLite.
- Output validation rejects directory substitution, file replacement, symlink/reparse points, hardlinks, descriptor swaps, unlisted files and size/hash drift. Empty output is accepted only through an explicit parent-authenticated receipt.
- Checkpoint tests cover concurrent CAS, same-timestamp late IDs, independent backfill state, old-to-new partial commits, interleaved newer runs, old sealed-crawl recovery and cursor preservation.
- An injected final `succeeded` failure with two records and `batch_size=1` leaves the first committed batch intact, rolls back all final content/checkpoint/success mutations, then replays the same sealed crawl from the current revision to restore only the missing item.
- Sentinel values are absent from argv, process output, exceptions, manifests, JSON, events and SQLite bytes. Tests resolve only generated dummy secrets.

## Live qualification

| Platform | Login | Creator scan | Media retrieval | Status |
| --- | --- | --- | --- | --- |
| `xhs` | Not run | Not run | Not run | `NOT_RUN` |
| `dy` | Not run | Not run | Not run | `NOT_RUN` |
| `ks` | Not run | Not run | Not run | `NOT_RUN` |
| `bili` | Not run | Not run | Not run | `NOT_RUN` |
| `wb` | Not run | Not run | Not run | `NOT_RUN` |
| `tieba` | Not run | Not run | Not run | `NOT_RUN` |
| `zhihu` | Not run | Not run | Not run | `NOT_RUN` |

Automated fixture and fake-child results prove only the local bridge contract. They do not prove that a platform currently accepts login, creator collection or media access.
