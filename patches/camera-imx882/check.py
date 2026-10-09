#!/usr/bin/env python3
"""Offline source checks; this neither compiles nor touches the phone."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile
import re

from generate import HERE, OUTPUT, PATCHES, outputs, patch_text, registers, vendor_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor-repo", type=Path, required=True)
    parser.add_argument("--kernel-tree", type=Path, required=True)
    args = parser.parse_args()
    expected = patch_text(args.vendor_repo)
    assert OUTPUT.read_text() == expected, "generated patch differs"
    source = vendor_source(args.vendor_repo)
    for name, width, height in (("imx882_preview_setting", 4000, 3000),
                                ("imx882_normal_video_setting", 4096, 2304)):
        table = dict(registers(source, name))
        word = lambda a: table[a] * 256 + table[a + 1]
        assert word(0x034c) == width and word(0x034e) == height
        assert word(0x0342) == 7500 and word(0x0340) == 3900
        assert table[0x0112] == table[0x0113] == 10
        assert table[0x0114] == 2
        assert table[0x30a3] == 0x30
    init = dict(registers(source, "imx882_init_setting"))
    assert init[0x0136] == 0x18 and init[0x0137] == 0
    assert ".mipi_sensor_type = MIPI_CPHY" in source
    assert ".mipi_lane_num = SENSOR_MIPI_3_LANE" in source
    for mode in ("pre", "normal_video"):
        info = re.search(r"\." + mode + r"\s*=\s*\{(.*?)\}", source, re.S).group(1)
        assert re.search(r"\.pclk\s*=\s*878400000", info)
        assert re.search(r"\.linelength\s*=\s*7500", info)
        assert re.search(r"\.framelength\s*=\s*3900", info)
    assert "16384 - (16384*BASEGAIN)/gain" in source
    assert "write_cmos_sensor_8(ctx, 0x0350, 0x00)" in source
    assert "write_cmos_sensor_8(ctx, 0x3206, 0x00)" in source
    generated = outputs(args.vendor_repo)
    driver = generated["drivers/media/i2c/imx882-tetris-stream.c"]
    start = driver[driver.index("static int imx882_stream"):]
    assert start.index("imx882_power_on") < start.index("IMX882_REG_CHIP_ID_HIGH")
    assert start.index("IMX882_REG_CHIP_ID_LOW") < start.index("imx882_init_regs")
    assert start.index("imx882_init_regs") < start.index("camera->mode->regs")
    assert start.index("imx882_apply_controls") < start.index("0x0100, 1")
    assert start.index("0x0100, 1") < start.index("camera->streaming = true")
    probe = driver[driver.index("static int imx882_camera_probe"):]
    assert "imx882_power_on" not in probe and "i2c_master_send" not in probe
    assert "num_data_lanes != 3" in probe
    assert "lanes[0] != 0 || lanes[1] != 1 || lanes[2] != 2" in probe
    assert 'device_property_read_u32(dev, "clock-frequency"' in probe
    assert "xclk_rate != IMX882_XCLK_RATE" in probe
    assert "V4L2_CID_PIXEL_RATE, 878400000, 878400000, 1, 878400000" in probe
    assert "V4L2_CID_HBLANK, 3500, 3500, 1, 3500" in probe
    assert "V4L2_CID_LINK_FREQ" not in driver
    assert "clk_set_rate_exclusive" in driver and "clk_rate_exclusive_put" in driver
    assert "if (camera->faulted)" in driver
    with tempfile.TemporaryDirectory(prefix="imx882-apply-") as tmp:
        tmp = Path(tmp)
        (tmp / "drivers/media/i2c").mkdir(parents=True)
        for path in ("drivers/media/i2c/Kconfig", "drivers/media/i2c/Makefile",
                     "MAINTAINERS"):
            shutil.copyfile(args.kernel_tree / path, tmp / path)
        for name in ("0047-media-i2c-pd9302a-vcm.patch",
                     "0049-media-i2c-imx882-identity.patch"):
            subprocess.run(["patch", "--batch", "-p1", "-i", str(PATCHES / name)],
                           cwd=tmp, check=True)
        subprocess.run(["patch", "--batch", "-p1", "-i", str(OUTPUT)],
                       cwd=tmp, check=True)
        for path, content in generated.items():
            assert (tmp / path).read_text() == content
    print("PASS: exact pinned register tables, mode timings, source-derived controls")
    print("PASS: stream order, no probe-time power-on, C-PHY and fault guards")
    print("PASS: patch applies to the pinned kernel after identity patch")
    print("NOT RUN: native transaction tests or kernel module compilation (CI only)")


if __name__ == "__main__":
    main()
