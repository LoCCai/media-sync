**English** | [中文](release-checklist.zh.md)

# GitHub release checklist (execution 0046)

Run top-down before every public push or tagged release. Every item is checkable offline except the two marked `[host]`, which belong to the Linux deployment host.

## Repository truthfulness

- [ ] `git status` clean; everything intended is committed and pushed (`git log origin/main..main` empty).
- [ ] `uv run python scripts/check_docs.py` passes (all Markdown links resolve).
- [ ] `uv run python scripts/check_upstreams.py` passes (both pinned checkouts clean at locked SHAs).
- [ ] Execution index (`docs/README.md`) rows match reality: no row claims Complete without its verification record.

## Secrets and privacy

- [ ] `git grep -iE "(set-cookie|cookie:|Authorization:)" -- docs src tests` shows only redaction references, sentinels or fixtures — never a real token.
- [ ] No `.env`, `*.sqlite3`, `browser_data/`, or runtime output tracked (`.gitignore` covers them; `git ls-files | grep -iE "\.env|sqlite"` empty).
- [ ] `THIRD_PARTY_NOTICES.md` current: both upstreams, correct licenses, no vendored code.
- [ ] No personal account data, QR images or profiles anywhere in the tree.

## Quality gates (in a synced environment)

- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run mypy --strict src`
- [ ] `uv run pytest -q` — full suite green on the deployment host (record the numbers in the newest execution's verification file)
- [ ] `uv run python -m compileall -q src/media_sync && uv build`

## Release mechanics

- [ ] Version bumped in `pyproject.toml` if releasing a tag; tag annotated with the execution index range included.
- [ ] README current-status section references the newest closeout commit.
- [ ] `[host]` Clean-clone drill: fresh `git clone` → `docs/deployment.zh.md` build → console reachable → one offline smoke (`media-sync doctor`).
- [ ] `[host]` Reminder honored: the Docker image embeds the non-commercial upstream checkout — never push it to a registry.
