#!/usr/bin/env python3
"""Static source/lifetime checks only; no C compilation or hardware access."""
from pathlib import Path
import os
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PIN = "ee2be53cb75670b548948636a0db1d1ff112bf12"


def vendor(name):
    tree = Path(os.environ.get("TETRIS_DEVICE_MODULES_TREE", str(
        ROOT.parent / "android_kernel_device_modules_6.1_nothing_mt6878")))
    return subprocess.check_output(["git", "-C", str(tree), "show", f"{PIN}:{name}"], text=True)


class SupplierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = (HERE / "mt6878-gpueb-mfg0.c").read_text()
        cls.prepare = cls.code.split("int mt6878_gpueb_mfg0_prepare(", 1)[1].split("EXPORT_SYMBOL", 1)[0]
        cls.resume = cls.code.split("int mt6878_gpueb_mfg0_resume(", 1)[1].split("EXPORT_SYMBOL", 1)[0]
        cls.quarantine = cls.code.split("int mt6878_gpueb_mfg0_quarantine(", 1)[1].split("EXPORT_SYMBOL", 1)[0]
        cls.finish = cls.code.split("int mt6878_gpueb_mfg0_finish(", 1)[1].split("EXPORT_SYMBOL", 1)[0]

    def test_matching_domain_is_not_nested_rpc(self):
        source = vendor("drivers/soc/mediatek/mtk-scpsys-mt6878.c")
        block = source.split("[MT6878_POWER_DOMAIN_MFG0_SHUTDOWN]", 1)[1].split(
            "[MT6878_POWER_DOMAIN_APU]", 1)[0]
        for text in ("0xEB4", "GENMASK(8, 8)", "GENMASK(12, 12)",
                     "0x0CA4, 0x0CA8", "0x0C44, 0x0C48", "MTK_SCPD_BYPASS_INIT_ON"):
            self.assertIn(text, block)
        self.assertIn("MT6878_POWER_DOMAIN_MFG0_SHUTDOWN", self.code)
        self.assertIn('"mediatek,mt6878-power-controller"', self.code)
        self.assertIn("supplier.args_count == 1", self.code)
        self.assertIn("of_node_put(supplier.np)", self.code)
        gpufreq = vendor("drivers/gpu/mediatek/gpufreq/v2/gpufreq_mt6878.c")
        callbacks = gpufreq.split("platform_eb_fp = {", 1)[1].split("};", 1)[0]
        self.assertNotIn("power_control", callbacks)

    def test_ownership_precedes_possible_power_write(self):
        for text in ("device_trylock(dev)", "device_is_bound(dev)", "suppress_bind_attrs",
                     "mfg0_domain(dev)", "try_module_get(THIS_MODULE)",
                     "try_module_get(scope->parent_module)", "get_device(dev)",
                     "*result = scope"):
            self.assertIn(text, self.prepare)
        self.assertNotIn("pm_runtime_get_sync", self.prepare)
        self.assertNotIn("pm_runtime_put", self.resume)
        self.assertLess(self.resume.index("scope->attempted = true"),
                        self.resume.index("ret = pm_runtime_get_sync(dev)"))
        self.assertIn("mt6878_gpueb_mfg0_quarantine(scope, ret)", self.resume)
        self.assertIn("device_unlock(scope->parent)", self.quarantine)
        self.assertNotIn("module_put", self.quarantine)

    def test_retirement_cannot_discard_failed_resume(self):
        check = self.finish.index("if (scope->first_error)")
        for operation in ("*slot = NULL", "pm_runtime_put_noidle(dev)", "device_unlock(dev)",
                          "put_device(dev)", "kfree(scope)"):
            self.assertLess(check, self.finish.index(operation))
        self.assertLess(check, self.finish.index("scope->task != current"))
        self.assertNotIn("pm_runtime_put_sync", self.code)
        self.assertNotIn("pm_runtime_enable(", self.code)
        for forbidden in ("writel(", "readl(", "regulator_enable(", "clk_prepare_enable(",
                          "arm_smccc", "rproc_boot(", "platform_driver_register("):
            self.assertNotIn(forbidden, self.code)

    def test_ci_only_strict_runner_and_fault_fixture(self):
        runner = (HERE / "run-native-ci.sh").read_text()
        self.assertLess(runner.index('${CI:-}'), runner.index('${HOSTCC:-cc}'))
        self.assertIn("-Wall -Wextra -Werror", runner)
        self.assertIn("-fsanitize=address,undefined", runner)
        fixture = (HERE / "native-test.c").read_text()
        self.assertIn('#include "mt6878-gpueb-mfg0.c"', fixture)
        for text in ("-ETIMEDOUT", "-EHOSTDOWN", "-EPERM", "-EBUSY", "-ENOMEM",
                     "resume_calls == 1", "noidle_calls == 0", "scope == NULL"):
            self.assertIn(text, fixture)


if __name__ == "__main__":
    unittest.main()
