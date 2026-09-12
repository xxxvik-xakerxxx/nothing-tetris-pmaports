#!/usr/bin/env python3
"""Inventory object dependencies, not module linkage or hardware readiness."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_symbols(output):
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 4 or len(fields[1]) != 1:
            raise ValueError(f"unexpected POSIX nm row: {line!r}")
        name, kind, _, _ = fields
        yield name, kind


def audit(objects, nm):
    definitions = defaultdict(list)
    required = defaultdict(list)
    weak = defaultdict(list)
    inventory = []
    for path in objects:
        output = subprocess.check_output(
            [nm, "--format=posix", "--extern-only", str(path)], text=True)
        inventory.append({"path": str(path), "sha256": digest(path)})
        for name, kind in parse_symbols(output):
            if kind == "U":
                required[name].append(str(path))
            elif kind in ("w", "v"):
                weak[name].append(str(path))
            elif kind in "ABCDGIRSTVWu":
                definitions[name].append({"object": str(path), "kind": kind})
            else:
                raise ValueError(f"unclassified symbol type {kind!r}: {name}")
    unresolved = sorted(required.keys() - definitions.keys())
    return {
        "scope": "Object-set dependency inventory; not a linked module",
        "module_export_and_crc_compatibility_verified": False,
        "object_count": len(objects),
        "unresolved_count": len(unresolved),
        "objects": inventory,
        "unresolved": {name: required[name] for name in unresolved},
        "resolved_within_set": {
            name: {"consumers": required[name], "providers": definitions[name]}
            for name in sorted(required.keys() & definitions.keys())},
        "unresolved_weak": {
            name: weak[name] for name in sorted(weak.keys() - definitions.keys())},
        "multiple_definitions": {
            name: definitions[name] for name in sorted(definitions)
            if len(definitions[name]) > 1},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nm", default="llvm-nm")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("inputs", type=Path, nargs="+")
    args = parser.parse_args()
    objects = []
    for path in args.inputs:
        if path.is_dir():
            selected = sorted(path.rglob("*.o"))
            if not selected:
                parser.error(f"no objects in {path}")
            objects.extend(selected)
        elif path.is_file() and path.suffix == ".o":
            objects.append(path)
        else:
            parser.error(f"not an object or directory: {path}")
    if len({p.resolve() for p in objects}) != len(objects):
        parser.error("overlapping inputs would count an object twice")
    result = audit(objects, args.nm)
    result["config_sha256"] = digest(args.config)
    result["nm_version"] = subprocess.check_output(
        [args.nm, "--version"], text=True).strip()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
