**English** | [中文](plan.zh.md)

# Execution 0028 plan

1. Inventory the corpus: classify every Markdown line by mixing convention (`EN / ZH` inline pair, label pair, bold label pair, vertical paragraph/list duplication, language-neutral command or table evidence) and quantify ambiguity before writing any transformation.
2. Write `scripts/split_bilingual_docs.pl` with `--dry-run` and `--write` modes: backtick spans without an internal boundary are masked so commands and quoted commit subjects cannot break detection; the unique valid inline boundary is resolved per unit; label pairs and bold label pairs are recognized before the general split; vertically duplicated runs pair item-by-item by kind and length; table rows split cell-by-cell; Chinese editions rewrite local links to `.zh.md` and every edition gets a language switcher.
3. Dry-run first, review the full report (vertical pair list, length mismatches, unpaired units, neutral ` / ` lines), fix the tool, and only then write.
4. Post-split manual pass: restore commit subjects that the old convention placed in only one half, collapse identical same-language pairs, repair the five historical translation gaps, and translate the single-language remainder.
5. Validate with a Perl gate implementing the `scripts/check_docs.py` link contract plus parity, purity, neutral-line preservation and unsplit-pair checks, because the migrating workstation has no Python runtime.
6. Update the journal (this directory's README and execution index), create the 0028 four-file record in both languages, and leave `uv run python scripts/check_docs.py` plus the regular quality gates to be re-run before push.

## Risks and rollback

- The transformation rewrites tracked documentation in place; the working tree was clean before the start, so `git checkout -- "*.md"` plus deleting untracked `.zh.md` files is the exact rollback.
- Misclassification risk is bounded by the dry-run report, the four validation gates and the fact that no runtime artifact depends on document prose.
