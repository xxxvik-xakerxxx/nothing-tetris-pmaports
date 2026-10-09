#!/usr/bin/env python3
"""Mechanically transplant pinned register tables and checked power helpers."""
import argparse
import difflib
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PATCHES = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
COMMIT = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
SOURCE = "mtkcam/imgsensor/src-v4l2/common/imx882_mipi_raw/imx882mipiraw_Sensor.c"
OUTPUT = PATCHES / "0112-media-i2c-imx882-v4l2-controls.patch"


def vendor_source(repo):
    return subprocess.check_output(
        ["git", "show", f"{COMMIT}:{SOURCE}"], cwd=repo, text=True
    )


def registers(source, name):
    body = re.search(r"static kal_uint16 " + name + r"\[\] = \{(.*?)\};",
                     source, re.S).group(1)
    body = re.sub(r"/\*.*?\*/|//[^\n]*", "", body, flags=re.S)
    values = [int(v.strip(), 0) for v in body.split(",") if v.strip()]
    assert len(values) % 2 == 0
    pairs = list(zip(values[::2], values[1::2]))
    assert all(0 <= a <= 65535 and 0 <= v <= 255 for a, v in pairs)
    assert not any(a == 0x0100 and v == 1 for a, v in pairs)
    return pairs


def power_helpers():
    original = (PATCHES / "0049-media-i2c-imx882-identity.patch").read_text()
    tail = original.split("+++ b/drivers/media/i2c/imx882-identity.c\n", 1)[1]
    code = "".join(line[1:] + "\n" for line in tail.splitlines()
                   if line.startswith("+") and not line.startswith("+++"))
    with tempfile.TemporaryDirectory(prefix="imx882-power-") as tmp:
        file = Path(tmp) / "drivers/media/i2c/imx882-identity.c"
        file.parent.mkdir(parents=True)
        file.write_text(code)
        for name in ("0050-media-i2c-imx882-honor-active-low-reset.patch",
                     "0106-media-i2c-imx882-check-shutdown.patch",
                     "0107-media-i2c-imx882-hold-clock-rate.patch"):
            subprocess.run(["patch", "--batch", "-p1", "-i", str(PATCHES / name)],
                           cwd=tmp, check=True, capture_output=True)
        code = file.read_text()
    code = code[:code.index("static int imx882_identity_probe")]
    code = code[code.index("#include <linux/clk.h>"):]
    return code


def outputs(repo):
    source = vendor_source(repo)
    tables = "/* SPDX-License-Identifier: GPL-2.0-only */\n"
    tables += f"/* Exact register order from Nothing 4.1 modules {COMMIT}. */\n"
    tables += '#include "imx882-stream-core.h"\n\n'
    for vendor, target in (("imx882_init_setting", "imx882_init_regs"),
                           ("imx882_preview_setting", "imx882_preview_regs"),
                           ("imx882_normal_video_setting", "imx882_video_regs")):
        tables += f"static const struct imx882_reg {target}[] = {{\n"
        tables += "".join(f"\t{{ 0x{a:04x}, 0x{v:02x} }},\n"
                          for a, v in registers(source, vendor))
        tables += "};\n\n"
    tables += """struct imx882_mode {
	unsigned int width, height;
	const struct imx882_reg *regs;
	unsigned int count;
};

static const struct imx882_mode imx882_modes[] = {
	{ 4000, 3000, imx882_preview_regs, ARRAY_SIZE(imx882_preview_regs) },
	{ 4096, 2304, imx882_video_regs, ARRAY_SIZE(imx882_video_regs) },
};
"""
    driver = "// SPDX-License-Identifier: GPL-2.0-only\n"
    driver += "/* Unenabled candidate: requires owned power and a C-PHY receiver. */\n"
    driver += "#include <linux/kernel.h>\n#include <linux/mutex.h>\n#include <linux/pm.h>\n"
    driver += "#include <media/v4l2-async.h>\n#include <media/v4l2-ctrls.h>\n"
    driver += "#include <media/v4l2-device.h>\n#include <media/v4l2-fwnode.h>\n"
    driver += '#include "imx882-tetris-tables.h"\n'
    driver += power_helpers() + (HERE / "v4l2-body.c").read_text().split("\n", 1)[1]
    return {"drivers/media/i2c/imx882-tetris-stream.c": driver,
            "drivers/media/i2c/imx882-tetris-tables.h": tables,
            "drivers/media/i2c/imx882-stream-core.h":
                (HERE / "imx882-stream-core.h").read_text(),
            "Documentation/devicetree/bindings/media/i2c/nothing,tetris-imx882-stream.yaml":
                (HERE / "nothing,tetris-imx882-stream.yaml").read_text()}


def patch_text(repo):
    patch = "From: Codex <codex@openai.com>\n"
    patch += "Subject: [PATCH] media: add bounded Tetris IMX882 V4L2 streaming candidate\n\n"
    patch += "No board DT activation. Keep identity-only probing as a separate driver.\n"
    patch += "Tables are mechanically copied from the pinned Nothing 4.1 driver.\n"
    patch += "Controls use short exposure only; calibration and receiver ownership\n"
    patch += "remain separate runtime gates. Build native tests and module in CI only.\n\n"
    for path, text in outputs(repo).items():
        patch += f"diff --git a/{path} b/{path}\nnew file mode 100644\n"
        patch += "".join(difflib.unified_diff([], text.splitlines(keepends=True),
                        fromfile="/dev/null", tofile="b/" + path))
    patch += """diff --git a/drivers/media/i2c/Kconfig b/drivers/media/i2c/Kconfig
--- a/drivers/media/i2c/Kconfig
+++ b/drivers/media/i2c/Kconfig
@@ -786,3 +786,14 @@
 \t  explicitly selected bring-up device trees only.
\x20
+config VIDEO_IMX882_TETRIS
+	tristate "Nothing Tetris IMX882 V4L2 streaming candidate"
+	depends on I2C && OF && GPIOLIB && COMMON_CLK && REGULATOR && PINCTRL
+	depends on VIDEO_DEV && MEDIA_CONTROLLER
+	select V4L2_FWNODE
+	help
+	  Unenabled C-PHY sensor candidate. Requires explicit board power
+	  ownership and a compatible receiver. Does not enable any DT nodes.
+	  Supports binned 30 fps modes and standard exposure/gain controls.
+	  Per-unit calibration and receiver DMA bring-up are separate tasks.
+
 source "drivers/media/i2c/ccs/Kconfig"
diff --git a/drivers/media/i2c/Makefile b/drivers/media/i2c/Makefile
--- a/drivers/media/i2c/Makefile
+++ b/drivers/media/i2c/Makefile
@@ -126,3 +126,4 @@
 obj-$(CONFIG_VIDEO_RJ54N1) += rj54n1cb0c.o
 obj-$(CONFIG_VIDEO_IMX882_IDENTITY) += imx882-identity.o
+obj-$(CONFIG_VIDEO_IMX882_TETRIS) += imx882-tetris-stream.o
 obj-$(CONFIG_VIDEO_PD9302A) += pd9302a.o
"""
    return patch


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor-repo", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = patch_text(args.vendor_repo)
    if args.check:
        assert OUTPUT.read_text() == result, "generated patch is stale"
        print("IMX882 generated patch matches pinned source and templates")
    else:
        OUTPUT.write_text(result)
