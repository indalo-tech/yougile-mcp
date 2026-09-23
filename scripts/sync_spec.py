"""Refresh the bundled YouGile OpenAPI spec and report operations missing from the catalog.

uv run --no-project python scripts/sync_spec.py          # download and update the snapshot
uv run --no-project python scripts/sync_spec.py --check  # only compare, exit 1 on drift
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import urllib.request
from pathlib import Path

SPEC_URL = "https://ru.yougile.com/api-json"
ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "src" / "yougile_mcp" / "data" / "openapi.json"
CATALOG = ROOT / "src" / "yougile_mcp" / "catalog.py"


def operation_ids(spec: dict) -> set[str]:
    return {op["operationId"] for item in spec["paths"].values() for op in item.values()}


def mapped_ids() -> set[str]:
    """Keys of catalog.MAPPING, read statically so the script needs no dependencies."""
    tree = ast.parse(CATALOG.read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "MAPPING":
            return {k.value for k in node.value.keys}  # type: ignore[union-attr]
    raise SystemExit("MAPPING not found in catalog.py")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="do not write the snapshot")
    args = parser.parse_args()

    with urllib.request.urlopen(SPEC_URL, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    fresh = json.loads(raw)
    current = json.loads(SNAPSHOT.read_text("utf-8"))

    new_ops = operation_ids(fresh) - operation_ids(current)
    gone_ops = operation_ids(current) - operation_ids(fresh)
    unmapped = operation_ids(fresh) - mapped_ids()
    changed = fresh != current

    version = fresh.get("info", {}).get("version")
    print(f"spec version {version}, {len(operation_ids(fresh))} operations")
    print(f"snapshot {'differs' if changed else 'is up to date'}")
    for label, ops in (("new", new_ops), ("removed", gone_ops), ("unmapped in catalog", unmapped)):
        if ops:
            print(f"{label}: {', '.join(sorted(ops))}")

    if changed and not args.check:
        SNAPSHOT.write_text(json.dumps(fresh, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(f"wrote {SNAPSHOT.relative_to(ROOT)}; run the tests")
    return 1 if unmapped else 0


if __name__ == "__main__":
    sys.exit(main())
