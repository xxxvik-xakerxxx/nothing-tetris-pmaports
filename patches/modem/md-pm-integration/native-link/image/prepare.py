#!/usr/bin/env python3
"""Prepare independent original vendor sources, never objects, for package Kbuild."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess


def prepare(source, destination, patches):
    source, destination = Path(source).absolute(), Path(destination).absolute()
    if source.resolve() != source or destination.resolve() != destination or destination.exists():
        raise ValueError("fresh independent native vendor source directory required")
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("native vendor source/destination overlap")
    destination.mkdir(parents=True)
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError("vendor source symlink: " + str(path))
        if not path.is_file() or not (path.suffix in (".c", ".h", ".S") or
                                     path.name in ("Makefile", "Kbuild", "Kconfig")):
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    for index, patch in enumerate(patches):
        data = Path(patch).read_bytes()
        for option in (["--check"], []):
            result = subprocess.run(["git", "apply", "--verbose", *option, "-"],
                                    cwd=destination, input=data, capture_output=True)
            # The reviewed frozen owner bundle predates shipping line-count
            # changes. Only that exact first layer permits its known offsets.
            legacy_owner = index == 0 and Path(patch).name == "0200-native-owner.patch.vendor"
            if result.returncode or b"Skipped patch" in result.stderr or re.search(rb"\bfuzz\b", result.stderr) or (
                    not legacy_owner and re.search(rb"\boffset\b", result.stderr)):
                raise ValueError("native vendor patch failed: " + str(patch) + "\n" + result.stderr.decode())
    if list(destination.rglob("*.o")) or list(destination.rglob("*.ko")):
        raise ValueError("native source preparation copied compiled objects")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("patches", nargs="+", type=Path)
    args = parser.parse_args()
    prepare(args.source, args.destination, args.patches)
