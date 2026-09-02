**English** | [中文](verification.zh.md)

# Execution 0028 verification

- Status: Documentation-language scope passes all gates available on the migrating workstation; regular Python quality gates and GitHub push reconciliation remain to be re-run in the usual environment
- Date: 2026-09-02
- Predecessor: `539395a483f4f368895fb0f35205c903dc2bd43d`
- Plan/implementation/closeout: the commits containing this record (self-referential SHAs intentionally left to Git history)

## Environment

Windows 10 (win32 10.0.26200), Git Bash, Perl 5.42.2 (cygwin). No Python/uv runtime is installed on this workstation, so every `uv run ...` gate is recorded as `NOT_RUN` below rather than silently skipped.

## Implemented evidence

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Corpus feasibility | `perl .tmp_analyze.pl .` (session temp; logic folded into the committed tool) | 0 | 124 files; 3371 lines with exactly one valid inline boundary; 0 multi-boundary lines; 21 special lines |
| Migration tool dry-run | `perl scripts/split_bilingual_docs.pl --dry-run .` | 0 | Final report: 3933 inline splits, 356 label-pair heads, 531 vertical pair units, 173 unpaired English units (kept in both editions), 6 unpaired Chinese units (translation gaps, fixed manually) |
| Migration write | `perl scripts/split_bilingual_docs.pl --write .` | 0 | 124 English editions rewritten in place; 124 Chinese editions created |
| Link + parity + purity | `perl .tmp_validate.pl .` (session temp; ports the `scripts/check_docs.py` link contract and adds parity/purity) | 0 | `checked 128 en + 128 zh markdown files — all link, parity and purity checks passed` |
| Neutral-line preservation | session Perl scan comparing every CJK-free, pair-free source line against both editions | 0 | `checked 4490 neutral lines, lost 0` |
| Unsplit-pair residue | session Perl scan for remaining `EN / ZH` boundaries inside Chinese editions | 0 | 1 line: `Emby / Jellyfin` — a legitimate English product phrase, intentionally kept |
| Scope audit | `git status --short` | 0 | Only `*.md`, `*.zh.md`, `scripts/split_bilingual_docs.pl` and removed session temp files changed; `src/`, `tests/`, `alembic.ini`, `pyproject.toml`, `upstreams.lock.json` untouched |

## Test and quality gates

| Check | Command | Result |
| --- | --- | --- |
| Documentation links (regular gate) | `uv run python scripts/check_docs.py` | `NOT_RUN` on this workstation (no Python runtime); must pass before push. The Perl gate above implements the same link contract over the same file set |
| Ruff, format, mypy, compileall, build | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy --strict src`; `uv run python -m compileall -q src/media_sync`; `uv build` | `NOT_RUN` on this workstation; no Python file was modified by this execution, so these gates cover pre-existing code only |
| Complete suite | `uv run pytest -q` | `NOT_RUN` on this workstation; no source change is claimed |
| Upstream locks | `uv run python scripts/check_upstreams.py` | `NOT_RUN` on this workstation; `upstreams.lock.json` and `.upstream/` untouched |

## Git reconciliation

Plan, implementation and closeout are three commits on `main` following the repository's start/close/closeout convention. The execution 0028 index row and journal summary are part of these commits. Local `main`, `origin/main` and GitHub must be reconciled by the push recorded after this section.

## Live and regular-environment qualification

| Row | Result |
| --- | --- |
| `uv run python scripts/check_docs.py` over the 256-file bilingual layout | `NOT_RUN` on this workstation; required before push |
| Full Python quality/build/test suite | `NOT_RUN` on this workstation; no source change is claimed |
| GitHub push and reconciliation | Attempted after the closeout commit; see the session record for the outcome |

Offline documentation evidence cannot imply any of the `NOT_RUN` rows above.
