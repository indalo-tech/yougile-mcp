"""Print the CHANGELOG.md section of a version; exit 1 if it is missing.

uv run --no-project python scripts/release_notes.py 0.2.0
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"


def section(version: str, text: str) -> str | None:
    match = re.search(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|^\[[^\]]+\]: |\Z)",
        text,
        flags=re.S | re.M,
    )
    return match.group(1).strip() if match else None


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    version = sys.argv[1].removeprefix("v")
    notes = section(version, CHANGELOG.read_text("utf-8"))
    if not notes:
        print(f"CHANGELOG.md has no section for {version}", file=sys.stderr)
        return 1
    print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
