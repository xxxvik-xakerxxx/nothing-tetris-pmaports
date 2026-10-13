#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Static mutation tests only: no C execution, hardware emulation or JIT."""
import ast
import json
import unittest

import check
import generate as gen


class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.output, cls.sources = check.check(gen.ROOT.parent)

    def reject_driver(self, old, new):
        output = dict(self.output)
        output[gen.DRIVER] = gen.replace_once(output[gen.DRIVER], old, new)
        with self.assertRaises((ValueError, AssertionError)):
            check.validate_delta(self.base, output)

    def test_source_files_parse(self):
        for name in ("generate.py", "check.py", "test_source.py"):
            ast.parse((gen.HERE / name).read_text())

    def test_parent_staging_uses_real_driver_only(self):
        staging = json.loads((gen.HERE / "STAGING.json").read_text())
        self.assertEqual(staging["ci_objects"], [gen.DRIVER.removesuffix(".c") + ".o"])
        self.assertEqual(staging["kernel_commit"], gen.KERNEL)
        self.assertEqual(staging["device_modules_commit"], gen.DEVICE)
        self.assertEqual(staging["modules_commit"], gen.MODULES)
        self.assertEqual(staging["ci_config"]["VIDEO_IMX882_IDENTITY"], "m")
        self.assertEqual(staging["dt_status"], "all sensor and regulator fixture nodes remain disabled")

    def test_patch_projection_excludes_unrelated_payload(self):
        data = b"--- a/ignored.c\n+++ b/ignored.c\n@@ -1 +1 @@\n-a\n+b\n"
        self.assertEqual(gen.project_patch(data), b"")

    def test_reject_running_output_takeover(self):
        self.reject_driver("if (__clk_is_enabled(imx882->xclk))", "if (false)")

    def test_reject_source_rate_guess(self):
        self.reject_driver("clk_get_rate(imx882->xclk_source) != IMX882_XCLK_RATE",
                           "clk_get_rate(imx882->xclk_source) == 0")

    def test_reject_swallowed_parent_error(self):
        self.reject_driver("ret = clk_set_parent(imx882->xclk, imx882->xclk_source);",
                           "clk_set_parent(imx882->xclk, imx882->xclk_source);\n\tret = 0;")

    def test_reject_swallowed_source_lease_error(self):
        self.reject_driver("ret = clk_rate_exclusive_get(imx882->xclk_source);",
                           "clk_rate_exclusive_get(imx882->xclk_source);\n\tret = 0;")

    def test_reject_missing_source_lease_release(self):
        self.reject_driver("clk_rate_exclusive_put(imx882->xclk_source);", "(void)imx882->xclk_source;")

    def test_reject_missing_runtime_call(self):
        self.reject_driver("ret = imx882_mclk_acquire(imx882);", "ret = 0;")

    def test_reject_reset_write_before_gate(self):
        self.reject_driver('devm_gpiod_get(dev, "reset", GPIOD_ASIS)',
                           'devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH)')

    def test_reject_missing_real_supply_reference(self):
        self.reject_driver("if (!device_property_present(dev, property))", "if (false)")

    def test_reject_inherited_sensor_rail(self):
        self.reject_driver('return dev_err_probe(dev, -EBUSY, "sensor rail already enabled\\n");',
                           "return 0;")

    def test_reject_removed_chip_id_gate(self):
        self.reject_driver("chip_id != IMX882_CHIP_ID", "false")

    def test_reject_changed_sensor_delay(self):
        self.reject_driver("usleep_range(5000, 5100);", "usleep_range(1, 2);")

    def test_reject_early_enable_in_dt(self):
        output = dict(self.output)
        output[gen.DTS] = output[gen.DTS].replace('status = "disabled";', 'status = "okay";', 1)
        with self.assertRaises(ValueError):
            check.validate_delta(self.base, output)

    def test_reject_old_factor_clock(self):
        output = dict(self.output)
        output[gen.DTS] = output[gen.DTS].replace("CLK_TOP_CAMTG2_SEL>,", "CLK_TOP_CAMTG2>,")
        with self.assertRaises(ValueError):
            check.validate_delta(self.base, output)

    def test_reject_unpaired_binding_clock_names(self):
        output = dict(self.output)
        output[gen.BINDING] = output[gen.BINDING].replace("- const: xclk-source", "- const: unused")
        with self.assertRaises(ValueError):
            check.validate_delta(self.base, output)

    def test_reject_source_clock_route_drift(self):
        sources = dict(self.sources)
        path = "arch/arm64/boot/dts/mediatek/cust_mt6878_camera_v4l2.dtsi"
        sources[path] = sources[path].replace("CLK_TOP_CAMTG2_SEL", "CLK_TOP_CAMTG3_SEL")
        with self.assertRaises(ValueError):
            gen.verify_vendor(sources)

    def test_reject_source_power_sequence_drift(self):
        sources = dict(self.sources)
        path = "mtkcam/imgsensor/src-v4l2/common/imx882_mipi_raw/imx882mipiraw_Sensor.c"
        sources[path] = sources[path].replace("{HW_ID_DVDD, 1200000, 1}", "{HW_ID_DVDD, 1100000, 1}")
        with self.assertRaises(ValueError):
            gen.verify_vendor(sources)

    def test_patch_rejects_other_kernel_baseline(self):
        base = dict(self.base)
        base[gen.DRIVER] = gen.replace_once(base[gen.DRIVER], "\tbool rate_exclusive;", "\tbool different_owner;")
        with self.assertRaises(gen.subprocess.CalledProcessError):
            gen.apply_check(base, gen.PATCH.read_text(), self.output)


if __name__ == "__main__":
    unittest.main()
