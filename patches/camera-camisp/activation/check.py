#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Validate real sensor call sites, clock topology and patch application."""
import argparse
import json
from pathlib import Path
import re

import generate as gen
import yaml


def require(condition, message):
    if not condition:
        raise ValueError(message)


def ordered(text, markers):
    position = 0
    for marker in markers:
        position = text.index(marker, position) + len(marker)


def validate_native(base):
    i2c8 = gen.block(base[gen.OBSERVE], "i2c8: i2c@11e03000")
    require("CLK_IMP_W_S_I3C8_W1S" in i2c8 and "CLK_PERAOP_DMA_B" in i2c8,
            "I2C8 main/DMA suppliers changed")
    require("power-domains" not in i2c8, "I2C8 acquired a power-domain dependency")
    transfer = gen.block(base["drivers/i2c/busses/i2c-mt65xx.c"], "static int mtk_i2c_transfer")
    ordered(transfer, ["clk_bulk_enable", "if (ret)", "return ret;", "clk_bulk_disable"])
    top = base[gen.TOP]
    require('"uvpll192m_d8"' in gen.block(top, "camtg2_parents[]"), "native MCLK parent missing")
    require(re.search(r'FACTOR\(CLK_TOP_UVPLL192M_D8, "uvpll192m_d8",\s*"univpll", 1, 104\)', top),
            "native 24 MHz source topology changed")
    require(re.search(r'MUX_GATE_CLR_SET_UPD\(CLK_TOP_CAMTG2_SEL.*?camtg2_parents', top, re.S),
            "native MCLK selector/gate missing")
    require(re.search(r'FACTOR\(CLK_TOP_CAMTG2, "camtg2_ck",\s*"camtg2_sel", 1, 1\)', top),
            "native fixture baseline no longer uses a factor wrapper")
    clk = base["drivers/clk/clk.c"]
    for symbol in ("clk_rate_exclusive_get", "clk_rate_exclusive_put", "clk_set_parent",
                   "clk_get_parent", "clk_is_match", "__clk_is_enabled"):
        require("EXPORT_SYMBOL_GPL(" + symbol + ")" in clk, "missing real clock API: " + symbol)
    require("core->ops->is_enabled(core->hw)" in gen.block(clk, "static bool clk_core_is_enabled"),
            "enabled-state API no longer reaches provider")


def validate_delta(base, output):
    require(set(output) == set(gen.TARGETS), "unexpected integration targets")
    driver = output[gen.DRIVER]
    acquire = gen.block(driver, "static int imx882_mclk_acquire")
    release = gen.block(driver, "static void imx882_mclk_release")
    ordered(acquire, ["clk_is_match(imx882->xclk, imx882->xclk_source)", "return -EINVAL;",
                     "ret = clk_rate_exclusive_get(imx882->xclk)", "if (ret)", "return ret;",
                     "imx882->rate_exclusive = true;", "__clk_is_enabled(imx882->xclk)",
                     "ret = -EBUSY;", "goto release;",
                     "ret = clk_rate_exclusive_get(imx882->xclk_source)", "if (ret)", "goto release;",
                     "imx882->source_rate_exclusive = true;",
                     "clk_get_rate(imx882->xclk_source) != IMX882_XCLK_RATE", "ret = -ERANGE;",
                     "goto release;", "ret = clk_set_parent(imx882->xclk, imx882->xclk_source)",
                     "if (ret)", "goto release;", "clk_is_match(clk_get_parent(imx882->xclk)",
                     "clk_get_rate(imx882->xclk) != IMX882_XCLK_RATE", "ret = -EIO;",
                     "goto release;", "return 0;", "release:", "imx882_mclk_release(imx882);", "return ret;"])
    for field, clock in (("rate_exclusive", "xclk"), ("source_rate_exclusive", "xclk_source")):
        ordered(release, ["if (imx882->" + field + ")", "clk_rate_exclusive_put(imx882->" + clock + ");",
                          "imx882->" + field + " = false;"])
    require("clk_set_rate" not in driver, "sensor must not tune a shared PLL")
    probe = gen.block(driver, "static int imx882_identity_probe")
    ordered(probe, ["i2c_check_functionality", "return -EOPNOTSUPP;", "device_property_read_u32",
                    "device_property_present", "devm_regulator_bulk_get", 'devm_clk_get(dev, "xclk")',
                    'devm_clk_get(dev, "xclk-source")', "GPIOD_ASIS", "gpiod_is_active_low",
                    "regulator_is_enabled", "ret < 0", "sensor rail already enabled",
                    "imx882_mclk_acquire(imx882)", "if (ret)", "cannot acquire sensor MCLK",
                    "gpiod_direction_output", "imx882_mclk_release", "return ret;", "imx882_power_on",
                    "IMX882_REG_CHIP_ID_HIGH", "IMX882_REG_CHIP_ID_LOW", "chip_id != IMX882_CHIP_ID",
                    "ret = -ENODEV;", "cleanup_ret = imx882_power_off", "ret = cleanup_ret;"])
    require(probe.count("imx882_mclk_acquire") == 1, "unexpected acquisition call count")
    require("GPIOD_OUT" not in probe, "reset changed before acquisition gate")
    on = gen.block(driver, "static int imx882_power_on")
    original_on = gen.block(base[gen.DRIVER], "static int imx882_power_on")
    old_clock = "\tret = clk_set_rate_exclusive(imx882->xclk, IMX882_XCLK_RATE);\n\tif (ret)\n\t\treturn ret;\n\timx882->rate_exclusive = true;\n\tif (clk_get_rate(imx882->xclk) != IMX882_XCLK_RATE)\n\t\treturn -EINVAL;\n\n"
    require(on == gen.replace_once(original_on, old_clock, ""), "sensor rail/reset/delay order changed")
    off = gen.block(driver, "static int imx882_power_off")
    ordered(off, ["gpiod_set_value_cansleep", "clk_disable_unprepare", "pinctrl_select_state",
                  "imx882_disable_supply", "if (!ret)", "ret = err;", "imx882_mclk_release", "return ret;"])
    require(driver.count("imx882_mclk_release(imx882);") == 3, "unbalanced release paths")
    require(".probe = imx882_identity_probe" in driver and "module_i2c_driver(imx882_identity_driver)" in driver,
            "delta is not called by real driver probe")
    for forbidden in ("i2c_master_send", "regulator_force_disable", "regulator_get_exclusive", "arm_smccc",
                      "mmdvfs", "mmup", "ready", "cookie", "calibrated"):
        require(forbidden not in acquire, "unrelated or simulated acquisition dependency: " + forbidden)
    expected_dts = gen.replace_once(base[gen.DTS], '\t\tclocks = <&topckgen CLK_TOP_CAMTG2>;\n\t\tclock-names = "xclk";',
                                   '\t\tclocks = <&topckgen CLK_TOP_CAMTG2_SEL>,\n\t\t\t <&topckgen CLK_TOP_UVPLL192M_D8>;\n\t\tclock-names = "xclk", "xclk-source";\n\t\tclock-frequency = <24000000>;')
    require(output[gen.DTS] == expected_dts, "DT delta exceeds clock resource wiring")
    require('status = "disabled";' in gen.block(output[gen.DTS], "camera@1a"), "sensor activated prematurely")
    binding = yaml.safe_load(output[gen.BINDING])
    properties = binding["properties"]
    require(len(properties["clocks"]["items"]) == 2, "binding must require both real clocks")
    require([item["const"] for item in properties["clock-names"]["items"]] == ["xclk", "xclk-source"],
            "binding clock acquisition names changed")
    require(properties["clock-frequency"]["const"] == 24000000 and "clock-frequency" in binding["required"],
            "clock rate absent from binding requirements")


def check(upstream, archive=None):
    sources = gen.vendor_inputs(upstream)
    gen.verify_vendor(sources)
    base, evidence = gen.baseline(upstream, archive)
    validate_native(base)
    output = gen.payload(base)
    validate_delta(base, output)
    patch = gen.patch_text(base, output)
    require(gen.PATCH.read_text() == patch, "stale sensor integration patch")
    gen.apply_check(base, patch, output)
    packaged = gen.package_contract(patch)
    frozen = json.loads((gen.HERE / "evidence.json").read_text())
    require(frozen["packaged_patch"] == packaged, "packaged identity evidence changed")
    require(frozen["patch_sha256"] == gen.digest(patch.encode()), "patch hash mismatch")
    require(frozen["packaged_patch_sha256"] == evidence["packaged_patch_sha256"], "packaged baseline changed")
    require(frozen["kernel_archive_sha512"] == evidence["kernel_archive_sha512"], "kernel baseline changed")
    require(frozen["dt_application_scope"] == evidence["dt_application_scope"], "DT validation scope changed")
    for field, files in (("vendor_source_sha256", sources), ("baseline_sha256", base), ("output_sha256", output)):
        require(frozen[field] == {p: gen.digest(d.encode()) for p, d in files.items()}, "source evidence changed: " + field)
    require([frozen["kernel_commit"], frozen["device_modules_commit"], frozen["modules_commit"]] ==
            [gen.KERNEL, gen.DEVICE, gen.MODULES], "source pins changed")
    print("PASS: real identity probe calls checked MCLK acquisition before reset/power/ID")
    print("PASS: source pins, disabled DT resource delta and exact patch application")
    print("NOT RUN: native compilation, DT schema/DTB or runtime tests")
    return base, output, sources


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=gen.ROOT.parent)
    parser.add_argument("--kernel-archive", type=Path)
    args = parser.parse_args()
    check(args.upstream, args.kernel_archive)
