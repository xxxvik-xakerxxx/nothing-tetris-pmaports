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
    "0100-vendor-scp-use-vfree-for-mailbox-tables.patch.vendor",
    "0101-vendor-scp-bound-recovery-to-firmware-reservation.patch.vendor",
    "0102-vendor-scp-bootstrap-resource-diagnostic.patch.vendor",
    "0103-vendor-scp-share-infracfg-syscon.patch.vendor",
)
SOURCE_FILES = (
    SOURCE,
    HEADER,
    "drivers/misc/mediatek/scp/rv/scp_reg.h",
    "drivers/misc/mediatek/scp/include/scp.h",
    "drivers/misc/mediatek/scp/rv/Makefile",
    "drivers/misc/mediatek/scp/rv/scp_dvfs.c",
    "drivers/misc/mediatek/scp/rv/scp_dvfs.h",
    "drivers/misc/mediatek/scp/rv/scp_excep.c",
    "drivers/misc/mediatek/scp/rv/scp_awake.c",
    "drivers/misc/mediatek/scp/rv/scp_feature_define.h",
)


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vendor_repo", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    patches = root / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
    apkbuild = (patches / "APKBUILD").read_text()
    source_list = apkbuild.split('source="', 1)[1].split('"', 1)[0].split()
    dt_base = "0099-arm64-dts-mediatek-add-manual-MT6878-SCP-contract.patch"
    dt_link = "0104-arm64-dts-mt6878-scp-infracfg.patch"
    if source_list.index(dt_link) < source_list.index(dt_base):
        raise RuntimeError("SCP infracfg DT patch precedes its prerequisite in APKBUILD")

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
typedef uint64_t u64;
#define check_add_overflow(a, b, out) __builtin_add_overflow(a, b, out)
#define check_mul_overflow(a, b, out) __builtin_mul_overflow(a, b, out)
#define pr_err(...) ((void)0)
#define SCP_A_TCM_SIZE (128U * 1024U)
""" + structure.group() + """
static struct scp_region_info_st scp_region_info_copy;
static struct { u32 scp_dram_region, core_nums, secure_dump; } scpreg;
"""
    tests = (root / "scripts/tests/scp-region-dram.c").read_text()
    with tempfile.TemporaryDirectory(prefix="scp-region-host-") as tmp:
        scratch = Path(tmp)
        dt_path = "arch/arm64/boot/dts/mediatek/mt6878-scp-manual.dtsi"
        for name in (dt_base, dt_link):
            run(["git", "apply", "--include=" + dt_path, str(patches / name)], cwd=scratch)
        if "mediatek,infracfg = <&infracfg_ao>;" not in (scratch / dt_path).read_text():
            raise RuntimeError("SCP DT lacks shared infracfg phandle")
        print("PASS: SCP DT patch order and application")
        source = scratch / SOURCE
        for path in SOURCE_FILES:
            target = scratch / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(vendor(path))
        before = None
        arithmetic = None
        for name in PATCHES:
            # Apply all files of each SCP patch in disposable storage.
            run(["git", "apply", "--check", str(patches / name)], cwd=scratch)
            run(["git", "apply", str(patches / name)], cwd=scratch)
            if name.startswith("0093-"):
                before = source.read_text()
            if name.startswith("0100-"):
                arithmetic = source.read_text()

        for label, contents in (("before", before), ("after", arithmetic),
                                ("memory", source.read_text())):
            start = contents.index("static bool scp_region_range_valid(")
            end = contents.index("static int scp_region_info_init(", start)
            harness = scratch / f"{label}.c"
            executable = scratch / label
            cases = ((root / "scripts/tests/scp-region-memory.c").read_text()
                     if label == "memory" else tests)
            harness.write_text(preamble + contents[start:end] + cases)
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
        contents = source.read_text()
        start = contents.index("static int scp_infracfg_init(void)")
        end = contents.index("static const struct dev_pm_ops", start)
        cases = (root / "scripts/tests/scp-infracfg.c").read_text()
        before, after = cases.split("/* INSERT_PATCHED_HELPER */")
        harness = scratch / "infracfg.c"
        executable = scratch / "infracfg"
        harness.write_text(before + contents[start:end] + after)
        run(shlex.split(os.environ.get("CC", "cc")) + [
            "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1",
            "-fsanitize=undefined", "-fno-sanitize-recover=all",
            str(harness), "-o", str(executable)])
        run([str(executable)])
        init = contents[contents.index("static int __init scp_init("):]
        if init.index("scp_infracfg_init();") > init.index("scp_dvfs_init();"):
            raise RuntimeError("infracfg must be validated before hardware setup")
        if "mtk_scpsys_device" in contents or "while (IS_ERR_OR_NULL" in contents:
            raise RuntimeError("legacy infracfg owner/readiness wait remains")
        awake = (scratch / "drivers/misc/mediatek/scp/rv/scp_awake.c").read_text()
        start = awake.index("int scp_awake_lock(")
        end = awake.index("EXPORT_SYMBOL_GPL(scp_awake_unlock);")
        cases = (root / "scripts/tests/scp-infracfg-awake.c").read_text()
        before, after = cases.split("/* INSERT_PATCHED_AWAKE */")
        harness = scratch / "infracfg-awake.c"
        executable = scratch / "infracfg-awake"
        harness.write_text(before + awake[start:end] + after)
        run(shlex.split(os.environ.get("CC", "cc")) + [
            "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1",
            "-fsanitize=undefined", "-fno-sanitize-recover=all",
            str(harness), "-o", str(executable)])
        run([str(executable)])
        start = contents.index("static bool bootstrap_26m;")
        end = contents.index("/* scp semaphore timeout count definition */", start)
        harness = scratch / "bootstrap.c"
        executable = scratch / "bootstrap"
        tests = (root / "scripts/tests/scp-bootstrap-resource.c").read_text()
        before, after = tests.split("/* INSERT_PATCHED_HELPERS */")
        harness.write_text(before + contents[start:end] + after)
        run(shlex.split(os.environ.get("CC", "cc")) + [
            "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1",
            "-fsanitize=undefined", "-fno-sanitize-recover=all",
            str(harness), "-o", str(executable)])
        run([str(executable)])
        init = contents[contents.index("static int __init scp_init("):]
        if init.index("scp_bootstrap_resource_get();") > init.index(
                "platform_driver_register(&mtk_scp_device)"):
            raise RuntimeError("bootstrap request is too late")
        for label in ("err_region_info:", "err_without_unregister:"):
            if not init.split(label, 1)[1].lstrip().startswith(
                    "scp_bootstrap_resource_put();"):
                raise RuntimeError(f"missing bootstrap cleanup at {label}")
        if "scp_bootstrap_resource_put();" not in init.split("static void __exit scp_exit", 1)[1]:
            raise RuntimeError("missing bootstrap exit cleanup")
        # The firmware sends LOGGER_CTRL before READY. A DT pin without the
        # logger's receive buffer reaches vendor mtk_mbox_isr's BUG_ON.
        apkbuild = (patches / "APKBUILD").read_text()
        scp_build = apkbuild.split('_tinysys_make "$_scp"', 1)[1].split(
            '_symbols=', 1)[0]
        logger_flag = "-DCONFIG_MTK_TINYSYS_SCP_LOGGER_SUPPORT=1"
        if logger_flag not in scp_build or 'KCFLAGS=' not in scp_build:
            raise RuntimeError("SCP logger must be enabled in C, not just Kbuild")
        if init.index("scp_logger_init(") > init.index("reset_scp(SCP_ALL_ENABLE)"):
            raise RuntimeError("logger receive buffer registered after SCP start")
        harness = scratch / "logger-config.c"
        harness.write_text('''#include <stdint.h>
#define __SCP_H__
#define NUM_FEATURE_ID 16
#include "drivers/misc/mediatek/scp/rv/scp_feature_define.h"
int main(void) { return SCP_LOGGER_ENABLE != EXPECT_LOGGER; }
''')
        for enabled in (0, 1):
            executable = scratch / f"logger-config-{enabled}"
            run(shlex.split(os.environ.get("CC", "cc")) + [
                "-std=c11", "-Wall", "-Wextra", "-Werror",
                f"-DEXPECT_LOGGER={enabled}",
                "-I" + str(scratch / "drivers/misc/mediatek/scp/include"),
            ] + ([logger_flag] if enabled else []) + [
                str(harness), "-o", str(executable)])
            run([str(executable)])
        print("PASS: SCP logger C configuration and pre-reset initialization")
        print(f"PASS: exact-source patch application and host UBSan ({VENDOR_COMMIT})")


if __name__ == "__main__":
    main()
