#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check actual source composition and lifecycle/error paths without C execution."""
import argparse
import json
import re

import yaml
import generate as gen


def require(condition, message):
    if not condition:
        raise ValueError(message)


def ordered(text, markers):
    cursor = 0
    for marker in markers:
        cursor = text.index(marker, cursor) + len(marker)


def registers(text, marker, vendor=False):
    body = gen.block(text, marker)
    body = re.sub(r"/\*.*?\*/|//[^\n]*", "", body, flags=re.S)
    if vendor:
        values = [int(value.strip(), 0) for value in body.split(",") if value.strip()]
        require(len(values) % 2 == 0, "odd vendor register table")
        return list(zip(values[::2], values[1::2]))
    return [(int(address, 16), int(value, 16)) for address, value in
            re.findall(r"\{ 0x([0-9a-f]+), 0x([0-9a-f]+) \}", body)]


def validate(base, output, vendor):
    require(set(output) == set(gen.TARGETS), "unexpected runtime delta scope")
    code = output[gen.DRIVER]
    for kind, name in (("void", "release"), ("int", "acquire")):
        marker = "static " + kind + " imx882_mclk_" + name
        require(gen.function(code, marker) == gen.function(base[gen.IDENTITY], marker),
                "MCLK contract differs from packaged identity 0121")
    acquired = gen.block(code, "static int imx882_mclk_acquire")
    ordered(acquired, ["clk_rate_exclusive_get(imx882->xclk)", "__clk_is_enabled(imx882->xclk)",
                       "clk_rate_exclusive_get(imx882->xclk_source)", "clk_get_rate(imx882->xclk_source)",
                       "clk_set_parent(imx882->xclk, imx882->xclk_source)", "clk_get_parent(imx882->xclk)"])
    require("int gpiod_set_value_cansleep(struct gpio_desc *desc, int value);" in
            base["include/linux/gpio/consumer.h"], "pinned GPIO errno ABI changed")
    paris = base["drivers/pinctrl/mediatek/pinctrl-paris.c"]
    require("PINCTRL_PIN_REG_MODE" in gen.block(paris, "static int mtk_pinmux_gpio_request_enable"),
            "reset ASIS mux-writing callback requires renewed review")
    for marker in ("imx882_supply_names", "imx882_supply_uv"):
        require(gen.function(code, marker) == gen.function(base[gen.DRIVER], marker), "sensor rail contract changed")
    for source, table in (("imx882_init_setting", "imx882_init_regs"),
                          ("imx882_preview_setting", "imx882_preview_regs"),
                          ("imx882_normal_video_setting", "imx882_video_regs")):
        require(registers(vendor[gen.SENSOR], source, True) == registers(base[gen.TABLES], table),
                "shipping table differs from NOS: " + source)
    # Pure media/control/format implementations and core/table payload stay intact.
    for name in ("imx882_read_reg", "imx882_write(", "imx882_apply_controls", "imx882_init_state",
                 "imx882_enum_code", "imx882_enum_size", "imx882_set_format", "imx882_get_interval",
                 "imx882_mbus_config", "imx882_frame_desc"):
        require(gen.function(code, "static int " + name) ==
                gen.function(base[gen.DRIVER], "static int " + name), "media API/timing implementation changed: " + name)
    for name in ("imx882_video_ops", "imx882_pad_ops", "imx882_subdev_ops", "imx882_internal_ops"):
        require(gen.function(code, name) == gen.function(base[gen.DRIVER], name), "media ops changed: " + name)
    require('imx882_write(camera, 0x3206, 0)' in code, "per-unit calibration gate bypassed")
    reset = gen.block(code, "static int imx882_reset_set")
    ordered(reset, ["ret = gpiod_set_value_cansleep", "if (!ret)", "imx882_reset_observe", "imx882_power_fault"])
    ordered(gen.block(code, "static int imx882_reset_observe"),
            ["gpiod_get_direction", "ret < 0", "return ret;", "ret != 0", "-EOPNOTSUPP",
             "gpiod_get_value_cansleep", "ret < 0", "return ret;", "ret == asserted ? 0 : -EIO"])
    on = gen.block(code, "static int imx882_power_on")
    ordered(on, ["if (power->first_error)", "return power->first_error;", "imx882_idle_check(power)",
                 "imx882_mclk_acquire(power)", "imx882_idle_check(power)", "gpiod_direction_output(power->reset, 1)",
                 "imx882_reset_observe(power, 1)", "imx882_power_fault(power, ret)",
                 "imx882_enable_supply(power, IMX882_SUPPLY_AFVDD)", "*enabled_supplies |= BIT(IMX882_SUPPLY_AFVDD)",
                 "imx882_enable_supply(power, IMX882_SUPPLY_AVDD)", "*enabled_supplies |= BIT(IMX882_SUPPLY_AVDD)",
                 "imx882_enable_supply(power, IMX882_SUPPLY_DVDD)", "*enabled_supplies |= BIT(IMX882_SUPPLY_DVDD)",
                 "imx882_enable_supply(power, IMX882_SUPPLY_DOVDD)", "*enabled_supplies |= BIT(IMX882_SUPPLY_DOVDD)",
                 "pinctrl_select_state(power->pinctrl, power->mclk_4ma)", "power->mclk_selected = true",
                 "clk_prepare_enable(power->xclk)", "*clock_enabled = true", "imx882_mclk_check(power)",
                 "imx882_supplies_observe(power, 1)", "imx882_reset_set(power, 0)"])
    require("clk_prepare_enable(power->xclk_source)" not in code, "shared source gets duplicate enable owner")
    ordered(gen.block(code, "static int imx882_idle_check"),
            ["__clk_is_enabled(power->xclk)", "return -EBUSY;", "imx882_supplies_observe(power, 0)"])
    ordered(gen.block(code, "static int imx882_supplies_observe"),
            ["regulator_is_enabled", "ret < 0", "return ret;", "!!ret != enabled", "enabled ? -EIO : -EBUSY"])
    ordered(gen.block(code, "static int imx882_enable_supply"),
            ["ret = regulator_set_voltage", "if (!ret)", "ret = regulator_enable", "imx882_power_fault"])
    ordered(gen.block(code, "static int imx882_power_fault"),
            ["if (!power->first_error)", "power->first_error = error", "return power->first_error;"])
    off = gen.block(code, "static int imx882_power_off")
    ordered(off, ["if (power->first_error)", "return power->first_error;", "return 0;",
                  "imx882_reset_set(power, 1)", "if (ret)", "return ret;", "clk_disable_unprepare",
                  "*clock_enabled = false", "__clk_is_enabled(power->xclk)", "imx882_power_fault(power, -EBUSY)",
                  "pinctrl_select_state(power->pinctrl, power->mclk_off)", "if (ret)", "imx882_power_fault(power, ret)",
                  "power->mclk_selected = false", "supply = IMX882_NUM_SUPPLIES - 1", "regulator_disable",
                  "if (ret)", "return imx882_power_fault(power, ret)", "*enabled_supplies &= ~BIT(supply)",
                  "imx882_mclk_release(power)"])
    require(off.count("imx882_mclk_release(power)") == 1, "uncertain shutdown releases clock protection early")
    validate_power = gen.block(code, "static int imx882_power_validate")
    ordered(validate_power, ["power->first_error", "imx882_mclk_check", "imx882_supplies_observe(power, 1)",
                            "imx882_reset_observe(power, 0)", "imx882_power_fault"])
    stream = gen.block(code, "static int imx882_stream")
    ordered(stream, ["mutex_lock", "if (!enable)", "ret = imx882_stop(camera)", "camera->faulted",
                     "camera->first_error", "camera->streaming", "imx882_power_validate", "imx882_power_on",
                     "IMX882_REG_CHIP_ID_HIGH", "IMX882_REG_CHIP_ID_LOW", "IMX882_CHIP_ID", "imx882_write_table",
                     "imx882_write(camera, 0x0100, 1)", "camera->streaming = true", "failed:",
                     "imx882_camera_fault(camera, ret)", "imx882_stop(camera)", "camera->power.first_error", "return ret;"])
    stop = gen.block(code, "static int imx882_stop")
    ordered(stop, ["camera->power.first_error", "return imx882_camera_fault", "imx882_write(camera, 0x0100, 0)",
                   "imx882_power_off(&camera->power, &camera->enabled_supplies", "&camera->clock_enabled",
                   "if (cleanup)", "return imx882_camera_fault", "camera->streaming = false",
                   "camera->faulted = false", "camera->first_error = 0"])
    controls = gen.block(code, "static int imx882_set_control")
    ordered(controls, ["camera->faulted", "return camera->first_error", "camera->streaming",
                       "imx882_power_validate", "imx882_apply_controls", "return imx882_camera_fault"])
    probe = gen.block(code, "static int imx882_camera_probe")
    ordered(probe, ["i2c_check_functionality", "I2C_FUNC_I2C", "device_property_read_u32", "IMX882_XCLK_RATE",
                    "kzalloc", "get_device(dev)", "camera->client = client", "imx882_resources_get(camera)",
                    "goto release_resources", "mutex_init", "v4l2_async_register_subdev_sensor",
                    "release_resources:", "imx882_resources_put(camera)"])
    for forbidden in ("gpiod_direction_output", "pinctrl_select_state", "imx882_power_on", "clk_prepare_enable"):
        require(forbidden not in probe, "probe forces hardware startup: " + forbidden)
    resources = gen.block(code, "static int imx882_resources_get")
    ordered(resources, ["device_property_present", "regulator_bulk_get", "camera->supplies_acquired = true",
                        'clk_get(dev, "xclk")', 'clk_get(dev, "xclk-source")', "pinctrl_get",
                        "imx882_idle_check", 'gpiod_get(dev, "reset", GPIOD_ASIS)', "gpiod_is_active_low"])
    remove = gen.block(code, "static void imx882_camera_remove")
    ordered(remove, ["v4l2_async_unregister_subdev", "mutex_lock", "ret = imx882_stop(camera)", "mutex_unlock",
                     "v4l2_subdev_cleanup", "mutex_destroy", "camera->power.first_error || imx882_power_active(camera)",
                     "return;", "imx882_resources_put(camera)"])
    require(remove.count("imx882_resources_put(camera)") == 1, "uncertain remove releases owner inputs")
    release = gen.block(code, "static void imx882_resources_put")
    ordered(release, ["gpiod_put", "pinctrl_put", "clk_put(power->xclk_source)", "clk_put(power->xclk)",
                      "camera->supplies_acquired", "regulator_bulk_free", "kfree(camera)", "put_device(dev)"])
    require(".suppress_bind_attrs = true" in code, "unsafe manual unbind enabled")
    require("imx882_power_active(camera)" in gen.block(code, "static int imx882_camera_suspend"),
            "suspend ignores retained dependencies")
    require('\tbool "Nothing Tetris IMX882 V4L2 streaming candidate"\n\tdefault n' in output[gen.KCONFIG],
            "retained owner can unload or became default-on")
    for forbidden in ("clk_set_rate", "devm_", "regulator_force_disable", "regulator_get_exclusive", "use_count",
                      "enable_count", "arm_smccc", "ioremap", "power->first_error = 0", "cookie", "ready"):
        require(forbidden not in code, "duplicated ownership, unsafe release or bypass: " + forbidden)
    schema = yaml.safe_load(output[gen.BINDING])
    require([row["const"] for row in schema["properties"]["clock-names"]["items"]] == ["xclk", "xclk-source"],
            "stream binding lacks explicit source")
    require(len(schema["properties"]["clocks"]["items"]) == 2 and schema["properties"]["clock-frequency"]["const"] == 24000000,
            "stream binding clock contract changed")
    require(schema["properties"]["compatible"]["const"] == "nothing,tetris-imx882-stream", "media compatible changed")
    for property in ("port", "pinctrl-names", "reset-gpios", "afvdd-supply", "avdd-supply", "dvdd-supply", "dovdd-supply"):
        require(schema["properties"][property] == yaml.safe_load(base[gen.BINDING])["properties"][property],
                "unrelated sensor interface changed: " + property)


def check(archive=None, device_repo=None, modules_repo=None):
    upstream = gen.ROOT.parent
    base, output, vendor, delta, evidence = gen.build(
        archive or upstream / ("linux-" + gen.KERNEL + ".tar.gz"),
        device_repo or upstream / "android_kernel_device_modules_6.1_nothing_mt6878",
        modules_repo or upstream / "android_kernel_modules_nothing_mt6878")
    validate(base, output, vendor)
    require((gen.HERE / "stream-owner.patch").read_text() == delta, "stale stream delta")
    require(json.loads((gen.HERE / "evidence.json").read_text()) == evidence, "stale stream evidence")
    print("PASS: actual stream lifecycle, identity 0121 clock contract, checked reset and retained dependency ledger")
    print("PASS: exact source pins, untouched media/register interfaces and strict shipping-baseline patch application")
    print("OPEN: rail/reset/pad ownership handoff, CAM/MMUP/CSI/DMA and calibration; DT remains disabled")
    print("NOT RUN: native compile, schema/DTB, emulation or capture")
    return base, output, delta, evidence, vendor


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    gen.arguments(parser)
    args = parser.parse_args()
    check(args.kernel_archive, args.device_repo, args.modules_repo)
