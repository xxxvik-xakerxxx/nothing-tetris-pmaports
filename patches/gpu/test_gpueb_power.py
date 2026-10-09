#!/usr/bin/env python3
"""Static checks/extraction only; native execution is reserved for CI."""
import argparse
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch as mock_patch

from test_supply_inventory import PATCHES, ROOT, new_file, validate_hunk_counts
from prepare_native import definition

NAME = "0118-pmdomain-mediatek-mt6878-gpueb-power-backend.patch"
CORE = "include/linux/soc/mediatek/mt6878-gpueb-power-core.h"
API = "include/linux/soc/mediatek/mt6878-gpueb-power.h"
DRIVER = "drivers/pmdomain/mediatek/mt6878-gpueb-power.c"
PIN = "ee2be53cb75670b548948636a0db1d1ff112bf12"


def source(path):
    return new_file((PATCHES / NAME).read_text(), path)


def vendor(path):
    repo = Path(os.environ.get("TETRIS_DEVICE_MODULES_TREE", str(
        ROOT.parent / "android_kernel_device_modules_6.1_nothing_mt6878")))
    return subprocess.check_output(["git", "show", f"{PIN}:{path}"],
                                   cwd=repo, text=True)


def require_exact_application(result):
    output = result.stdout + result.stderr
    if result.returncode or re.search(r"\b(?:offset|fuzz)\b", output, re.IGNORECASE):
        raise AssertionError(f"{NAME}: non-exact patch application:\n{output}")


class GPUEBPower(unittest.TestCase):
    def test_vendor_tree_override_preserves_pin(self):
        path = "drivers/gpu/mediatek/gpufreq/v2/include/gpufreq_ipi.h"
        with mock_patch.dict(os.environ, {"TETRIS_DEVICE_MODULES_TREE": "/ci/upstream/device-modules"}), \
                mock_patch("subprocess.check_output", return_value="fixture") as read:
            self.assertEqual(vendor(path), "fixture")
            read.assert_called_once_with(["git", "show", f"{PIN}:{path}"],
                                         cwd=Path("/ci/upstream/device-modules"), text=True)

    def test_complete_hunks(self):
        validate_hunk_counts((PATCHES / NAME).read_text(), NAME)

    def test_zero_fuzz_application(self):
        kernel = Path(os.environ.get("TETRIS_KERNEL_TREE", str(
            ROOT.parent / "linux-d84b264a54a37611f2f46bc19363cb9b41606205")))
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            for relative in ("drivers/pmdomain/mediatek/Makefile",
                             "drivers/pmdomain/mediatek/Kconfig"):
                target = tree / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text((kernel / relative).read_text())
            result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1"],
                                    cwd=tree, input=(PATCHES / NAME).read_text(),
                                    text=True, capture_output=True)
            require_exact_application(result)
            for relative in (CORE, API, DRIVER):
                self.assertEqual((tree / relative).read_text(), source(relative))

    def test_patch_diagnostics_reject_offset_and_fuzz(self):
        for output in ("Hunk #1 succeeded at 2 (offset 1 line).",
                       "Hunk #1 succeeded at 1 with fuzz 1."):
            with self.subTest(output=output), self.assertRaises(AssertionError):
                require_exact_application(subprocess.CompletedProcess([], 0, output, ""))
        require_exact_application(subprocess.CompletedProcess([], 0, "patching file test", ""))

    def test_no_activation_or_direct_hardware(self):
        text = (PATCHES / NAME).read_text()
        for forbidden in ("regmap_write(", "regmap_update_bits(", "writel(",
                          "readl(", "regulator_enable(", "clk_prepare_enable(",
                          "of_genpd_add_provider", "pm_genpd_init(",
                          "module_platform_driver", 'status = "okay"'):
            # API comment describes a future registration, not executable code.
            code = source(CORE) + source(DRIVER)
            self.assertNotIn(forbidden, code)
        self.assertNotIn("arch/arm64/boot/dts", text)
        self.assertIn("mutex_lock(domain->session_lock)", source(DRIVER))
        self.assertIn("mutex_unlock(domain->session_lock)", source(DRIVER))

    def test_exact_vendor_route_and_abi(self):
        prefix = "drivers/gpu/mediatek/gpufreq/v2/"
        abi = vendor(prefix + "include/gpufreq_ipi.h")
        wrapper = vendor(prefix + "gpufreq_v2.c")
        platform = vendor(prefix + "gpufreq_mt6878.c")
        timeout = vendor("drivers/gpu/mediatek/gpueb/include/gpueb_ipi.h")
        self.assertIn("CMD_POWER_CONTROL             = 6,", abi)
        self.assertIn("unsigned long long base;", abi)
        self.assertIn("unsigned int target;", abi)
        self.assertIn("send_msg.u.power_state = power;", wrapper)
        self.assertIn("ret = g_recv_msg.u.return_value;", wrapper)
        self.assertIn("data.magic = g_ipi_magic;", wrapper)
        self.assertIn('no support on AP mode', platform)
        self.assertIn("IPI_TIMEOUT_MS     10000U", timeout)
        self.assertIn("words[4] = on;", source(CORE))

    def test_single_transfer_no_retry(self):
        core = source(CORE)
        self.assertEqual(core.count("ret = ops->transfer("), 1)
        for loop in ("while (", "for (", "goto "):
            self.assertNotIn(loop, core)
        self.assertIn("if (state->first_error)", core)
        self.assertIn("return -EBUSY;", core)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract", type=Path)
    args = parser.parse_args()
    if args.extract:
        # Production logic unchanged; native fixture supplies only scalar types.
        args.extract.write_text(source(CORE).replace("#include <linux/errno.h>\n", "")
                                .replace("#include <linux/types.h>\n", ""))
        abi = vendor("drivers/gpu/mediatek/gpufreq/v2/include/gpufreq_ipi.h")
        args.extract.with_name("vendor-abi.h").write_text(
            definition(abi, "enum gpufreq_ipi_cmd {") +
            definition(abi, "struct gpufreq_ipi_data {") +
            definition(vendor("drivers/gpu/mediatek/gpufreq/v2/include/gpufreq_v2.h"),
                       "enum gpufreq_power_state {"))
    else:
        unittest.main(argv=[__file__])
