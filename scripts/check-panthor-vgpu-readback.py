#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Host-only executable source comparison; success does NOT authorize GPU probe."""

import argparse
import hashlib
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


VENDOR_COMMIT = "ee2be53cb75670b548948636a0db1d1ff112bf12"
KERNEL_COMMIT = "d84b264a54a37611f2f46bc19363cb9b41606205"
DRIVER = "drivers/regulator/mt6315-regulator.c"
HEADER = "include/linux/regulator/mt6315-regulator.h"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def function(source, signature):
    # These pinned C functions have an unindented closing brace. Reject drift.
    require(source.count(signature) == 1, f"missing/ambiguous function: {signature}")
    start = source.index(signature)
    end = source.index("\n}\n", start) + 3
    return source[start:end]


def register(source, name):
    matches = re.findall(r"^#define\s+" + name + r"\s+(0x[0-9a-fA-F]+)\s*$",
                         source, re.MULTILINE)
    require(len(matches) == 1, f"missing/ambiguous register: {name}")
    return int(matches[0], 16)


def file_text(tree, commit, path):
    candidate = tree / path
    if candidate.is_file():
        return candidate.read_text()
    return subprocess.check_output(
        ["git", "-C", str(tree), "show", f"{commit}:{path}"], text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel_tree", type=Path,
                        help="Linux 6.18 tree prepared from d84b264a")
    parser.add_argument("device_modules", type=Path,
                        help="git repository containing the pinned Nothing 4.1 object")
    parser.add_argument("--cc", default="cc", help="host C compiler (no target build)")
    args = parser.parse_args()

    def vendor(path):
        return subprocess.check_output(
            ["git", "-C", str(args.device_modules), "show", f"{VENDOR_COMMIT}:{path}"],
            text=True)

    upstream = file_text(args.kernel_tree, KERNEL_COMMIT, DRIVER)
    upstream_header = file_text(args.kernel_tree, KERNEL_COMMIT, HEADER)
    helpers = file_text(args.kernel_tree, KERNEL_COMMIT,
                        "drivers/regulator/helpers.c")
    downstream = vendor(DRIVER)
    downstream_header = vendor(HEADER)
    # Ensure the functions under test are the callbacks actually selected by each driver.
    for source, callback in ((upstream, "regulator_get_voltage_sel_regmap"),
                             (downstream, "mt6315_regulator_get_voltage_sel")):
        require(re.search(r"\.get_voltage_sel\s*=\s*" + callback + r"\s*,", source),
                f"voltage callback changed: {callback}")
        require("REGULATOR_LINEAR_RANGE(0, 0, 0xbf, 6250)" in source,
                "voltage range changed; review test selector limits")
    require(re.search(r'MT_BUCK\("vbuck2",\s*MT6315_VBUCK2,\s*MT6315_BUCK_TOP_ELR2\)',
                      upstream), "mainline VBUCK2 descriptor changed")
    require(re.search(r'MT_BUCK\("vbuck2",\s*VBUCK2,\s*mt_volt_range1,\s*2,\s*'
                      r'MT6315_BUCK_TOP_ELR2,\s*0x2\)', downstream),
            "vendor VBUCK2 descriptor changed")
    require(re.search(r'\.vsel_mask\s*=\s*0xff', upstream)
            and re.search(r'\.vsel_mask\s*=\s*0xff', downstream), "selector mask changed")
    for expression in (r'\.da_vsel_reg\s*=\s*MT6315_VBUCK##_bid##_DBG0',
                       r'\.da_reg\s*=\s*MT6315_VBUCK##_bid##_DBG4',
                       r'\.qi\s*=\s*BIT\(0\)'):
        require(re.search(expression, downstream), "vendor readback descriptor changed")

    defines = []
    for name in ("MT6315_BUCK_TOP_ELR2", "MT6315_VBUCK2_DBG0", "MT6315_VBUCK2_DBG4"):
        value = register(upstream_header, name)
        require(value == register(downstream_header, name), f"register mismatch: {name}")
        defines.append(f"#define {name} {value}")
    generated = "\n".join(defines) + "\n" + function(
        downstream, "static int mt6315_regulator_get_voltage_sel(") + function(
        helpers, "int regulator_get_voltage_sel_regmap(")
    fixture = Path(__file__).parent / "tests/panthor-vgpu-readback.c"
    with tempfile.TemporaryDirectory(prefix="panthor-vgpu-host-") as temporary:
        directory = Path(temporary)
        source_header = directory / "readback-source.h"
        source_header.write_text(generated)
        binary = directory / "readback-test"
        command = shlex.split(args.cc) + ["-std=c11", "-Wall", "-Wextra", "-Werror",
                  "-I", str(directory), str(fixture), "-o", str(binary)]
        subprocess.run(command, check=True)
        subprocess.run([str(binary)], check=True)
        for name, old, new in (
            ("wrong enabled readback register", "reg_addr = info->da_vsel_reg;",
             "reg_addr = rdev->desc->vsel_reg;"),
            ("swallowed read errors", "return ret;", "return 0;"),
        ):
            require(old in generated, f"mutation anchor missing: {name}")
            source_header.write_text(generated.replace(old, new))
            subprocess.run(command, check=True)
            result = subprocess.run([str(binary)], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, cwd=directory)
            require(result.returncode != 0, f"test failed to detect mutation: {name}")
            print(f"PASS: rejected {name}")
    print(f"Vendor source: {VENDOR_COMMIT}")
    for name, source in ((DRIVER, upstream), (HEADER, upstream_header),
                         ("drivers/regulator/helpers.c", helpers)):
        print(f"Kernel SHA256 {name}: {hashlib.sha256(source.encode()).hexdigest()}")
    print("BLOCKER: enabled-rail ELR2/DBG0 equivalence is unproven; no runtime approval.")


if __name__ == "__main__":
    main()
