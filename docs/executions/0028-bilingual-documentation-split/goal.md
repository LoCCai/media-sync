**English** | [中文](goal.zh.md)

# Execution 0028 goal

- Status: Complete for the documentation-language scope; no runtime behavior changed
- Date: 2026-09-02
- Predecessor: Execution 0027 closeout `539395a483f4f368895fb0f35205c903dc2bd43d`
- Scope: Replace every mixed Chinese/English Markdown document with two single-language editions — English keeps the original `<name>.md` path, Chinese becomes a sibling `<name>.zh.md` — without changing any source code, schema or runtime behavior

## Outcome

1. Every Markdown document under the repository root (except generated `.zh.md` outputs) is processed into an English edition at its original path and a Chinese edition at `<name>.zh.md`.
2. Each edition is prefixed with a language switcher linking to its counterpart, and local Markdown links inside each edition point to same-language files.
3. The mixed-language writing conventions (`EN / ZH` inline pairs, label pairs, bold label pairs, vertically duplicated paragraphs) are resolved deterministically by a committed, re-runnable migration tool rather than by hand-editing 124 files.
4. Content that previously existed in only one language (untranslated requirements bullets, research/architecture paragraphs, decisions and upstream notes) is translated so both editions are complete.
5. Validation proves link integrity, English/Chinese file parity, language purity of the English editions, zero loss of language-neutral lines, and no unsplit pairs left in the Chinese editions.

## Acceptance boundaries

- Documentation and the migration tool only; `src/`, `tests/`, `alembic.ini`, `pyproject.toml` and `upstreams.lock.json` are untouched.
- Quoted Git commit subjects inside backticks stay verbatim in both editions; they are historical artifacts, not document prose.
- The migrating workstation has no Python runtime, so `uv run python scripts/check_docs.py` and the usual quality gates are `NOT_RUN` there and must be re-run in the regular environment before pushing.
- Historical `NOT_RUN`/deferred claims are copied verbatim into both editions; no execution boundary is re-qualified.

## Explicitly deferred

Live platform/CDN/Emby qualification, REST/production packaging, multiple `durl` segments and every other product item remain outside this documentation-only execution.
