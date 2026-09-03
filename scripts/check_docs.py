"""Validate links and structural invariants in project documentation.

Checks per Markdown file:
  - local link targets exist;
  - at most one H1 heading;
  - at most one language-switcher line, and it must sit at the very top;
  - no duplicate H2 headings.
For every ``<name>.zh.md`` with an English counterpart ``<name>.md`` (and vice
versa) the H1/H2 heading structure must match across the two editions.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
H1_RE = re.compile(r"^# (.+)$", re.MULTILINE)
H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)
SWITCHER_HINTS = ("**English** |", "[English](")
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


def _strip_code_blocks(text: str) -> str:
    """Blank out fenced code blocks so shell comments never look like headings."""

    return FENCE_RE.sub(lambda match: "\n" * match.group(0).count("\n"), text)


def markdown_files(root: Path) -> list[Path]:
    files = sorted(root.glob("*.md"))
    files.extend(sorted((root / "docs").rglob("*.md")))
    return [path for path in files if path.is_file()]


def _structure(text: str) -> tuple[list[str], list[str]]:
    prose = _strip_code_blocks(text)
    return H1_RE.findall(prose), H2_RE.findall(prose)


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    structures: dict[Path, tuple[list[str], list[str]]] = {}
    for source in markdown_files(root):
        text = source.read_text(encoding="utf-8")
        relative = source.relative_to(root)
        structures[source] = _structure(text)

        for match in LINK_RE.finditer(text):
            raw_target = match.group(1).strip().strip("<>")
            if (
                not raw_target
                or raw_target.startswith("#")
                or raw_target.startswith(("http://", "https://", "mailto:"))
            ):
                continue
            relative_target = unquote(raw_target.split("#", 1)[0])
            target = (source.parent / relative_target).resolve()
            if not target.exists():
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"{relative}:{line}: missing link target {raw_target!r}")

        h1_headings = structures[source][0]
        if len(h1_headings) > 1:
            errors.append(f"{relative}: duplicate H1 headings ({len(h1_headings)}): {h1_headings[:3]} ...")

        switcher_lines = [
            line_no
            for line_no, line in enumerate(text.splitlines(), start=1)
            if any(hint in line for hint in SWITCHER_HINTS)
        ]
        if len(switcher_lines) > 1:
            errors.append(f"{relative}: multiple language-switcher lines at {switcher_lines}")
        elif switcher_lines and switcher_lines[0] != 1:
            errors.append(f"{relative}:{switcher_lines[0]}: language switcher must be the first line")

        duplicate_h2 = [name for name, count in Counter(structures[source][1]).items() if count > 1]
        if duplicate_h2:
            errors.append(f"{relative}: duplicate H2 headings: {duplicate_h2}")

    for source, (h1, h2) in structures.items():
        counterpart = (
            source.with_name(source.name[: -len(".zh.md")] + ".md")
            if source.name.endswith(".zh.md")
            else source.with_name(source.stem + ".zh.md")
        )
        if counterpart in structures:
            other_h1, other_h2 = structures[counterpart]
            if len(h1) != len(other_h1) or len(h2) != len(other_h2):
                errors.append(
                    f"{source.relative_to(root)}: heading structure diverges from "
                    f"{counterpart.relative_to(root)} "
                    f"(H1 {len(h1)} vs {len(other_h1)}, H2 {len(h2)} vs {len(other_h2)})"
                )
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = validate(root)
    if errors:
        print("Documentation validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Documentation links OK ({len(markdown_files(root))} Markdown files checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
