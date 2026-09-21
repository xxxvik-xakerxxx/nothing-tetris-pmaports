#!/usr/bin/env python3
"""Check that each declared vendor patch is explicitly applied in prepare()."""
import re
import sys
from pathlib import Path


def check(source):
    sources = re.search(r'^source="(.*?)^"', source, re.M | re.S)
    prepare = re.search(r'^prepare\(\)\s*\{(.*?)^\}', source, re.M | re.S)
    if not sources or not prepare:
        raise ValueError("missing source list or prepare()")
    declared = re.findall(r'^\s*([^\s"/]+\.patch\.vendor)\s*$', sources[1], re.M)
    body = prepare[1].replace("\\\n", " ")
    applied = re.findall(
        r'^\s*patch\s+-p1\s+-d\s+"\$_(?:devmods|connmods)_dir"\s+'
        r'<\s*"\$srcdir"/([^\s]+\.patch\.vendor)\s*$', body, re.M
    )
    errors = [name for name in declared if applied.count(name) != 1]
    errors += [name for name in applied if name not in declared]
    if errors:
        raise ValueError("vendor patches must be declared and applied exactly once: "
                         + ", ".join(sorted(set(errors))))


if __name__ == "__main__":
    try:
        check(Path(sys.argv[1]).read_text())
    except (ValueError, IndexError) as error:
        sys.exit(str(error))
    print("vendor patch application: PASS")
