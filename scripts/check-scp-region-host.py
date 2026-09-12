#!/usr/bin/env python3
"""Compile the patched SCP validator from the pinned vendor source; no device I/O."""

import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


VENDOR_COMMIT = "ee2be53cb75670b548948636a0db1d1ff112bf12"
SOURCE = "drivers/misc/mediatek/scp/rv/scp_helper.c"
HEADER = "drivers/misc/mediatek/scp/rv/scp_helper.h"
PATCHES = (
    "0036-vendor-scp-linux-6.18-api.patch.vendor",
    "0041-vendor-scp-fail-closed-dvfs-timeout.patch.vendor",
    "0093-vendor-scp-validate-region-info.patch.vendor",
    "0094-vendor-scp-validate-dram-recovery-span.patch.vendor",
)
SOURCE_FILES = (
    SOURCE,
    "drivers/misc/mediatek/scp/include/scp.h",
    "drivers/misc/mediatek/scp/rv/Makefile",
    "drivers/misc/mediatek/scp/rv/scp_dvfs.c",
    "drivers/misc/mediatek/scp/rv/scp_dvfs.h",
    "drivers/misc/mediatek/scp/rv/scp_excep.c",
)


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vendor_repo", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    patches = root / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"

    def vendor(path):
        return run(["git", "-C", str(args.vendor_repo), "show",
                    f"{VENDOR_COMMIT}:{path}"], capture_output=True).stdout

    header = vendor(HEADER)
    structure = re.search(r"struct scp_region_info_st \{.*?\n\};", header, re.S)
    if structure is None:
        raise RuntimeError("pinned vendor region-info structure not found")
    preamble = """
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
#define check_add_overflow(a, b, out) __builtin_add_overflow(a, b, out)
#define check_mul_overflow(a, b, out) __builtin_mul_overflow(a, b, out)
#define pr_err(...) ((void)0)
#define SCP_A_TCM_SIZE (128U * 1024U)
""" + structure.group() + """
static struct scp_region_info_st scp_region_info_copy;
static struct { u32 scp_dram_region; } scpreg;
"""
    tests = (root / "scripts/tests/scp-region-dram.c").read_text()
    with tempfile.TemporaryDirectory(prefix="scp-region-host-") as tmp:
        scratch = Path(tmp)
        source = scratch / SOURCE
        for path in SOURCE_FILES:
            target = scratch / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(vendor(path))
        before = None
        for name in PATCHES:
            run(["git", "apply", "--check", str(patches / name)], cwd=scratch)
            run(["git", "apply", str(patches / name)], cwd=scratch)
            if name.startswith("0093-"):
                before = source.read_text()

        for label, contents in (("before", before), ("after", source.read_text())):
            start = contents.index("static bool scp_region_range_valid(")
            end = contents.index("static int scp_region_info_init(", start)
            harness = scratch / f"{label}.c"
            executable = scratch / label
            harness.write_text(preamble + contents[start:end] + tests)
            run(shlex.split(os.environ.get("CC", "cc")) + [
                "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1",
                "-fsanitize=undefined", "-fno-sanitize-recover=all",
                str(harness), "-o", str(executable)])
            result = subprocess.run([str(executable)], text=True, capture_output=True)
            print(f"{label}: {result.stdout.strip()}")
            if label == "before":
                if result.returncode != 1 or "FAIL backup span wraps:" not in result.stderr:
                    raise RuntimeError("test did not reproduce the baseline mapping defect")
            elif result.returncode:
                raise RuntimeError(result.stderr)
        print(f"PASS: exact-source patch application and host UBSan ({VENDOR_COMMIT})")


if __name__ == "__main__":
    main()
