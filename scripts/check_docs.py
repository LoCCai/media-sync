"""Validate local Markdown links in project documentation."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
REMOTE_PREFIXES = ("http://", "https://", "mailto:")


def markdown_files(root: Path) -> list[Path]:
    files = sorted(root.glob("*.md"))
    files.extend(sorted((root / "docs").rglob("*.md")))
    return [path for path in files if path.is_file()]


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    for source in markdown_files(root):
        text = source.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            raw_target = match.group(1).strip().strip("<>")
            if not raw_target or raw_target.startswith("#") or raw_target.startswith(REMOTE_PREFIXES):
                continue
            relative_target = unquote(raw_target.split("#", 1)[0])
            target = (source.parent / relative_target).resolve()
            if not target.exists():
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"{source.relative_to(root)}:{line}: missing link target {raw_target!r}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = validate(root)
    if errors:
        print("Documentation link validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Documentation links OK ({len(markdown_files(root))} Markdown files checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
