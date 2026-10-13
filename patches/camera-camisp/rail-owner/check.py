#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Static source/ABI, ownership and application checks; no C execution."""
import argparse
import json
from pathlib import Path
import re

import yaml
import generate as gen


def require(condition, message):
    if not condition:
        raise ValueError(message)


def ordered(text, markers):
    position = 0
    for marker in markers:
        position = text.index(marker, position) + len(marker)


def validate_request_path(base):
    """ASIS skips direction setup, not the earlier GPIO/mux request callback."""
    devres = base["drivers/gpio/gpiolib-devres.c"]
    require("return devm_gpiod_get_index(dev, con_id, 0, flags);" in
            gen.block(devres, "struct gpio_desc *__must_check devm_gpiod_get("), "managed GPIO entry changed")
    require("desc = gpiod_get_index(dev, con_id, idx, flags);" in
            gen.block(devres, "struct gpio_desc *__must_check devm_gpiod_get_index("), "managed request changed")
    gpio = base["drivers/gpio/gpiolib.c"]
    require("return gpiod_find_and_request(dev, fwnode, con_id, idx, flags, label, true);" in
            gen.block(gpio, "struct gpio_desc *__must_check gpiod_get_index("), "GPIO lookup entry changed")
    ordered(gen.block(gpio, "struct gpio_desc *gpiod_find_and_request"),
            ["ret = gpiod_request(desc, label);", "if (ret)", "return ERR_PTR(ret);",
             "ret = gpiod_configure_flags(desc, con_id, lookupflags, flags);"])
    ordered(gen.block(gpio, "int gpiod_request("),
            ["try_module_get(desc->gdev->owner)", "gpiod_request_commit(desc, label)", "gpio_device_get(desc->gdev)"])
    ordered(gen.block(gpio, "static int gpiod_request_commit"),
            ["test_and_set_bit(GPIOD_FLAG_REQUESTED", "return -EBUSY;",
             "if (guard.gc->request)", "ret = guard.gc->request(guard.gc, offset);", "if (ret)",
             "goto out_clear_bit;", "guard.gc->get_direction", "gpiod_get_direction(desc);"])
    require("return pinctrl_gpio_request(gc, offset);" in gen.block(gpio, "int gpiochip_generic_request"),
            "GPIO request no longer delegates to pinctrl")
    ordered(gen.block(gpio, "int gpiod_configure_flags"),
            ["gpiod_set_transitory", "if (!(dflags & GPIOD_FLAGS_BIT_DIR_SET))", "return 0;",
             "gpiod_direction_output_nonotify"])
    require("GPIOD_ASIS\t= 0," in base["include/linux/gpio/consumer.h"], "ASIS flags changed")
    ordered(gen.block(base["drivers/pinctrl/core.c"], "int pinctrl_gpio_request"),
            ["pinctrl_get_device_gpio_range", "mutex_lock(&pctldev->mutex)", "gpio_to_pin",
             "pinmux_request_gpio", "mutex_unlock(&pctldev->mutex)"])
    mux = base["drivers/pinctrl/pinmux.c"]
    require("pin_request(pctldev, pin, owner, range)" in gen.block(mux, "int pinmux_request_gpio"),
            "pinctrl GPIO reservation changed")
    ordered(gen.block(mux, "static int pin_request"),
            ["scoped_guard(mutex, &desc->mux_lock)", "(!gpio_range || ops->strict)",
             "desc->mux_usecount", "(gpio_range || ops->strict)", "desc->gpio_owner",
             "desc->gpio_owner = owner;", "try_module_get(pctldev->owner)",
             "if (gpio_range && ops->gpio_request_enable)",
             "status = ops->gpio_request_enable(pctldev, gpio_range, pin);"])
    ordered(gen.block(mux, "int pinmux_enable_setting"), ["pin_request", "ret = ops->set_mux"])
    paris = base["drivers/pinctrl/mediatek/pinctrl-paris.c"]
    ops = gen.block(paris, "static const struct pinmux_ops")
    require(".gpio_request_enable\t= mtk_pinmux_gpio_request_enable," in ops and ".strict" not in ops,
            "Paris non-strict mux ownership changed; review acquisition again")
    ordered(gen.block(paris, "mtk_build_gpiochip("),
            ["chip->parent\t\t= hw->dev;", "chip->request\t\t= gpiochip_generic_request;", "gpiochip_add_data(chip, hw)"])
    require("return mtk_hw_set_value(hw, desc, PINCTRL_PIN_REG_MODE," in
            gen.block(paris, "static int mtk_pinmux_gpio_request_enable"), "ASIS request MODE write changed")
    require("hw->soc->gpio_m" in gen.block(paris, "static int mtk_pinmux_gpio_request_enable"),
            "GPIO mux target changed")
    require(".gpio_m = 0," in gen.block(base["drivers/pinctrl/mediatek/pinctrl-mt6878.c"],
                                      "static const struct mtk_pin_soc"), "MT6878 GPIO mode changed")
    common = base["drivers/pinctrl/mediatek/pinctrl-mtk-common-v2.c"]
    ordered(gen.block(common, "int mtk_hw_set_value"), ["mtk_hw_pin_field_get", "mtk_rmw"])
    ordered(gen.block(common, "void mtk_rmw("),
            ["spin_lock_irqsave(&pctl->lock", "mtk_r32", "mtk_w32", "spin_unlock_irqrestore"])


def validate_native(base):
    validate_request_path(base)
    gpio = base["include/linux/gpio/consumer.h"]
    require("int gpiod_set_value_cansleep(struct gpio_desc *desc, int value);" in gpio,
            "GPIO setter error ABI changed")
    fixed = base["drivers/regulator/fixed.c"]
    require("GPIOD_OUT_LOW" in fixed and "GPIOD_FLAGS_BIT_NONEXCLUSIVE" in fixed and "cfg.ena_gpiod" in fixed,
            "fixed-regulator startup basis changed")
    core = base["drivers/regulator/core.c"]
    enable = gen.block(core, "static int _regulator_enable(struct regulator *regulator)\n{")
    disable = gen.block(core, "static int _regulator_disable(struct regulator *regulator)\n{")
    ordered(enable, ["if (rdev->use_count == 0)", "_regulator_is_enabled(rdev)",
                     "_regulator_do_enable(rdev)", "rdev->use_count++"])
    ordered(disable, ["rdev->use_count == 1", "_regulator_do_disable(rdev)", "if (ret < 0)",
                      "return ret;", "rdev->use_count = 0", "rdev->use_count > 1", "rdev->use_count--"])
    paris = base["drivers/pinctrl/mediatek/pinctrl-paris.c"]
    require("PINCTRL_PIN_REG_MODE" in gen.block(paris, "static int mtk_pinmux_gpio_request_enable"),
            "ASIS request mux side effect changed")
    ordered(gen.block(paris, "static int mtk_gpio_direction_output"),
            ["mtk_gpio_set", "if (ret)", "return ret;", "pinctrl_gpio_direction_output"])
    ordered(gen.block(paris, "static int mtk_gpio_get_direction("),
            ["mtk_hw_get_value(hw, desc, PINCTRL_PIN_REG_DIR", "if (err)", "return err;",
             "if (value)", "return GPIO_LINE_DIRECTION_OUT;", "return GPIO_LINE_DIRECTION_IN;"])
    require("return mtk_hw_set_value(hw, desc, PINCTRL_PIN_REG_DIR, !input);" in
            gen.block(paris, "static int mtk_pinmux_gpio_set_direction"), "Paris output direction encoding changed")
    require("PINCTRL_PIN_REG_DI" in gen.block(paris, "static int mtk_gpio_get("), "GPIO observation is not a DI read")
    require("platform_set_drvdata(pdev, hw);" in gen.block(paris, "int mtk_paris_pinctrl_probe"),
            "pinctrl owner private-data contract changed")
    require("hw->dev = &pdev->dev;" in paris, "pinctrl owner identity contract changed")
    common = base["drivers/pinctrl/mediatek/pinctrl-mtk-common-v2.c"]
    require("EXPORT_SYMBOL_GPL(mtk_hw_get_value);" in common, "real pinctrl read interface unavailable")
    getter = gen.block(common, "int mtk_hw_get_value")
    require("mtk_hw_pin_field_get" in getter and "return err;" in getter and "mtk_r32" in getter,
            "pinctrl read/error contract changed")


def validate_payload(base, output):
    require(set(output) == {gen.DRIVER, gen.BINDING, gen.KCONFIG, gen.MAKEFILE, gen.DTS}, "unexpected payload scope")
    code = output[gen.DRIVER]
    rows = {role: (int(pin), int(voltage)) for role, pin, voltage in
            re.findall(r'\{ "(\w+)", (\d+), (\d+) \}', code)}
    require(rows == gen.RAILS, "invented rail topology or voltage")
    owner = gen.block(code, "static int tetris_rail_gpio_contract")
    ordered(owner, ["of_count_phandle_with_args", "of_parse_phandle_with_args", "gpio.args_count != 2",
                    "gpio.args[0] != spec->pin", "gpio.args[1] != 0", "of_find_device_by_node",
                    "device_lock", "!owner->dev.driver", "strcmp(owner->dev.driver->name", '"mt6878-pinctrl"',
                    "ret = -EOPNOTSUPP", "platform_get_drvdata", "hw->dev != &owner->dev",
                    "hw->chip.parent != &owner->dev", "!hw->chip.gpiodev",
                    "spin_lock_irqsave", "ret = mtk_hw_get_value(hw, pin, PINCTRL_PIN_REG_MODE",
                    "if (!ret)", "ret = mtk_hw_get_value(hw, pin, PINCTRL_PIN_REG_DIR",
                    "if (!ret)", "ret = mtk_hw_get_value(hw, pin, PINCTRL_PIN_REG_DO",
                    "if (!ret)", "ret = mtk_hw_get_value(hw, pin, PINCTRL_PIN_REG_DI",
                    "spin_unlock_irqrestore", "mode != hw->soc->gpio_m", "output != 0", "input != 0",
                    "ret = -EBUSY", "direction != 0 && direction != 1", "ret = -EOPNOTSUPP", "device_unlock", "put_device", "return ret;"])
    for forbidden in ("mtk_hw_set_value", "writel", "ioremap", "gpiod_direction_output", "GPIOD_OUT", "regulator_enable"):
        require(forbidden not in owner, "owner preflight must be read-only: " + forbidden)
    probe = gen.block(code, "static int tetris_camera_rail_probe")
    ordered(probe, ["of_get_regulator_init_data",
                    "init->constraints.min_uV != spec->microvolts", "init->constraints.max_uV != spec->microvolts",
                    "init->constraints.boot_on", "init->constraints.always_on", "init->constraints.initial_state",
                    "init->constraints.apply_uV = 0", "ret = tetris_rail_gpio_contract(node, spec);",
                    "if (ret)", "return dev_err_probe", 'devm_gpiod_get(dev, "enable", GPIOD_ASIS)',
                    "IS_ERR(rail->gpio)", "gpiod_is_active_low", "tetris_rail_startup_observe(rail)",
                    "if (ret < 0)", "return dev_err_probe", "ret = gpiod_direction_output(rail->gpio, 0)",
                    "if (ret)", "return dev_err_probe", "tetris_rail_observe(rail, 0)", "if (ret < 0)",
                    "return dev_err_probe", "config.init_data = init", "devm_regulator_register"])
    startup = gen.block(code, "static int tetris_rail_startup_observe")
    ordered(startup, ["if (rail->first_error)", "return rail->first_error", "gpiod_get_direction", "direction < 0",
                      "tetris_rail_fault(rail, direction)", "direction != 0 && direction != 1", "-EOPNOTSUPP",
                      "gpiod_get_value_cansleep", "level < 0", "tetris_rail_fault(rail, level)",
                      "level != 0", "tetris_rail_fault(rail, -EBUSY)", "return 0;"])
    require(code.count("tetris_rail_startup_observe(") == 2, "input-low allowance escaped startup-only path")
    for forbidden in ("gpiod_direction", "gpiod_set", "last_level ="):
        require(forbidden not in startup, "startup observation writes or fabricates state: " + forbidden)
    observe = gen.block(code, "static int tetris_rail_observe")
    ordered(observe, ["if (rail->first_error)", "return rail->first_error", "gpiod_get_direction", "direction < 0",
                      "tetris_rail_fault(rail, direction)", "if (direction != 0)", "-EOPNOTSUPP",
                      "gpiod_get_value_cansleep", "level < 0", "tetris_rail_fault(rail, level)",
                      "level != expected", "level ? -EBUSY : -EIO", "return level;"])
    transition = gen.block(code, "static int tetris_rail_set")
    ordered(transition, ["tetris_rail_observe(rail, rail->last_level)", "ret < 0", "return ret;",
                         "ret == target", "return 0;", "ret = gpiod_set_value_cansleep", "if (ret)",
                         "return tetris_rail_fault(rail, ret)", "tetris_rail_observe(rail, target)",
                         "ret < 0", "return ret;", "rail->last_level = ret", "return 0;"])
    require("return tetris_rail_observe(rail, rail->last_level);" in gen.block(code, "static int tetris_rail_is_enabled"),
            "enabled status is not backed by a GPIO observation")
    for forbidden in ("ena_gpiod =", "GPIOD_OUT_LOW", "GPIOD_FLAGS_BIT_NONEXCLUSIVE", "enable_count",
                      "use_count", "regulator_get_exclusive", "regulator_force_disable", "regulator_enable_regmap",
                      "arm_smccc", "ioremap", "cookie", "ready", "first_error = 0"):
        require(forbidden not in code, "duplicated owner, bypass or fabricated status: " + forbidden)
    require(".probe = tetris_camera_rail_probe" in code and "builtin_platform_driver(tetris_camera_rail_driver)" in code,
            "provider lacks real built-in probe registration")
    require(".suppress_bind_attrs = true" in code and ".shutdown" not in code and ".remove" not in code,
            "provider acquired unproven force-off/teardown policy")
    config = output[gen.KCONFIG]
    require("depends on OF && GPIOLIB && PINCTRL_MT6878\n\tdefault n" in config, "native owner dependency/default changed")
    schema = yaml.safe_load(output[gen.BINDING])
    props = schema["properties"]
    require(props["compatible"]["const"] == "nothing,tetris-camera-gpio-regulator", "fixed fallback compatible added")
    require(props["nothing,rail"]["enum"] == list(gen.RAILS), "binding rail selectors changed")
    for prop in ("regulator-boot-on", "regulator-always-on", "pinctrl-0", "pinctrl-names", "vin-supply"):
        require(props[prop] is False, "binding permits pre-observation startup: " + prop)
    dt = output[gen.DTS]
    require(dt.count('status = "disabled";') == 4, "rail nodes activated prematurely")
    require("regulator-fixed" not in dt and "enable-active-high;" not in dt, "fixed provider fallback remains")
    for role, (pin, voltage) in gen.RAILS.items():
        node = gen.block(dt, f"camera_main_{role}: regulator-camera-main-{role}")
        require(f'nothing,rail = "{role}";' in node and f"enable-gpios = <&pio {pin} GPIO_ACTIVE_HIGH>;" in node,
                "DT rail selector/pin mismatch")
        require(f"regulator-min-microvolt = <{voltage}>;" in node and f"regulator-max-microvolt = <{voltage}>;" in node,
                "DT voltage differs from NOS")
    require(output[gen.MAKEFILE].count("obj-$(CONFIG_REGULATOR_TETRIS_CAMERA_GPIO)") == 1, "duplicate provider object")


def check(upstream=gen.ROOT.parent, archive=None, device_repo=None, modules_repo=None):
    base, output, vendor, provider, dt, evidence = gen.build(upstream, archive, device_repo, modules_repo)
    validate_native(base)
    validate_payload(base, output)
    require((gen.HERE / "provider.patch").read_text() == provider, "stale provider delta")
    require((gen.HERE / "disabled-description.patch").read_text() == dt, "stale disabled DT delta")
    require(json.loads((gen.HERE / "evidence.json").read_text()) == evidence, "source evidence changed")
    print("PASS: pinned ASIS request-to-MODE-write path, read-only pre-request gate and regulator accounting")
    print("OPEN: pre-request snapshot is not atomic GPIO/mux or firmware ownership; no DT activation")
    print("PASS: exact NOS/Linux sources, disabled rail DT and scoped patch application")
    print("NOT RUN: compilation, DTB/schema, physical rail transition or capture")
    return base, output, vendor


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=gen.ROOT.parent)
    parser.add_argument("--kernel-archive", type=Path)
    parser.add_argument("--device-repo", type=Path)
    parser.add_argument("--modules-repo", type=Path)
    args = parser.parse_args()
    check(args.upstream, args.kernel_archive, args.device_repo, args.modules_repo)
