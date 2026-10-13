#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Static rejection tests; never compile C or emulate a GPIO/regulator."""
import ast
import json
import os
import unittest
from unittest.mock import patch

import check
import generate as gen
import run_ci


class RailSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.output, cls.vendor = check.check()

    def reject(self, old, new):
        output = dict(self.output)
        output[gen.DRIVER] = gen.replace_once(output[gen.DRIVER], old, new)
        with self.assertRaises(ValueError):
            check.validate_payload(self.base, output)

    def reject_native(self, path, old, new):
        base = dict(self.base)
        base[path] = gen.replace_once(base[path], old, new)
        with self.assertRaises(ValueError):
            check.validate_native(base)

    def test_python_sources_parse(self):
        for name in ("generate.py", "check.py", "test_source.py", "run_ci.py"):
            ast.parse((gen.HERE / name).read_text())

    def test_reject_forced_low_request(self):
        self.reject('devm_gpiod_get(dev, "enable", GPIOD_ASIS)', 'devm_gpiod_get(dev, "enable", GPIOD_OUT_LOW)')

    def test_reject_nonexclusive_physical_gpio_owner(self):
        self.reject("GPIOD_ASIS", "GPIOD_ASIS | GPIOD_FLAGS_BIT_NONEXCLUSIVE")

    def test_reject_omitted_native_pinctrl_observation(self):
        self.reject("ret = tetris_rail_gpio_contract(node, spec);", "ret = 0;")

    def test_reject_inherited_mux_takeover(self):
        self.reject("mode != hw->soc->gpio_m", "false")

    def test_reject_inherited_output_latch_on(self):
        self.reject("output != 0", "false")

    def test_reject_inherited_pad_on(self):
        self.reject("input != 0", "false")

    def test_reject_unknown_direction(self):
        self.reject("if (!ret && direction != 0 && direction != 1)", "if (!ret && false)")

    def test_reject_wrong_native_owner_before_private_data_cast(self):
        self.reject('strcmp(owner->dev.driver->name, "mt6878-pinctrl")', "false")

    def test_reject_unregistered_gpiochip(self):
        self.reject("!hw->chip.gpiodev", "false")

    def test_reject_swallowed_mode_read_error(self):
        self.reject("ret = mtk_hw_get_value(hw, pin, PINCTRL_PIN_REG_MODE, &mode);",
                    "mtk_hw_get_value(hw, pin, PINCTRL_PIN_REG_MODE, &mode);\n\tret = 0;")

    def test_preflight_must_precede_mux_writing_request(self):
        output = dict(self.output)
        code = output[gen.DRIVER]
        before = "ret = tetris_rail_gpio_contract(node, spec);"
        request = 'rail->gpio = devm_gpiod_get(dev, "enable", GPIOD_ASIS);'
        code = code.replace(before, "TEMP_ORDER", 1).replace(request, before, 1).replace("TEMP_ORDER", request, 1)
        output[gen.DRIVER] = code
        with self.assertRaises(ValueError):
            check.validate_payload(self.base, output)

    def test_startup_accepts_known_input_low_but_callbacks_remain_output_only(self):
        startup = gen.block(self.output[gen.DRIVER], "static int tetris_rail_startup_observe")
        self.assertIn("direction != 0 && direction != 1", startup)
        self.assertIn("level != 0", startup)
        steady = gen.block(self.output[gen.DRIVER], "static int tetris_rail_observe")
        self.assertIn("if (direction != 0)", steady)
        probe = gen.block(self.output[gen.DRIVER], "static int tetris_camera_rail_probe")
        check.ordered(probe, ["tetris_rail_startup_observe(rail)", "gpiod_direction_output(rail->gpio, 0)",
                              "tetris_rail_observe(rail, 0)", "devm_regulator_register"])

    def test_reject_high_input_during_startup(self):
        self.reject("if (level != 0)", "if (false)")

    def test_reject_unknown_startup_direction(self):
        self.reject("if (direction != 0 && direction != 1)", "if (false)")

    def test_reject_input_tolerance_in_steady_callbacks(self):
        self.reject("if (direction != 0)", "if (direction != 0 && direction != 1)")

    def test_native_request_hook_must_be_traced(self):
        self.reject_native("drivers/pinctrl/mediatek/pinctrl-paris.c",
                           "chip->request\t\t= gpiochip_generic_request;", "chip->request = NULL;")

    def test_native_asis_request_mode_write_must_be_traced(self):
        self.reject_native("drivers/pinctrl/mediatek/pinctrl-paris.c",
                           "return mtk_hw_set_value(hw, desc, PINCTRL_PIN_REG_MODE,\n\t\t\t\thw->soc->gpio_m);",
                           "return 0;")

    def test_native_strict_mux_change_requires_new_review(self):
        self.reject_native("drivers/pinctrl/mediatek/pinctrl-paris.c",
                           ".gpio_request_enable\t= mtk_pinmux_gpio_request_enable,",
                           ".gpio_request_enable\t= mtk_pinmux_gpio_request_enable,\n\t.strict = true,")

    def test_native_gpiolib_request_must_precede_direction_flags(self):
        path = "drivers/gpio/gpiolib.c"
        base = dict(self.base)
        before = "ret = gpiod_request(desc, label);"
        flags = "ret = gpiod_configure_flags(desc, con_id, lookupflags, flags);"
        code = base[path].replace(before, "TEMP_ORDER", 1).replace(flags, before, 1).replace("TEMP_ORDER", flags, 1)
        base[path] = code
        with self.assertRaises(ValueError):
            check.validate_native(base)

    def test_native_checked_do_write_must_precede_dir_transition(self):
        self.reject_native("drivers/pinctrl/mediatek/pinctrl-paris.c",
                           "ret = mtk_gpio_set(chip, gpio, value);", "ret = 0;")

    def test_reject_swallowed_native_get_error(self):
        self.reject("ret = mtk_hw_get_value(hw, pin, PINCTRL_PIN_REG_DO, &output);",
                    "mtk_hw_get_value(hw, pin, PINCTRL_PIN_REG_DO, &output);\n\tret = 0;")

    def test_reject_missing_off_gate(self):
        self.reject("ret = tetris_rail_startup_observe(rail);", "ret = 0;")

    def test_reject_swallowed_set_error(self):
        self.reject("ret = gpiod_set_value_cansleep(rail->gpio, target);",
                    "gpiod_set_value_cansleep(rail->gpio, target);\n\tret = 0;")

    def test_reject_missing_postwrite_observation(self):
        self.reject("ret = tetris_rail_observe(rail, target);", "ret = target;")

    def test_reject_invented_voltage(self):
        self.reject('{ "dvdd", 21, 1200000 }', '{ "dvdd", 21, 1100000 }')

    def test_reject_core_gpio_enable_pin_bypass(self):
        self.reject("config.driver_data = rail;", "config.driver_data = rail;\n\tconfig.ena_gpiod = rail->gpio;")

    def test_reject_boot_on_constraint(self):
        self.reject("init->constraints.boot_on", "false")

    def test_reject_private_shared_enable_count(self):
        self.reject("rail->last_level = ret;", "rail->last_level = ret;\n\trdev->use_count++;")

    def test_reject_software_only_enabled_status(self):
        self.reject("return tetris_rail_observe(rail, rail->last_level);", "return rail->last_level;")

    def test_reject_fault_clear_retry(self):
        self.reject("rail->last_level = ret;", "rail->last_level = ret;\n\trail->first_error = 0;")

    def test_reject_enabled_dt(self):
        output = dict(self.output)
        output[gen.DTS] = output[gen.DTS].replace('status = "disabled";', 'status = "okay";', 1)
        with self.assertRaises(ValueError):
            check.validate_payload(self.base, output)

    def test_reject_stock_shared_client_drift(self):
        vendor = dict(self.vendor)
        name = "arch/arm64/boot/dts/mediatek/cust_mt6878_camera_v4l2.dtsi"
        vendor[name] = vendor[name].replace(b"dovdd-supply = <&camera_common_dovdd>;", b"dovdd-supply = <&private_dovdd>;", 1)
        with self.assertRaises(ValueError):
            gen.verify_vendor(vendor)

    def test_reject_wrong_base_application(self):
        base = dict(self.base)
        base[gen.MAKEFILE] = base[gen.MAKEFILE].replace("fixed.o", "other.o")
        with self.assertRaises(gen.subprocess.CalledProcessError):
            gen.apply_check(base, (gen.HERE / "provider.patch").read_text(),
                            (gen.HERE / "disabled-description.patch").read_text(), self.output)

    def test_dt_patch_applies_inside_a_larger_board_without_root_anchor(self):
        base, output = dict(self.base), dict(self.output)
        prefix, suffix = "/ {\n\t/* Existing board nodes precede the camera rails. */\n", "};\n"
        base[gen.DTS] = prefix + base[gen.DTS] + suffix
        output[gen.DTS] = prefix + output[gen.DTS] + suffix
        gen.apply_check(base, (gen.HERE / "provider.patch").read_text(),
                        (gen.HERE / "disabled-description.patch").read_text(), output)

    def test_ci_runner_refuses_before_process_or_write(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), \
                patch.object(run_ci.subprocess, "run") as process, \
                patch.object(run_ci.subprocess, "check_output") as query:
            with self.assertRaisesRegex(ValueError, "CI-only"):
                run_ci.main()
        process.assert_not_called()
        query.assert_not_called()

    def test_ci_runner_builds_real_native_object_and_checks_result(self):
        tree = ast.parse((gen.HERE / "run_ci.py").read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
        self.assertEqual(ast.unparse(main.body[0]), "ci_only()")
        source = ast.unparse(main)
        self.assertIn("'REGULATOR_TETRIS_CAMERA_GPIO'", source)
        self.assertIn("'PINCTRL_MT6878'", source)
        self.assertIn("run([*make, target])", source)
        self.assertIn("smoke.object_identity(artifact)", source)
        self.assertIn("identity_helper_sha256=gen.sha(helper.read_bytes())", source)
        self.assertIn("verify_security_profile(original, resolved_text)", source)
        self.assertNotIn("'-d'", source)
        self.assertNotIn("'LTO_NONE'", source)
        self.assertIn("manifest.update(status='failed'", source)
        self.assertNotIn("dtc", source)
        self.assertNotIn("GPIOD_OUT", source)

    def test_ci_rejects_security_profile_downgrade(self):
        original = (gen.PACKAGE / "config-postmarketos-mediatek-mt6878.aarch64").read_text()
        for symbol in ("LTO_CLANG_THIN", "CFI", "SHADOW_CALL_STACK"):
            changed = original.replace(f"CONFIG_{symbol}=y", f"# CONFIG_{symbol} is not set")
            with self.subTest(symbol=symbol), self.assertRaisesRegex(ValueError, "profile changed"):
                run_ci.verify_security_profile(original, changed)
        self.assertEqual(run_ci.verify_security_profile(original, original)["CFI"], "y")

    def test_ci_requires_portable_explicit_source_inputs(self):
        tree = ast.parse((gen.HERE / "run_ci.py").read_text())
        required = {node.args[0].value for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_argument" and node.args
                    and any(kw.arg == "required" and isinstance(kw.value, ast.Constant)
                            and kw.value.value is True for kw in node.keywords)}
        self.assertTrue({"--kernel-archive", "--device-repo", "--modules-repo"}.issubset(required))
        vendor, _ = gen.sources(gen.ROOT / "nonexistent-upstream",
                                gen.ROOT.parent / "android_kernel_device_modules_6.1_nothing_mt6878",
                                gen.ROOT.parent / "android_kernel_modules_nothing_mt6878")
        self.assertEqual(vendor, self.vendor)

    def test_ci_checks_all_prepared_pinctrl_sources_against_verified_archive(self):
        with gen.tempfile.TemporaryDirectory(prefix="rail-owner-source-") as directory:
            kernel = gen.Path(directory)
            for path in gen.NATIVE:
                target = kernel / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(self.base[path])
            table, _ = gen.prepared_pin_table(self.base)
            (kernel / gen.PIN_TABLE).write_text(table)
            hashes = run_ci.verify_prepared_owner(kernel, self.base)
            for path in ("drivers/pinctrl/core.c", "drivers/pinctrl/pinmux.c",
                         "drivers/pinctrl/mediatek/pinctrl-mt6878.c", "drivers/pinctrl/mediatek/pinctrl-paris.c"):
                self.assertIn(path, hashes)
                target = kernel / path
                target.write_text(self.base[path] + "\n/* unverified change */\n")
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, "differs from pin"):
                    run_ci.verify_prepared_owner(kernel, self.base)
                target.write_text(self.base[path])

    def test_ci_rejects_unverified_soc_pin_table_changes(self):
        with gen.tempfile.TemporaryDirectory(prefix="rail-owner-table-") as directory:
            kernel = gen.Path(directory)
            table, _ = gen.prepared_pin_table(self.base)
            for path in gen.NATIVE:
                target = kernel / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(table if path == gen.PIN_TABLE else self.base[path])
            run_ci.verify_prepared_owner(kernel, self.base)
            (kernel / gen.PIN_TABLE).write_text(table + "\n/* unverified pin metadata */\n")
            with self.assertRaisesRegex(ValueError, "differs from pin"):
                run_ci.verify_prepared_owner(kernel, self.base)

    def test_manifest_keeps_all_hardware_and_install_gates_open(self):
        manifest = json.loads((gen.HERE / "STAGING.json").read_text())
        self.assertEqual(manifest["ci_object"], gen.DRIVER.removesuffix(".c") + ".o")
        self.assertEqual(manifest["shipping_selector"], "CONFIG_REGULATOR_TETRIS_CAMERA_GPIO=n")
        self.assertEqual(manifest["shared_dovdd_stock_consumers"], ["sensor0@1a", "sensor1@10", "sensor2@36"])
        self.assertEqual(manifest["kernel_commit"], gen.KERNEL)
        self.assertEqual(manifest["modules_commit"], gen.MODULES)


if __name__ == "__main__":
    unittest.main()
