#!/usr/bin/env python3
"""Test a patch against exact existing U-Boot code in ignored scratch storage."""
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

BASE = "c931695bb963efaa0dfdf928ea475440581838b4"
folder = Path(__file__).resolve().parent
repo = Path(sys.argv[1]).resolve()
local = folder / "local"
local.mkdir(exist_ok=True)


def git(*args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


with tempfile.TemporaryDirectory(prefix="stock48-", dir=local) as tmp:
    root = Path(tmp)
    files = git("ls-tree", "-r", "--name-only", BASE, "scripts/dtc/libfdt").decode().splitlines()
    files += ["board/mediatek/mt6878/mt6878_tetris.c", ".github/tests/tetris_ccci_handoff.c"]
    for name in files:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git("show", f"{BASE}:{name}"))
    test = root / ".github/tests/test_ccci_stock48.c"
    test.write_bytes((folder / "test_ccci_stock48.c").read_bytes())
    sources = ["fdt.c", "fdt_addresses.c", "fdt_empty_tree.c", "fdt_ro.c",
               "fdt_rw.c", "fdt_strerror.c", "fdt_sw.c", "fdt_wip.c"]
    for phase in ("before", "after"):
        if phase == "after":
            patch = str(folder / "ccci-stock48.patch")
            # Avoid discovering the parent worktree and silently skipping paths
            # outside this scratch directory's prefix.
            environment = dict(os.environ, GIT_CEILING_DIRECTORIES=str(root.parent))
            subprocess.run(["git", "apply", "--check", patch], cwd=root, env=environment, check=True)
            subprocess.run(["git", "apply", patch], cwd=root, env=environment, check=True)
            source = root / "board/mediatek/mt6878/mt6878_tetris.c"
            if "TETRIS_CCCI_STOCK_V3_DESC_SIZE" not in source.read_text():
                raise RuntimeError("stock48 patch was not applied")
        binary = root / phase
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-O1",
            "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
            "-Iscripts/dtc/libfdt", str(test)]
        if phase == "before":
            command += ["-DEXPECT_OLD_REJECTION"]
        command += ["scripts/dtc/libfdt/" + source for source in sources]
        subprocess.run(command + ["-o", str(binary)], cwd=root, check=True)
        subprocess.run([str(binary)], check=True)
