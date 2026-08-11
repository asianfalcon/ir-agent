#!/usr/bin/env python3
"""Copy the legacy mutable state into the external IRA runtime layout.

The command is dry-run by default. It never removes legacy files and refuses to
overwrite a different destination file. Re-running it is therefore safe.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _copy_file(source: Path, target: Path, execute: bool) -> str:
    if target.exists():
        if source.stat().st_size == target.stat().st_size and _digest(source) == _digest(target):
            return "same"
        raise FileExistsError(f"destination differs; refusing overwrite: {target}")
    if execute:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return "copy"


def migrate(runtime_root: Path, execute: bool = False) -> dict[str, int]:
    mappings = (
        (PROJECT_ROOT / "data" / "inputs", runtime_root / "sources" / "manual"),
        (PROJECT_ROOT / "data" / "raw", runtime_root / "sources" / "external"),
        (PROJECT_ROOT / "data" / "processed", runtime_root / "derived"),
        (PROJECT_ROOT / "data" / "storage" / "lancedb_root", runtime_root / "stores" / "vector" / "lancedb_root"),
        (PROJECT_ROOT / "data" / "storage" / "kuzu_root.db", runtime_root / "stores" / "graph" / "kuzu_root.db"),
        (PROJECT_ROOT / "databases" / "ira.db", runtime_root / "stores" / "relational" / "ira.db"),
        (PROJECT_ROOT / "output", runtime_root / "artifacts"),
        (PROJECT_ROOT / "outputs", runtime_root / "artifacts" / "legacy-outputs"),
    )
    counts = {"copy": 0, "same": 0, "missing": 0}
    for source_root, target_root in mappings:
        if not source_root.exists():
            counts["missing"] += 1
            continue
        files = [source_root] if source_root.is_file() else [p for p in source_root.rglob("*") if p.is_file()]
        for source in files:
            target = target_root if source_root.is_file() else target_root / source.relative_to(source_root)
            result = _copy_file(source, target, execute)
            counts[result] += 1
            print(f"{result:>4}  {source} -> {target}")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=os.environ.get("IRA_RUNTIME_ROOT"),
        required="IRA_RUNTIME_ROOT" not in os.environ,
    )
    parser.add_argument("--execute", action="store_true", help="perform copies; otherwise only preview")
    args = parser.parse_args()
    runtime_root = args.runtime_root.expanduser().resolve()
    if runtime_root == PROJECT_ROOT or PROJECT_ROOT in runtime_root.parents:
        raise SystemExit("runtime root must be physically outside the code repository")
    counts = migrate(runtime_root, execute=args.execute)
    mode = "completed" if args.execute else "dry-run"
    print(f"{mode}: {counts}")


if __name__ == "__main__":
    main()
