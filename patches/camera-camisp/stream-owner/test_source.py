#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Static source mutation and real patch-application tests, never C simulation."""
import argparse
import ast
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import check
import generate as gen
import stage


class StreamOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.output, cls.delta, cls.evidence, cls.vendor = check.check()

    def reject(self, marker, old, new):
        output = dict(self.output)
        body = gen.function(output[gen.DRIVER], marker)
        output[gen.DRIVER] = gen.replace_once(output[gen.DRIVER], body, gen.replace_once(body, old, new))
        with self.assertRaises(ValueError):
            check.validate(self.base, output, self.vendor)

    def test_python_parses(self):
        for name in ("generate.py", "check.py", "stage.py", "test_source.py"):
            ast.parse((gen.HERE / name).read_text())

    def test_clock_contract_is_packaged_identity_0121_not_an_isolated_copy(self):
        for kind, name in (("void", "release"), ("int", "acquire")):
            marker = f"static {kind} imx882_mclk_{name}"
            self.assertEqual(gen.function(self.output[gen.DRIVER], marker), gen.function(self.base[gen.IDENTITY], marker))
        self.assertIn("0121-media-i2c-imx882-acquire-mclk-source.patch", self.evidence["packaged_patch_sha256"])

    def test_reject_shared_pll_retuning(self):
        self.reject("static int imx882_mclk_acquire", "ret = clk_rate_exclusive_get(imx882->xclk);",
                    "ret = clk_set_rate_exclusive(imx882->xclk, IMX882_XCLK_RATE);")

    def test_reject_inherited_clock_on(self):
        self.reject("static int imx882_mclk_acquire", "__clk_is_enabled(imx882->xclk)", "false")

    def test_reject_source_rate_mismatch(self):
        self.reject("static int imx882_mclk_acquire", "clk_get_rate(imx882->xclk_source)", "IMX882_XCLK_RATE")

    def test_reject_missing_parent_readback(self):
        self.reject("static int imx882_mclk_acquire", "clk_is_match(clk_get_parent(imx882->xclk), imx882->xclk_source)", "true")

    def test_reject_missing_source_handle(self):
        self.reject("static int imx882_resources_get", 'clk_get(dev, "xclk-source")', 'clk_get(dev, "xclk")')

    def test_reject_reset_assertion_on_probe(self):
        self.reject("static int imx882_camera_probe", "ret = imx882_resources_get(camera);",
                    "gpiod_direction_output(camera->power.reset, 1);\n\tret = imx882_resources_get(camera);")

    def test_reject_inherited_supply_on(self):
        self.reject("static int imx882_idle_check", "imx882_supplies_observe(power, 0)", "0")

    def test_reject_reset_request_before_idle_observation(self):
        output = dict(self.output)
        body = gen.function(output[gen.DRIVER], "static int imx882_resources_get")
        first = "ret = imx882_idle_check(power);"
        second = 'power->reset = gpiod_get(dev, "reset", GPIOD_ASIS);'
        swapped = body.replace(first, "ORDER_TEMP", 1).replace(second, first, 1).replace("ORDER_TEMP", second, 1)
        output[gen.DRIVER] = gen.replace_once(output[gen.DRIVER], body, swapped)
        with self.assertRaises(ValueError):
            check.validate(self.base, output, self.vendor)

    def test_reject_ignored_reset_write_errno(self):
        self.reject("static int imx882_reset_set", "ret = gpiod_set_value_cansleep(power->reset, asserted);",
                    "gpiod_set_value_cansleep(power->reset, asserted);\n\tret = 0;")

    def test_reject_missing_reset_readback(self):
        self.reject("static int imx882_reset_set", "ret = imx882_reset_observe(power, asserted);", "ret = 0;")

    def test_reject_unknown_reset_direction(self):
        self.reject("static int imx882_reset_observe", "ret != 0", "false")

    def test_reject_startup_reset_direction_write_without_readback(self):
        self.reject("static int imx882_power_on", "ret = imx882_reset_observe(power, 1);", "ret = 0;")

    def test_reject_missing_power_validation_before_reset_release(self):
        self.reject("static int imx882_power_on", "ret = imx882_supplies_observe(power, 1);", "ret = 0;")

    def test_reject_clock_release_before_regulator_disable_success(self):
        self.reject("static int imx882_power_off", "ret = regulator_disable(power->supplies[supply].consumer);",
                    "imx882_mclk_release(power);\n\t\tret = regulator_disable(power->supplies[supply].consumer);")

    def test_reject_uncertain_dependency_retry(self):
        self.reject("static int imx882_power_off", "return power->first_error;", "power->first_error = 0;")

    def test_reject_missing_partial_supply_ledger_update(self):
        self.reject("static int imx882_power_off", "*enabled_supplies &= ~BIT(supply);", "*enabled_supplies = 0;")

    def test_reject_stopping_after_only_published_stream_success(self):
        self.reject("static int imx882_stream", "ret = imx882_stop(camera);", "ret = camera->streaming ? imx882_stop(camera) : 0;")

    def test_reject_missing_control_power_guard(self):
        self.reject("static int imx882_set_control", "ret = imx882_power_validate(&camera->power);", "ret = 0;")

    def test_reject_reset_fault_hiding_first_error(self):
        self.reject("static int imx882_power_fault", "if (!power->first_error)", "if (true)")

    def test_reject_managed_resource_release_on_uncertain_remove(self):
        self.reject("static int imx882_resources_get", "ret = regulator_bulk_get(dev, IMX882_NUM_SUPPLIES, power->supplies);",
                    "ret = devm_regulator_bulk_get(dev, IMX882_NUM_SUPPLIES, power->supplies);")

    def test_reject_unconditional_owner_free_on_remove(self):
        self.reject("static void imx882_camera_remove", "camera->power.first_error || imx882_power_active(camera)", "false")

    def test_reject_free_in_uncertain_remove_branch(self):
        self.reject("static void imx882_camera_remove", "\t\treturn;", "\t\timx882_resources_put(camera);\n\t\treturn;")

    def test_reject_module_unload_of_retained_storage(self):
        output = dict(self.output)
        output[gen.KCONFIG] = output[gen.KCONFIG].replace('\tbool "Nothing Tetris IMX882 V4L2 streaming candidate"',
                                                           '\ttristate "Nothing Tetris IMX882 V4L2 streaming candidate"')
        with self.assertRaises(ValueError):
            check.validate(self.base, output, self.vendor)

    def test_reject_media_packet_api_drift(self):
        self.reject("static int imx882_frame_desc", "desc->entry[1].bus.csi2.dt = 0x30;", "desc->entry[1].bus.csi2.dt = 0x2b;")

    def test_reject_binding_source_omission(self):
        output = dict(self.output)
        output[gen.BINDING] = output[gen.BINDING].replace("      - const: xclk-source\n", "")
        with self.assertRaises(ValueError):
            check.validate(self.base, output, self.vendor)

    def test_real_prepared_patch_application_preserves_config_and_headers(self):
        with gen.tempfile.TemporaryDirectory(prefix="stream-owner-prepared-") as directory:
            kernel = Path(directory)
            for path, text in self.base.items():
                target = kernel / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            config = "CONFIG_LTO_CLANG_THIN=y\nCONFIG_CFI=y\n"
            (kernel / ".config").write_text(config)
            stage.apply(kernel, self.base, self.output, gen.HERE / "stream-owner.patch")
            for path, text in self.output.items():
                self.assertEqual((kernel / path).read_text(), text)
            for path in (gen.CORE, gen.TABLES, gen.IDENTITY, gen.TOP):
                self.assertEqual((kernel / path).read_text(), self.base[path])
            self.assertEqual((kernel / ".config").read_text(), config)
            with self.assertRaisesRegex(ValueError, "differs from exact packaged"):
                stage.verify_prepared(kernel, self.base)

    def test_reject_wrong_prepared_clock_provider_before_staging(self):
        with gen.tempfile.TemporaryDirectory(prefix="stream-owner-wrong-") as directory:
            kernel = Path(directory)
            for path, text in self.base.items():
                target = kernel / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            (kernel / gen.TOP).write_text(self.base[gen.TOP] + "\n/* unverified clock source */\n")
            with self.assertRaisesRegex(ValueError, "differs from exact packaged"):
                stage.apply(kernel, self.base, self.output, gen.HERE / "stream-owner.patch")
            self.assertEqual((kernel / gen.DRIVER).read_text(), self.base[gen.DRIVER])

    def test_ci_mutation_refuses_locally_before_any_process_or_write(self):
        with patch.dict(os.environ, {"CI": "false", "GITHUB_ACTIONS": "false"}), \
                patch.object(sys, "argv", ["stage.py", "--ci-apply"]), \
                patch.object(stage.check, "check") as checked, \
                patch.object(stage.subprocess, "run") as process, \
                patch.object(Path, "mkdir") as mkdir:
            with self.assertRaisesRegex(ValueError, "CI-only"):
                stage.main()
        checked.assert_not_called()
        process.assert_not_called()
        mkdir.assert_not_called()

    def test_ci_requires_portable_source_inputs_and_has_no_compile_commands(self):
        parser = argparse.ArgumentParser()
        gen.arguments(parser, explicit=True)
        self.assertTrue(all(action.required for action in parser._actions if action.dest != "help"))
        source = (gen.HERE / "stage.py").read_text()
        for command in ("make", "clang", "dtc", "qemu", "llvm-dis", "llvm-readelf"):
            self.assertNotIn('"' + command + '"', source)
        self.assertNotIn('"scripts/config"', source)

    def test_staging_manifest_stays_disabled_and_not_capture(self):
        manifest = json.loads((gen.HERE / "STAGING.json").read_text())
        self.assertEqual(manifest["kernel_commit"], gen.KERNEL)
        self.assertEqual(manifest["shipping_selector"], "CONFIG_VIDEO_IMX882_TETRIS=n")
        self.assertEqual(manifest["object"], gen.DRIVER.removesuffix(".c") + ".o")
        self.assertEqual(manifest["runtime_activation"], "disabled; no DT delta")


if __name__ == "__main__":
    unittest.main()
