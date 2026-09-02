**English** | [中文](progress.zh.md)

# Execution 0028 progress

- Status: Complete for the documentation-language scope
- Date: 2026-09-02

## Completed

- Corpus analysis over all 124 Markdown files: 3371 lines carried exactly one valid inline `EN / ZH` boundary, zero lines carried more than one, and 21 lines needed special handling — establishing that a deterministic split was feasible.
- `scripts/split_bilingual_docs.pl` implemented with dry-run/write modes, backtick-span masking, first-valid-boundary resolution, label/bold-label handling, run-based vertical pairing, cell-wise table splitting, Chinese link rewriting and language switchers.
- Three dry-run/fix cycles caught and fixed: the label-pair ordering bug (labels never fired), the last-boundary-instead-of-first bug (bold acceptance lines stayed mixed), and a Perl capture-variable bug that dropped `— PASS.` suffixes.
- Final write: 3933 inline splits, 356 label-pair heads, 531 vertically paired units, 124 English editions rewritten in place and 124 Chinese editions created.
- Manual pass: commit subjects restored to both halves of executions 0020–0023 plans; identical pairs (`Ruff / Ruff`, `Pytest cases / Pytest case`, `SQLite sidecars / SQLite sidecar`, `Creator/Detail child shim`) collapsed; the 0009 plan index cell split on its full-width semicolon; the 0009 frozen-contract paragraph given its missing English twin; the ZH navigation links of the journal README rebuilt.
- Translation pass: 34 requirements bullets, both research documents, 11 architecture paragraphs (including splitting one combined translation back into two), 5 decision bullets, upstream notes and scattered label contents translated into the Chinese editions; roadmap phase numbering restored in Chinese headings.
- Journal updated: bilingual-layout note, rewritten documentation rule, execution 0028 index row and summary paragraph in both languages.

## Deviations and decisions

- The migration workstation (Git Bash + Perl 5.42) has no Python/uv runtime, so the documented quality gates could not be executed there; a Perl gate reproduced the link contract and added parity/purity/preservation checks instead. This is recorded as `NOT_RUN`, not as a pass.
- Quoted commit subjects inside backticks remain bilingual in both editions by decision: they are verbatim historical artifacts.

## Remaining

- Re-run `uv run python scripts/check_docs.py`, Ruff, mypy, the full test suite and the repository audit in the regular Python environment before pushing.
- Future milestones must author both editions directly per the updated documentation rule.
